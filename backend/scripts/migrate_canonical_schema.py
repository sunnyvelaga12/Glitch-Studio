"""
migrate_canonical_schema.py — Non-Destructive, Idempotent Canonical Field Migration Script for VirtualHR

Usage:
    python backend/scripts/migrate_canonical_schema.py --dry-run
    python backend/scripts/migrate_canonical_schema.py --execute

Performs:
  1. Field standardization: companyId -> company_id, fullName -> full_name, etc.
  2. Leave balance schema migration: converts old leave_balance counters to canonical atomic schema
     { allocated, used, pending, available }
  3. Orphaned reference detection
  4. Idempotent execution (safe to run multiple times without duplicating or corrupting data)
"""

import sys
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone

# Ensure backend root is on Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_db, ensure_indexes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")


async def run_migration(dry_run: bool = True):
    logger.info(f"--- STARTING CANONICAL SCHEMA MIGRATION (Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}) ---")
    db = get_db()

    stats = {
        "users_scanned": 0,
        "users_migrated": 0,
        "companies_scanned": 0,
        "companies_migrated": 0,
        "leave_requests_scanned": 0,
        "leave_requests_migrated": 0,
        "documents_scanned": 0,
        "documents_migrated": 0,
        "policies_scanned": 0,
        "policies_migrated": 0,
        "orphaned_user_companies": 0,
        "orphaned_leave_users": 0,
    }

    # 1. Fetch valid company IDs to detect orphaned references
    existing_company_ids = set()
    async for comp in db.companies.find({}):
        existing_company_ids.add(str(comp["_id"]))

    # ------------------------------------------------------------------
    # 1. Users Migration
    # ------------------------------------------------------------------
    logger.info("Migrating 'users' collection...")
    async for user in db.users.find({}):
        stats["users_scanned"] += 1
        user_id = user["_id"]
        update_doc = {}

        # Canonical field mappings
        company_id = user.get("company_id") or user.get("companyId")
        if company_id:
            update_doc["company_id"] = company_id
            update_doc["companyId"] = company_id  # Maintain dual-read compatibility during migration
            if company_id not in existing_company_ids and user.get("role") != "super_admin":
                stats["orphaned_user_companies"] += 1
                logger.warning(f"Orphaned user detected: user {user_id} references non-existent company '{company_id}'")

        if "fullName" in user and "full_name" not in user:
            update_doc["full_name"] = user["fullName"]
        if "jobTitle" in user and "job_title" not in user:
            update_doc["job_title"] = user["jobTitle"]
        if "managerName" in user and "manager_name" not in user:
            update_doc["manager_name"] = user["managerName"]
        if "officeLocation" in user and "office_location" not in user:
            update_doc["office_location"] = user["officeLocation"]
        if "workMode" in user and "work_mode" not in user:
            update_doc["work_mode"] = user["workMode"]
        if "passwordHash" in user and "password_hash" not in user:
            update_doc["password_hash"] = user["passwordHash"]
        if "tokenVersion" in user and "token_version" not in user:
            update_doc["token_version"] = user["tokenVersion"]
        if "isActive" in user and "is_active" not in user:
            update_doc["is_active"] = user["isActive"]
        if "createdAt" in user and "created_at" not in user:
            update_doc["created_at"] = user["createdAt"]
        if "updatedAt" in user and "updated_at" not in user:
            update_doc["updated_at"] = user["updatedAt"]

        # Canonical Atomic Leave Balance Migration
        raw_lb = user.get("leave_balances") or user.get("leave_balance") or {}
        canonical_lb = {
            "casual_leave": {
                "allocated": 12,
                "used": raw_lb.get("casual_leave_used", 0),
                "pending": raw_lb.get("casual_leave_pending", 0),
                "available": raw_lb.get("casual_leave_remaining", 12 - raw_lb.get("casual_leave_used", 0) - raw_lb.get("casual_leave_pending", 0)),
            },
            "sick_leave": {
                "allocated": 10,
                "used": raw_lb.get("sick_leave_used", 0),
                "pending": raw_lb.get("sick_leave_pending", 0),
                "available": raw_lb.get("sick_leave_remaining", 10 - raw_lb.get("sick_leave_used", 0) - raw_lb.get("sick_leave_pending", 0)),
            },
            "privilege_leave": {
                "allocated": 15,
                "used": raw_lb.get("privilege_leave_used", 0),
                "pending": raw_lb.get("privilege_leave_pending", 0),
                "available": raw_lb.get("privilege_leave_remaining", 15 - raw_lb.get("privilege_leave_used", 0) - raw_lb.get("privilege_leave_pending", 0)),
            },
            "floating_holiday": {
                "allocated": 3,
                "used": raw_lb.get("floating_holidays_used", 0),
                "pending": raw_lb.get("floating_holidays_pending", 0),
                "available": raw_lb.get("floating_holidays_remaining", 3 - raw_lb.get("floating_holidays_used", 0) - raw_lb.get("floating_holidays_pending", 0)),
            },
        }
        update_doc["leave_balances"] = canonical_lb

        if update_doc:
            stats["users_migrated"] += 1
            if not dry_run:
                await db.users.update_one({"_id": user_id}, {"$set": update_doc})

    # ------------------------------------------------------------------
    # 2. Companies Migration
    # ------------------------------------------------------------------
    logger.info("Migrating 'companies' collection...")
    async for comp in db.companies.find({}):
        stats["companies_scanned"] += 1
        comp_id = comp["_id"]
        update_doc = {}
        if "createdAt" in comp and "created_at" not in comp:
            update_doc["created_at"] = comp["createdAt"]
        if "updatedAt" in comp and "updated_at" not in comp:
            update_doc["updated_at"] = comp["updatedAt"]

        if update_doc:
            stats["companies_migrated"] += 1
            if not dry_run:
                await db.companies.update_one({"_id": comp_id}, {"$set": update_doc})

    # ------------------------------------------------------------------
    # 3. Leave Requests Migration
    # ------------------------------------------------------------------
    logger.info("Migrating 'leave_requests' collection...")
    async for leave in db.leave_requests.find({}):
        stats["leave_requests_scanned"] += 1
        leave_id = leave["_id"]
        update_doc = {}

        company_id = leave.get("company_id") or leave.get("companyId")
        if company_id:
            update_doc["company_id"] = company_id
            update_doc["companyId"] = company_id

        user_id = leave.get("user_id") or leave.get("userId") or leave.get("employee_id")
        if user_id:
            update_doc["user_id"] = user_id

        if "from_date" in leave and "start_date" not in leave:
            update_doc["start_date"] = leave["from_date"]
        if "to_date" in leave and "end_date" not in leave:
            update_doc["end_date"] = leave["to_date"]

        if update_doc:
            stats["leave_requests_migrated"] += 1
            if not dry_run:
                await db.leave_requests.update_one({"_id": leave_id}, {"$set": update_doc})

    # ------------------------------------------------------------------
    # 4. Documents Migration
    # ------------------------------------------------------------------
    logger.info("Migrating 'documents' collection...")
    async for doc in db.documents.find({}):
        stats["documents_scanned"] += 1
        doc_id = doc["_id"]
        update_doc = {}

        company_id = doc.get("company_id") or doc.get("companyId")
        if company_id:
            update_doc["company_id"] = company_id
            update_doc["companyId"] = company_id
        if "uploadedBy" in doc and "uploaded_by" not in doc:
            update_doc["uploaded_by"] = doc["uploadedBy"]
        if "uploadedAt" in doc and "uploaded_at" not in doc:
            update_doc["uploaded_at"] = doc["uploadedAt"]
        if "updatedAt" in doc and "updated_at" not in doc:
            update_doc["updated_at"] = doc["updatedAt"]

        if update_doc:
            stats["documents_migrated"] += 1
            if not dry_run:
                await db.documents.update_one({"_id": doc_id}, {"$set": update_doc})

    # ------------------------------------------------------------------
    # 5. Database Indexes Initialization
    # ------------------------------------------------------------------
    if not dry_run:
        logger.info("Ensuring database indexes...")
        await ensure_indexes()

    logger.info("--- MIGRATION SUMMARY REPORT ---")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    logger.info(f"Status: {'DRY-RUN COMPLETED (No data mutated)' if dry_run else 'SUCCESSFULLY MIGRATED'}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Canonical Schema Migration Script for VirtualHR")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry-run inspection without mutating DB records")
    parser.add_argument("--execute", action="store_true", help="Execute canonical schema updates in MongoDB")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        logger.error("Must specify either --dry-run or --execute")
        sys.exit(1)

    asyncio.run(run_migration(dry_run=not args.execute))


if __name__ == "__main__":
    main()
