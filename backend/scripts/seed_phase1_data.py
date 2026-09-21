"""
Phase 1 Seed Data Script — Populates Multi-Tenant HR Domain Records

Seeds:
1. Two distinct companies: Acme Corp (comp_acme_01) and Globex Corp (comp_globex_02)
2. Argon2id hashed company passkeys
3. Users and Employee system-of-record profiles with same-tenant manager hierarchy
4. Leave balances for 2026
5. Initial policy documents and versions
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, date, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import get_db, ensure_indexes
from app.passkey_service import hash_passkey
from app.auth import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("virtualhr.seed_phase1")


async def seed_phase1_data():
    db = get_db()
    logger.info("Starting Phase 1 seed data population...")

    # Ensure indexes exist
    await ensure_indexes()

    now = datetime.now(timezone.utc)

    # 1. Clean existing seed data
    await db.companies.delete_many({"_id": {"$in": ["comp_acme_01", "comp_globex_02"]}})
    await db.users.delete_many({"company_id": {"$in": ["comp_acme_01", "comp_globex_02"]}})
    await db.employees.delete_many({"company_id": {"$in": ["comp_acme_01", "comp_globex_02"]}})
    await db.leave_balances.delete_many({"company_id": {"$in": ["comp_acme_01", "comp_globex_02"]}})
    await db.policy_documents.delete_many({"company_id": {"$in": ["comp_acme_01", "comp_globex_02"]}})
    await db.policy_versions.delete_many({"company_id": {"$in": ["comp_acme_01", "comp_globex_02"]}})

    # 2. Seed Companies
    acme_passkey_hash = hash_passkey("ACME-2026-PASSKEY")
    globex_passkey_hash = hash_passkey("GLOBEX-2026-PASSKEY")

    companies = [
        {
            "_id": "comp_acme_01",
            "name": "Acme Corporation",
            "domain": "acme.com",
            "passkey_hash": acme_passkey_hash,
            "passkey_expires_at": None,
            "is_passkey_revoked": False,
            "failed_passkey_attempts": 0,
            "subscription_tier": "enterprise",
            "work_schedule": {
                "work_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                "standard_hours_per_day": 8.0
            },
            "ai_monthly_budget_usd": 250.0,
            "created_at": now,
            "updated_at": now
        },
        {
            "_id": "comp_globex_02",
            "name": "Globex Corporation",
            "domain": "globex.com",
            "passkey_hash": globex_passkey_hash,
            "passkey_expires_at": None,
            "is_passkey_revoked": False,
            "failed_passkey_attempts": 0,
            "subscription_tier": "pro",
            "work_schedule": {
                "work_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                "standard_hours_per_day": 8.0
            },
            "ai_monthly_budget_usd": 100.0,
            "created_at": now,
            "updated_at": now
        }
    ]
    await db.companies.insert_many(companies)
    logger.info("Seeded 2 multi-tenant companies with Argon2id passkeys.")

    # 3. Seed Users & Employees for Acme Corp
    pw_hash = hash_password("Password123!")

    # Acme Manager (CEO / Top Executive)
    acme_mgr_user = {
        "_id": "usr_acme_mgr_01",
        "company_id": "comp_acme_01",
        "email": "sarah.manager@acme.com",
        "password_hash": pw_hash,
        "role": "manager",
        "token_version": 1,
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }
    acme_mgr_emp = {
        "_id": "emp_acme_mgr_01",
        "company_id": "comp_acme_01",
        "user_id": "usr_acme_mgr_01",
        "first_name": "Sarah",
        "last_name": "Manager",
        "designation": "Engineering Director",
        "department": "Engineering",
        "manager_id": None,  # Top executive
        "join_date": "2023-01-15",
        "employment_type": "full_time",
        "status": "active",
        "created_at": now,
        "updated_at": now
    }

    # Acme Employee
    acme_emp_user = {
        "_id": "usr_acme_emp_01",
        "company_id": "comp_acme_01",
        "email": "aarav.sharma@acme.com",
        "password_hash": pw_hash,
        "role": "employee",
        "token_version": 1,
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }
    acme_emp_emp = {
        "_id": "emp_acme_emp_01",
        "company_id": "comp_acme_01",
        "user_id": "usr_acme_emp_01",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "designation": "Senior Software Engineer",
        "department": "Engineering",
        "manager_id": "usr_acme_mgr_01",  # Same-tenant manager
        "join_date": "2024-03-15",
        "employment_type": "full_time",
        "status": "active",
        "created_at": now,
        "updated_at": now
    }

    # Globex Employee (Company B Tenant)
    globex_emp_user = {
        "_id": "usr_globex_emp_01",
        "company_id": "comp_globex_02",
        "email": "john.doe@globex.com",
        "password_hash": pw_hash,
        "role": "employee",
        "token_version": 1,
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }
    globex_emp_emp = {
        "_id": "emp_globex_emp_01",
        "company_id": "comp_globex_02",
        "user_id": "usr_globex_emp_01",
        "first_name": "John",
        "last_name": "Doe",
        "designation": "Product Manager",
        "department": "Product",
        "manager_id": None,
        "join_date": "2024-01-10",
        "employment_type": "full_time",
        "status": "active",
        "created_at": now,
        "updated_at": now
    }

    await db.users.insert_many([acme_mgr_user, acme_emp_user, globex_emp_user])
    await db.employees.insert_many([acme_mgr_emp, acme_emp_emp, globex_emp_emp])
    logger.info("Seeded users & employee profiles.")

    # 4. Seed Leave Balances for 2026
    leave_balances = [
        {
            "_id": "bal_acme_emp_01_2026",
            "company_id": "comp_acme_01",
            "user_id": "usr_acme_emp_01",
            "year": 2026,
            "balances": {
                "annual": {"allocated": 18, "used": 2, "pending": 0},
                "sick": {"allocated": 12, "used": 0, "pending": 0},
                "casual": {"allocated": 6, "used": 1, "pending": 0}
            },
            "updated_at": now
        },
        {
            "_id": "bal_globex_emp_01_2026",
            "company_id": "comp_globex_02",
            "user_id": "usr_globex_emp_01",
            "year": 2026,
            "balances": {
                "annual": {"allocated": 15, "used": 0, "pending": 0},
                "sick": {"allocated": 10, "used": 0, "pending": 0},
                "casual": {"allocated": 5, "used": 0, "pending": 0}
            },
            "updated_at": now
        }
    ]
    await db.leave_balances.insert_many(leave_balances)
    logger.info("Seeded leave balance records.")

    # 5. Seed Policy Documents & Versions
    policy_doc = {
        "_id": "pol_acme_leave_2026",
        "company_id": "comp_acme_01",
        "title": "Acme Employee Leave Policy 2026",
        "category": "leave_benefits",
        "active_version": 1,
        "access_scope": ["employee", "manager", "hr_admin"],
        "department_scope": ["ALL"],
        "created_by": "usr_acme_mgr_01",
        "created_at": now
    }
    policy_ver = {
        "_id": "pol_ver_acme_leave_v1",
        "company_id": "comp_acme_01",
        "policy_id": "pol_acme_leave_2026",
        "version_number": 1,
        "status": "active",
        "storage_key": "comp_acme_01/policies/leave_policy_v1.pdf",
        "file_name": "leave_policy_v1.pdf",
        "file_size_bytes": 512000,
        "mime_type": "application/pdf",
        "chunk_count": 8,
        "published_at": now
    }
    await db.policy_documents.insert_one(policy_doc)
    await db.policy_versions.insert_one(policy_ver)
    logger.info("Seeded Acme leave policy document & version v1.")

    logger.info("Phase 1 seed data population COMPLETE.")


if __name__ == "__main__":
    asyncio.run(seed_phase1_data())
