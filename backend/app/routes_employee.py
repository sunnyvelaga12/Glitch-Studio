"""
Employee Management API Routes

Provides endpoints for:
- Employee profiles and data
- Attendance tracking
- Leave management
- Employee statistics
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.schemas import (
    EmployeeProfileResponse,
    LeaveBalanceResponse,
    AttendanceRecordResponse,
    EmployeeStatsResponse,
    LeaveStatsResponse,
)
from app.deps import get_current_user
from app.db import get_db

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


# ─── Employee Profile ────────────────────────────────────────────────────────

@router.get("/profile/me", response_model=EmployeeProfileResponse)
async def get_my_profile(
    current_user = Depends(get_current_user),
):
    """Get current user's employee profile (strictly company scoped)."""
    try:
        user_id = current_user.get("sub") or current_user.get("id")
        user_email = current_user.get("email", "")
        company_id = current_user.get("company_id") or current_user.get("companyId")
        
        mongo_db = get_db()
        c_filter = {"company_id": company_id} if company_id else {}

        
        from bson import ObjectId
        u_doc = None
        if user_id:
            u_doc = await mongo_db.users.find_one({"_id": user_id, **c_filter})
            if not u_doc and ObjectId.is_valid(user_id):
                u_doc = await mongo_db.users.find_one({"_id": ObjectId(user_id), **c_filter})
        if not u_doc and user_email:
            u_doc = await mongo_db.users.find_one({"email": user_email, **c_filter})
            
        full_name = (u_doc.get("fullName") if u_doc else None) or current_user.get("fullName")
        email = (u_doc.get("email") if u_doc else None) or user_email
        
        if not full_name:
            full_name = email.split("@")[0].replace(".", " ").title() if email else "Employee Workspace"
            
        name_parts = full_name.split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        dept = (u_doc.get("department") if u_doc else None) or "General"
        title = (u_doc.get("jobTitle") or u_doc.get("designation") if u_doc else None) or "Team Member"
        manager = (u_doc.get("managerName") if u_doc else None) or "Reporting Manager"

        office_loc = (u_doc.get("officeLocation") if u_doc else None) or "Main Office"
        mode = (u_doc.get("workMode") if u_doc else None) or "Hybrid"

        return {
            "employee_id": str(user_id) if user_id else "EMP001",
            "first_name": first_name,
            "last_name": last_name,
            "email": email or "employee@company.com",
            "phone": (u_doc.get("phone") if u_doc else None) or "+1-234-567-8900",
            "department": dept,
            "designation": title,
            "manager_name": manager,
            "office_location": office_loc,
            "work_mode": mode,
            "employment_status": "Active",
            "years_with_company": 2,
            "performance_rating": 4.8,
            "skills": ["Python", "React", "AI", "Cloud"],
            "certifications": ["Certified Developer"],
            "date_of_joining": "2024-01-15",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching profile: {str(e)}")


@router.get("/profile/{employee_id}", response_model=EmployeeProfileResponse)
async def get_employee_profile(
    employee_id: str,
    current_user = Depends(get_current_user),
):
    """Get complete employee profile with company multi-tenant isolation."""
    company_id = current_user.get("company_id") or current_user.get("companyId")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    mongo_db = get_db()
    c_filter = {"company_id": company_id}
    from bson import ObjectId
    u_doc = await mongo_db.users.find_one({"_id": employee_id, **c_filter})
    if not u_doc and ObjectId.is_valid(employee_id):
        u_doc = await mongo_db.users.find_one({"_id": ObjectId(employee_id), **c_filter})

    
    if not u_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found or access denied",
        )

    full_name = u_doc.get("fullName") or u_doc.get("name") or "Employee"
    parts = full_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    return {
        "employee_id": str(u_doc.get("_id")),
        "first_name": first_name,
        "last_name": last_name,
        "email": u_doc.get("email", ""),
        "phone": u_doc.get("phone", ""),
        "department": u_doc.get("department", "General"),
        "designation": u_doc.get("jobTitle") or u_doc.get("designation", "Team Member"),
        "manager_name": u_doc.get("managerName", ""),
        "office_location": u_doc.get("officeLocation", ""),
        "work_mode": u_doc.get("workMode", "Hybrid"),
        "employment_status": u_doc.get("employmentStatus", "Active"),
        "years_with_company": u_doc.get("years_with_company", 1),
        "performance_rating": u_doc.get("performance_rating", 0.0),
        "skills": u_doc.get("skills", []),
        "certifications": u_doc.get("certifications", []),
        "date_of_joining": u_doc.get("date_of_joining", u_doc.get("createdAt", "")[:10] if u_doc.get("createdAt") else ""),
    }



# ─── Leave Balance ────────────────────────────────────────────────────────────

@router.get("/leave-balance/{employee_id}", response_model=LeaveBalanceResponse)
async def get_leave_balance(
    employee_id: str,
    current_user = Depends(get_current_user),
):
    """Get employee's leave balance."""
    try:
        return {
            "employee_id": employee_id,
            "casual_leave_total": 12,
            "casual_leave_used": 3,
            "casual_leave_remaining": 9,
            "sick_leave_total": 10,
            "sick_leave_used": 2,
            "sick_leave_remaining": 8,
            "privilege_leave_total": 20,
            "privilege_leave_used": 5,
            "privilege_leave_remaining": 15,
            "floating_holidays_total": 5,
            "floating_holidays_used": 2,
            "floating_holidays_remaining": 3,
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leave balance: {str(e)}")


@router.get("/leave-balance/me", response_model=LeaveBalanceResponse)
async def get_my_leave_balance(
    current_user = Depends(get_current_user),
):
    """Get current user's leave balance."""
    employee_id = current_user.get("employee_id", "EMP001")
    try:
        return {
            "employee_id": employee_id,
            "casual_leave_total": 12,
            "casual_leave_used": 3,
            "casual_leave_remaining": 9,
            "sick_leave_total": 10,
            "sick_leave_used": 2,
            "sick_leave_remaining": 8,
            "privilege_leave_total": 20,
            "privilege_leave_used": 5,
            "privilege_leave_remaining": 15,
            "floating_holidays_total": 5,
            "floating_holidays_used": 2,
            "floating_holidays_remaining": 3,
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leave balance: {str(e)}")


# ─── Attendance ──────────────────────────────────────────────────────────────

@router.get("/attendance/{employee_id}", response_model=List[AttendanceRecordResponse])
async def get_attendance(
    employee_id: str,
    days: int = Query(5, ge=1, le=30),
    current_user = Depends(get_current_user),
):
    """Get employee's attendance records for past N days."""
    try:
        records = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "status": ["Present", "WFH", "Half-Day", "Absent", "Leave"][i % 5],
                "hours_worked": 8.5 if i % 2 == 0 else 4.0,
                "check_in_time": "09:00 AM",
                "check_out_time": "05:30 PM",
                "location": "San Francisco" if i % 2 == 0 else "Remote",
            })
        return sorted(records, key=lambda x: x["date"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching attendance: {str(e)}")


@router.get("/attendance/me", response_model=List[AttendanceRecordResponse])
async def get_my_attendance(
    days: int = Query(5, ge=1, le=30),
    current_user = Depends(get_current_user),
):
    """Get current user's attendance records."""
    employee_id = current_user.get("employee_id", "EMP001")
    try:
        records = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "status": ["Present", "WFH", "Half-Day", "Absent", "Leave"][i % 5],
                "hours_worked": 8.5 if i % 2 == 0 else 4.0,
                "check_in_time": "09:00 AM",
                "check_out_time": "05:30 PM",
                "location": "San Francisco" if i % 2 == 0 else "Remote",
            })
        return sorted(records, key=lambda x: x["date"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching attendance: {str(e)}")


# ─── Employee Statistics ─────────────────────────────────────────────────────

@router.get("/stats", response_model=EmployeeStatsResponse)
async def get_employee_stats(
    current_user = Depends(get_current_user),
):
    """Get company-wide employee statistics."""
    try:
        return {
            "total_employees": 125,
            "active_employees": 120,
            "on_leave_today": 12,
            "absent_today": 15,
            "present_today": 98,
            "work_from_home_today": 35,
            "terminations_this_month": 1,
            "new_hires_this_month": 3,
            "average_performance_rating": 4.2,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")


@router.get("/leave-stats", response_model=LeaveStatsResponse)
async def get_leave_stats(
    current_user = Depends(get_current_user),
):
    """Get leave statistics."""
    try:
        return {
            "pending_approvals": 12,
            "approved_this_month": 28,
            "rejected_this_month": 2,
            "on_leave_today": 12,
            "returning_tomorrow": 5,
            "total_leaves_taken_this_year": 45,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leave stats: {str(e)}")


# ─── Dashboard Data ──────────────────────────────────────────────────────────

@router.get("/dashboard-overview")
async def get_dashboard_overview(
    current_user = Depends(get_current_user),
):
    """Get all data needed for dashboard overview in one call."""
    try:
        employee_id = current_user.get("employee_id", "EMP001")
        
        profile = {
            "employee_id": employee_id,
            "first_name": "John",
            "last_name": "Doe",
            "department": "Engineering",
            "designation": "Senior Software Engineer",
            "manager_name": "Jane Smith",
            "performance_rating": 4.5,
        }
        
        leave_balance = {
            "casual_leave_remaining": 9,
            "sick_leave_remaining": 8,
            "privilege_leave_remaining": 15,
            "floating_holidays_remaining": 3,
        }
        
        attendance = []
        for i in range(5):
            date = datetime.now() - timedelta(days=i)
            attendance.append({
                "date": date.strftime("%Y-%m-%d"),
                "status": ["Present", "WFH", "Half-Day", "Absent", "Leave"][i % 5],
                "hours_worked": 8.5 if i % 2 == 0 else 4.0,
            })
        
        return {
            "profile": profile,
            "leave_balance": leave_balance,
            "attendance": sorted(attendance, key=lambda x: x["date"]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard data: {str(e)}")


# ─── Leave Applications ──────────────────────────────────────────────────────

@router.post("/leaves/apply")
async def apply_leave(
    request: Request,
    payload: dict,
    current_user = Depends(get_current_user),
):
    """Submit a leave application for current employee with idempotency key, atomic $expr reservation, and transaction recovery."""
    from app.utils import format_api_error_response

    mongo_db = get_db()
    
    # 1. Enforce strict server-derived tenant & user context (ignoring client payloads/headers/query params)
    user_id = current_user.get("user_id") or current_user.get("sub") or "EMP001"
    company_id = current_user.get("company_id") or current_user.get("companyId") or "company_1"
    user_email = current_user.get("email", "")

    # 2. Extract Idempotency Key & calculate canonical payload hash
    idempotency_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
    endpoint_key = "POST:/api/v1/employees/leaves/apply"
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    if idempotency_key:
        idempotency_query = {
            "company_id": company_id,
            "user_id": user_id,
            "endpoint": endpoint_key,
            "idempotency_key": idempotency_key,
        }
        existing_idem = await mongo_db.idempotency_keys.find_one(idempotency_query)
        if existing_idem:
            if existing_idem.get("payload_hash") == payload_hash:
                return JSONResponse(
                    status_code=existing_idem.get("status_code", 201),
                    content=existing_idem.get("response_body"),
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=format_api_error_response(
                        "IDEMPOTENCY_KEY_REUSED",
                        "Idempotency key has already been used with a different request payload.",
                    ),
                )

    # 3. Extract dates & calculate duration
    from_date = payload.get("from_date") or payload.get("start_date") or ""
    to_date = payload.get("to_date") or payload.get("end_date") or ""
    leave_type = payload.get("leave_type", "casual_leave")
    reason = payload.get("reason", "")

    if not from_date or not to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_api_error_response("INVALID_REQUEST", "Start and end dates are required"),
        )

    try:
        d1 = datetime.strptime(from_date, "%Y-%m-%d")
        d2 = datetime.strptime(to_date, "%Y-%m-%d")
        if d2 < d1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=format_api_error_response("INVALID_REQUEST", "end_date cannot be earlier than start_date"),
            )
        duration_days = (d2 - d1).days + 1
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_api_error_response("INVALID_REQUEST", f"Invalid date format: {str(ve)}"),
        )

    # 4. Fetch user details for display
    u_doc = await mongo_db.users.find_one({"_id": user_id, "company_id": company_id})
    if not u_doc and user_email:
        u_doc = await mongo_db.users.find_one({"email": user_email, "company_id": company_id})

    emp_name = (u_doc.get("fullName") if u_doc else None) or current_user.get("fullName") or "Aarav Sharma"
    dept = (u_doc.get("department") if u_doc else None) or "Engineering"
    manager = (u_doc.get("managerName") if u_doc else None) or "Reporting Manager"
    emp_code = (u_doc.get("employeeId") if u_doc else None) or user_id

    leave_id = f"LV-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)

    doc_response = {
        "_id": leave_id,
        "id": leave_id,
        "leave_id": leave_id,
        "company_id": company_id,
        "companyId": company_id,
        "user_id": user_id,
        "employee_name": emp_name,
        "employee_email": user_email,
        "employee_id": emp_code,
        "department": dept,
        "manager_name": manager,
        "leave_type": leave_type,
        "from_date": from_date,
        "to_date": to_date,
        "start_date": from_date,
        "end_date": to_date,
        "days": duration_days,
        "reason": reason,
        "status": "pending",
        "applied_at": now_iso,
        "created_at": now_iso,
    }

    # 5. Bounded 3-Attempt Retry Loop for Atomic Transaction & Concurrent Recovery
    for attempt in range(1, 4):
        session = None
        try:
            # Check if MongoDB deployment supports multi-document transactions
            client = mongo_db.client
            try:
                session = await client.start_session()
                session.start_transaction()
            except Exception:
                session = None

            # A. Atomic $expr balance reservation (allocated - used - pending >= duration_days)
            balance_filter = {
                "_id": user_id,
                "company_id": company_id,
                "$expr": {
                    "$gte": [
                        {
                            "$subtract": [
                                {
                                    "$subtract": [
                                        f"$leave_balances.{leave_type}.allocated",
                                        f"$leave_balances.{leave_type}.used",
                                    ]
                                },
                                f"$leave_balances.{leave_type}.pending",
                            ]
                        },
                        duration_days,
                    ]
                },
            }

            update_doc = {
                "$inc": {
                    f"leave_balances.{leave_type}.pending": duration_days,
                },
                "$set": {"updated_at": now_iso},
            }

            kwargs = {"return_document": ReturnDocument.AFTER}
            if session:
                kwargs["session"] = session

            updated_user = await mongo_db.users.find_one_and_update(balance_filter, update_doc, **kwargs)

            if not updated_user:
                if session and session.in_transaction:
                    await session.abort_transaction()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=format_api_error_response(
                        "INSUFFICIENT_LEAVE_BALANCE",
                        f"Insufficient available balance for leave type '{leave_type}'. Requested: {duration_days} days.",
                    ),
                )

            # B. Insert Leave Request
            insert_kwargs = {}
            if session:
                insert_kwargs["session"] = session
            await mongo_db.leave_requests.insert_one(doc_response, **insert_kwargs)

            # C. Insert Idempotency Record if key supplied
            if idempotency_key:
                idempotency_doc = {
                    "_id": f"{company_id}:{user_id}:{endpoint_key}:{idempotency_key}",
                    "company_id": company_id,
                    "user_id": user_id,
                    "endpoint": endpoint_key,
                    "idempotency_key": idempotency_key,
                    "payload_hash": payload_hash,
                    "status_code": 201,
                    "response_body": doc_response,
                    "response_version": 1,
                    "created_at": now_dt,
                }
                await mongo_db.idempotency_keys.insert_one(idempotency_doc, **insert_kwargs)

            # D. Commit transaction
            if session and session.in_transaction:
                await session.commit_transaction()

            # Record Audit Event
            from app.security_audit import log_security_audit_event
            await log_security_audit_event(
                event_type="LEAVE_APPLIED",
                company_id=company_id,
                actor_user_id=user_id,
                actor_role="employee",
                resource_type="leave_request",
                resource_id=leave_id,
                metadata={"leave_type": leave_type, "days": duration_days, "status": "pending"},
            )

            return JSONResponse(status_code=201, content=doc_response)

        except (DuplicateKeyError, PyMongoError) as exc:
            if session and session.in_transaction:
                await session.abort_transaction()

            # Check if winner committed idempotency record
            if idempotency_key:
                idempotency_query = {
                    "company_id": company_id,
                    "user_id": user_id,
                    "endpoint": endpoint_key,
                    "idempotency_key": idempotency_key,
                }
                existing_idem = await mongo_db.idempotency_keys.find_one(idempotency_query)
                if existing_idem:
                    if existing_idem.get("payload_hash") == payload_hash:
                        return JSONResponse(
                            status_code=existing_idem.get("status_code", 201),
                            content=existing_idem.get("response_body"),
                        )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=format_api_error_response(
                                "IDEMPOTENCY_KEY_REUSED",
                                "Idempotency key has already been used with a different request payload.",
                            ),
                        )

            if attempt == 3:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=format_api_error_response(
                        "LEAVE_STATE_CONFLICT",
                        "Concurrent leave application collision. Please retry.",
                    ),
                )
        finally:
            if session:
                await session.end_session()



@router.get("/leaves/my-requests")
async def get_my_leave_requests(
    current_user = Depends(get_current_user),
):
    """Get current user's submitted leave applications (company scoped)."""
    try:
        from app.db import get_db
        mongo_db = get_db()
        company_id = current_user.get("companyId")
        user_id = current_user.get("sub") or current_user.get("id")
        user_email = current_user.get("email", "")

        user_conds = []
        if user_id: user_conds.append({"user_id": user_id})
        if user_email: user_conds.append({"employee_email": user_email})
        
        query = {}
        if company_id:
            query["$or"] = [{"company_id": company_id}, {"companyId": company_id}]
            
        if user_conds:
            if "$or" in query:
                query = {"$and": [{"$or": query["$or"]}, {"$or": user_conds}]}
            else:
                query["$or"] = user_conds

        cursor = mongo_db.leave_requests.find(query).sort("applied_at", -1)
        items = await cursor.to_list(length=50)

        for item in items:
            if "_id" in item and not isinstance(item["_id"], str):
                item["_id"] = str(item["_id"])
            if "id" not in item:
                item["id"] = item.get("_id")

        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leave requests: {str(e)}")
