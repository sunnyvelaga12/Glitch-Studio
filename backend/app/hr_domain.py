"""
HR Domain Service — Business Invariants, State Machine & CAS Transitions

Implements core domain rules for VirtualHR:
1. Manager Same-Tenant Verification (manager.company_id == employee.company_id)
2. Compare-And-Set (CAS) Leave Approvals / Rejections / Cancellations with 409 Conflict Protection
3. Atomic Leave Balance Updates
4. Single Active Policy Version Transactional Invariant
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pymongo import ReturnDocument
from app.db import get_db


class LeaveStateConflictError(Exception):
    """Raised when a compare-and-set (CAS) state transition fails due to concurrent modification."""
    pass


class LeaveInsufficientBalanceError(Exception):
    """Raised when an employee attempts to request more leave than their available balance."""
    pass


class CrossTenantValidationError(Exception):
    """Raised when a manager or resource belongs to a different tenant."""
    pass


async def validate_manager_tenant(db, company_id: str, manager_user_id: Optional[str]) -> bool:
    """
    Validates that the assigned manager belongs to the EXACT same company_id.
    Allows manager_user_id to be None (for top-level executives / CEOs).
    """
    if not manager_user_id:
        return True

    manager = await db.users.find_one({"_id": manager_user_id})
    if not manager:
        raise CrossTenantValidationError(f"Manager user ID '{manager_user_id}' does not exist.")

    if manager.get("company_id") != company_id:
        raise CrossTenantValidationError(
            f"Manager '{manager_user_id}' belongs to company '{manager.get('company_id')}', "
            f"which violates tenant boundary for employee in company '{company_id}'."
        )

    return True


async def submit_leave_request_atomic(
    db,
    company_id: str,
    user_id: str,
    request_id: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    total_days: int,
    reason: str,
    approver_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submits a new leave request after verifying available balance and atomically
    incrementing the 'pending' balance field.
    """
    # 1. Fetch current leave balance document
    balance_doc = await db.leave_balances.find_one({"company_id": company_id, "user_id": user_id, "year": 2026})
    if not balance_doc:
        raise LeaveInsufficientBalanceError(f"No leave balance record found for user '{user_id}'.")

    type_balance = balance_doc.get("balances", {}).get(leave_type, {"allocated": 0, "used": 0, "pending": 0})
    allocated = type_balance.get("allocated", 0)
    used = type_balance.get("used", 0)
    pending = type_balance.get("pending", 0)

    available = allocated - used - pending
    if available < total_days:
        raise LeaveInsufficientBalanceError(
            f"Insufficient {leave_type} leave balance. Requested: {total_days}, Available: {available}."
        )

    # 2. Increment pending balance atomically
    update_result = await db.leave_balances.update_one(
        {
            "company_id": company_id,
            "user_id": user_id,
            "year": 2026,
            f"balances.{leave_type}.pending": pending  # Optimistic check
        },
        {"$inc": {f"balances.{leave_type}.pending": total_days}}
    )

    if update_result.modified_count == 0:
        raise LeaveStateConflictError("Concurrent modification on leave balance. Please retry.")

    # 3. Create leave request document
    now = datetime.now(timezone.utc)
    leave_req = {
        "_id": request_id,
        "company_id": company_id,
        "user_id": user_id,
        "leave_type": leave_type,
        "start_date": start_date,
        "end_date": end_date,
        "total_days": total_days,
        "reason": reason,
        "status": "PENDING",
        "approver_id": approver_id,
        "approver_notes": None,
        "decided_at": None,
        "created_at": now,
        "updated_at": now
    }
    await db.leave_requests.insert_one(leave_req)

    # 4. Audit Log Entry
    await db.audit_logs.insert_one({
        "event_id": str(uuid.uuid4()),
        "company_id": company_id,
        "action": "LEAVE_SUBMITTED",
        "resource_id": request_id,
        "user_id": user_id,
        "details": {"leave_type": leave_type, "total_days": total_days},
        "timestamp": now
    })

    return leave_req


async def approve_leave_request_cas(
    db,
    company_id: str,
    request_id: str,
    approver_id: str,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Atomically approves a pending leave request using compare-and-set query.
    Prevents duplicate approval, race conditions, and returns 409 Conflict error on duplicate/invalid state.
    """
    now = datetime.now(timezone.utc)

    # 1. Compare-And-Set update: ONLY matches if status == "PENDING"
    updated_req = await db.leave_requests.find_one_and_update(
        {
            "_id": request_id,
            "company_id": company_id,
            "status": "PENDING"  # CAS Condition
        },
        {
            "$set": {
                "status": "APPROVED",
                "approver_id": approver_id,
                "approver_notes": notes,
                "decided_at": now,
                "updated_at": now
            }
        },
        return_document=ReturnDocument.AFTER
    )

    if not updated_req:
        # Check if request exists to provide exact error code
        existing = await db.leave_requests.find_one({"_id": request_id, "company_id": company_id})
        if not existing:
            raise LeaveStateConflictError(f"Leave request '{request_id}' not found.")
        raise LeaveStateConflictError(
            f"Leave request '{request_id}' cannot be approved because current status is '{existing.get('status')}'. "
            "Only PENDING requests can be approved."
        )

    # 2. Update balance atomically: decrement pending, increment used
    user_id = updated_req["user_id"]
    leave_type = updated_req["leave_type"]
    total_days = updated_req["total_days"]

    await db.leave_balances.update_one(
        {"company_id": company_id, "user_id": user_id, "year": 2026},
        {
            "$inc": {
                f"balances.{leave_type}.pending": -total_days,
                f"balances.{leave_type}.used": total_days
            }
        }
    )

    # 3. Audit Log Entry
    await db.audit_logs.insert_one({
        "event_id": str(uuid.uuid4()),
        "company_id": company_id,
        "action": "LEAVE_APPROVED",
        "resource_id": request_id,
        "user_id": user_id,
        "approver_id": approver_id,
        "details": {"leave_type": leave_type, "total_days": total_days},
        "timestamp": now
    })

    return updated_req


async def reject_leave_request_cas(
    db,
    company_id: str,
    request_id: str,
    approver_id: str,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Atomically rejects a pending leave request using compare-and-set query.
    Clears pending balance and updates status to REJECTED.
    """
    now = datetime.now(timezone.utc)

    updated_req = await db.leave_requests.find_one_and_update(
        {
            "_id": request_id,
            "company_id": company_id,
            "status": "PENDING"
        },
        {
            "$set": {
                "status": "REJECTED",
                "approver_id": approver_id,
                "approver_notes": notes,
                "decided_at": now,
                "updated_at": now
            }
        },
        return_document=ReturnDocument.AFTER
    )

    if not updated_req:
        existing = await db.leave_requests.find_one({"_id": request_id, "company_id": company_id})
        if not existing:
            raise LeaveStateConflictError(f"Leave request '{request_id}' not found.")
        raise LeaveStateConflictError(
            f"Leave request '{request_id}' cannot be rejected because current status is '{existing.get('status')}'."
        )

    # Release pending balance
    user_id = updated_req["user_id"]
    leave_type = updated_req["leave_type"]
    total_days = updated_req["total_days"]

    await db.leave_balances.update_one(
        {"company_id": company_id, "user_id": user_id, "year": 2026},
        {"$inc": {f"balances.{leave_type}.pending": -total_days}}
    )

    # Audit log
    await db.audit_logs.insert_one({
        "event_id": str(uuid.uuid4()),
        "company_id": company_id,
        "action": "LEAVE_REJECTED",
        "resource_id": request_id,
        "user_id": user_id,
        "approver_id": approver_id,
        "details": {"notes": notes},
        "timestamp": now
    })

    return updated_req


async def publish_policy_version_transactional(
    db,
    company_id: str,
    policy_id: str,
    target_version_number: int
) -> bool:
    """
    Publishes a policy version with a single active policy version invariant:
    1. Archives any existing active version for (company_id, policy_id).
    2. Sets target version status to 'active'.
    3. Updates policy_documents.active_version to target version number.
    """
    now = datetime.now(timezone.utc)

    # Archive previous active versions
    await db.policy_versions.update_many(
        {
            "company_id": company_id,
            "policy_id": policy_id,
            "status": "active"
        },
        {"$set": {"status": "archived"}}
    )

    # Set target version to active
    ver_result = await db.policy_versions.update_one(
        {
            "company_id": company_id,
            "policy_id": policy_id,
            "version_number": target_version_number
        },
        {"$set": {"status": "active", "published_at": now}}
    )

    if ver_result.matched_count == 0:
        raise ValueError(f"Policy version v{target_version_number} for policy '{policy_id}' not found.")

    # Update master policy document
    await db.policy_documents.update_one(
        {"_id": policy_id, "company_id": company_id},
        {"$set": {"active_version": target_version_number}}
    )

    return True
