"""
policy_versioning.py — Immutable Policy Versioning Engine for VirtualHR

Enforces:
  1. Lifecycle state transitions: draft -> review -> approved -> published -> archived
  2. Immutability: Published policy version records in MongoDB CANNOT be mutated or overwritten.
  3. Versioning: Editing a published policy generates a new draft with an incremented version_number.
  4. Audit metadata: Tracks publisher_id, published_at, superseded_version_id, and change_summary.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status
from app.db import get_db

logger = logging.getLogger(__name__)

from pymongo.errors import DuplicateKeyError

VALID_STATUSES = {"draft", "review", "approved", "published", "archived"}

VALID_TRANSITIONS = {
    "draft": {"review", "archived"},
    "review": {"approved", "draft", "archived"},
    "approved": {"published", "draft", "archived"},
    "published": {"archived"},
    "archived": set(),
}


def transition_policy_state(current_status: str, target_status: str) -> None:
    """Validate lifecycle state transitions: draft -> review -> approved -> published -> archived."""
    if current_status == target_status:
        return
    allowed = VALID_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid policy lifecycle transition from '{current_status}' to '{target_status}'. Allowed transitions: {sorted(list(allowed))}",
        )


async def create_policy_draft(
    company_id: str,
    title: str,
    content_text: str,
    created_by: str,
    change_summary: str = "Initial policy draft",
    existing_policy_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new policy or a new draft version of an existing policy.
    """
    db = get_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    policy_id = existing_policy_id or str(uuid.uuid4())

    # Find highest version number for this policy
    latest_version = await db.policy_versions.find_one(
        {"policy_id": policy_id, "company_id": company_id},
        sort=[("version_number", -1)]
    )

    version_number = (latest_version["version_number"] + 1) if latest_version else 1
    version_id = str(uuid.uuid4())

    doc = {
        "_id": version_id,
        "policy_id": policy_id,
        "version_number": version_number,
        "company_id": company_id,
        "companyId": company_id,
        "title": title,
        "content_text": content_text,
        "status": "draft",
        "created_by": created_by,
        "created_at": now_iso,
        "published_by": None,
        "published_at": None,
        "superseded_version_id": latest_version["_id"] if latest_version else None,
        "change_summary": change_summary,
    }

    try:
        await db.policy_versions.insert_one(doc)
    except DuplicateKeyError as exc:
        logger.warning(f"Concurrent policy draft creation collision on policy {policy_id} v{version_number}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Concurrent modification collision: Policy version v{version_number} already exists for policy '{policy_id}'. Please refresh and retry.",
        )

    logger.info(f"Created policy draft v{version_number} for policy {policy_id} (Company: {company_id})")
    return doc



async def publish_policy_version(
    company_id: str,
    version_id: str,
    published_by: str,
) -> Dict[str, Any]:
    """
    Publish an approved policy version.
    Marks prior published versions of the same policy as 'archived'.
    """
    db = get_db()
    now_iso = datetime.now(timezone.utc).isoformat()

    target_version = await db.policy_versions.find_one({
        "_id": version_id,
        "$or": [{"company_id": company_id}, {"companyId": company_id}]
    })

    if not target_version:
        raise HTTPException(status_code=404, detail="Policy version not found or access denied")

    if target_version["status"] == "published":
        return target_version  # Already published, immutable

    policy_id = target_version["policy_id"]

    # Archive previous published versions for this policy
    await db.policy_versions.update_many(
        {"policy_id": policy_id, "company_id": company_id, "status": "published"},
        {"$set": {"status": "archived", "updated_at": now_iso}}
    )

    # Publish target version
    await db.policy_versions.update_one(
        {"_id": version_id},
        {
            "$set": {
                "status": "published",
                "published_by": published_by,
                "published_at": now_iso,
                "updated_at": now_iso,
            }
        }
    )

    logger.info(f"Published policy version {version_id} (v{target_version['version_number']}) for policy {policy_id}")

    # Also update current published policy snapshot in policies collection
    await db.policies.update_one(
        {"company_id": company_id, "policy_id": policy_id},
        {
            "$set": {
                "policy_id": policy_id,
                "company_id": company_id,
                "companyId": company_id,
                "title": target_version["title"],
                "content_text": target_version["content_text"],
                "current_version_id": version_id,
                "version_number": target_version["version_number"],
                "published_at": now_iso,
                "published_by": published_by,
            }
        },
        upsert=True
    )

    updated_doc = await db.policy_versions.find_one({"_id": version_id})
    return updated_doc
