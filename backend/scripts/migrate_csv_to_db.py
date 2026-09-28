"""
migrate_csv_to_db.py — Migrate and Sync Employee Data from CSV into MongoDB

Resolves the architectural issue where employee operational data was stored as a static
file in the codebase (backend/data/employee_data_sample.csv) instead of in the database.

Populates/Syncs:
1. `db.users`: adds skills, certifications, experience, performance rating, phone, exact leave balances.
2. `db.employees`: canonical Phase 1 System-of-Record employee profiles.
3. `db.attendance`: daily attendance records (date, check-in, check-out, hours worked, location, status).
4. `db.leave_balances`: canonical leave balance records (allocated, used, pending, available).

Usage:
    python backend/scripts/migrate_csv_to_db.py
    python backend/scripts/migrate_csv_to_db.py --file backend/data/employee_data_sample.csv
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import get_db, ensure_indexes
from app.auth import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("csv_migration")


def parse_csv_line(line: str) -> Dict[str, Any]:
    """Parse a single 37-column tab-separated or comma-separated row."""
    # Detect delimiter
    if "\t" in line:
        parts = [p.strip() for p in line.split("\t")]
    else:
        parts = [p.strip() for p in line.split(",")]

    if len(parts) < 30:
        return {}

    def safe_float(val: str, default: float = 0.0) -> float:
        try:
            return float(val.strip())
        except (ValueError, TypeError):
            return default

    def safe_int(val: str, default: int = 0) -> int:
        try:
            return int(float(val.strip()))
        except (ValueError, TypeError):
            return default

    # 1: EMP ID, 2: First Name, 3: Last Name, 4: Email, 5: Phone
    emp_id = parts[0]
    first_name = parts[1]
    last_name = parts[2]
    email = parts[3].lower()
    phone = parts[4]

    # 6: Department, 7: Role/Designation, 8: Manager Name, 9: Location, 10: Work Mode
    department = parts[5]
    designation = parts[6]
    manager_name = parts[7]
    office_location = parts[8]
    work_mode = parts[9]

    # 11: Status, 12: Years with Company, 13: Performance Rating, 14: Skills, 15: Certs
    status = parts[10]
    years_with_company = safe_float(parts[11], 1.0)
    performance_rating = safe_float(parts[12], 4.0)
    skills = [s.strip() for s in parts[13].split(";") if s.strip()] if len(parts) > 13 else []
    certifications = [c.strip() for c in parts[14].split(";") if c.strip()] if len(parts) > 14 else []

    # 16: Att Date, 17: Check-in, 18: Check-out, 19: Att Status, 20: Hours Worked, 21: Att Location
    att_date = parts[15] if len(parts) > 15 and parts[15] else "2026-06-19"
    check_in = parts[16] if len(parts) > 16 else ""
    check_out = parts[17] if len(parts) > 17 else ""
    att_status = parts[18] if len(parts) > 18 and parts[18] else "Present"
    hours_worked = safe_float(parts[19], 8.0) if len(parts) > 19 else 8.0
    att_location = parts[20] if len(parts) > 20 and parts[20] else office_location

    # Leave Balances
    # 22: CL Alloc, 23: CL Used, 24: CL Rem
    # 25: SL Alloc, 26: SL Used, 27: SL Rem
    # 28: PL Alloc, 29: PL Used, 30: PL Rem
    # 31: FL Alloc, 32: FL Used, 33: FL Rem
    cl_alloc = safe_int(parts[21], 12) if len(parts) > 21 else 12
    cl_used = safe_int(parts[22], 0) if len(parts) > 22 else 0
    cl_rem = safe_int(parts[23], max(0, cl_alloc - cl_used)) if len(parts) > 23 else max(0, cl_alloc - cl_used)

    sl_alloc = safe_int(parts[24], 10) if len(parts) > 24 else 10
    sl_used = safe_int(parts[25], 0) if len(parts) > 25 else 0
    sl_rem = safe_int(parts[26], max(0, sl_alloc - sl_used)) if len(parts) > 26 else max(0, sl_alloc - sl_used)

    pl_alloc = safe_int(parts[27], 18) if len(parts) > 27 else 18
    pl_used = safe_int(parts[28], 0) if len(parts) > 28 else 0
    pl_rem = safe_int(parts[29], max(0, pl_alloc - pl_used)) if len(parts) > 29 else max(0, pl_alloc - pl_used)

    fl_alloc = safe_int(parts[30], 3) if len(parts) > 30 else 3
    fl_used = safe_int(parts[31], 0) if len(parts) > 31 else 0
    fl_rem = safe_int(parts[32], max(0, fl_alloc - fl_used)) if len(parts) > 32 else max(0, fl_alloc - fl_used)

    # 34: On Leave, 35: Leave End Date, 36: Leave Type, 37: Remarks
    on_leave = parts[33] if len(parts) > 33 else "No"
    leave_end_date = parts[34] if len(parts) > 34 else ""
    leave_type = parts[35] if len(parts) > 35 else ""
    remarks = parts[36] if len(parts) > 36 else ""

    return {
        "employee_id": emp_id,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": f"{first_name} {last_name}",
        "email": email,
        "phone": phone,
        "department": department,
        "designation": designation,
        "manager_name": manager_name,
        "office_location": office_location,
        "work_mode": work_mode,
        "status": status,
        "years_with_company": years_with_company,
        "performance_rating": performance_rating,
        "skills": skills,
        "certifications": certifications,
        "att_date": att_date,
        "check_in": check_in,
        "check_out": check_out,
        "att_status": att_status,
        "hours_worked": hours_worked,
        "att_location": att_location,
        "casual_leave": {"allocated": cl_alloc, "used": cl_used, "remaining": cl_rem},
        "sick_leave": {"allocated": sl_alloc, "used": sl_used, "remaining": sl_rem},
        "privilege_leave": {"allocated": pl_alloc, "used": pl_used, "remaining": pl_rem},
        "floating_holiday": {"allocated": fl_alloc, "used": fl_used, "remaining": fl_rem},
        "on_leave": on_leave,
        "leave_end_date": leave_end_date,
        "leave_type": leave_type,
        "remarks": remarks,
    }


async def migrate_csv(file_path: str):
    if not os.path.exists(file_path):
        logger.error(f"CSV file not found: {file_path}")
        return

    logger.info(f"Opening CSV source: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    rows = []
    for line in lines:
        row = parse_csv_line(line)
        if row and row.get("email"):
            rows.append(row)

    logger.info(f"Parsed {len(rows)} employee rows from CSV.")
    if not rows:
        logger.warning("No valid rows parsed.")
        return

    db = get_db()
    await ensure_indexes()
    now_iso = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)

    # 1. Determine company_id to associate these employees with
    # Check if existing smartnavigator users have a company_id
    sample_user = await db.users.find_one({"email": rows[0]["email"]})
    company_id = None
    if sample_user:
        company_id = sample_user.get("company_id") or sample_user.get("companyId")

    if not company_id:
        # Fallback to existing company or create one
        comp = await db.companies.find_one({"name": {"$in": ["Smart Navigator", "Nanda_ai", "Glitch"]}})
        if comp:
            company_id = str(comp["_id"])
        else:
            first_comp = await db.companies.find_one({})
            if first_comp:
                company_id = str(first_comp["_id"])
            else:
                company_id = "comp_smartnavigator_01"
                await db.companies.insert_one({
                    "_id": company_id,
                    "name": "Smart Navigator",
                    "domain": "smartnavigator.com",
                    "passkey": "SMARTNAV2026",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                })

    logger.info(f"Associating employees with company_id: {company_id}")

    default_password_hash = hash_password("SmartNav2026!")

    stats = {
        "users_upserted": 0,
        "employees_upserted": 0,
        "attendance_upserted": 0,
        "leave_balances_upserted": 0,
    }

    for row in rows:
        email = row["email"]
        emp_id = row["employee_id"]

        # ----------------------------------------------------
        # 1. Upsert db.users
        # ----------------------------------------------------
        existing_user = await db.users.find_one({"email": email})
        user_id = str(existing_user["_id"]) if existing_user else f"usr_{emp_id.lower()}"

        user_doc_update = {
            "company_id": company_id,
            "companyId": company_id,
            "email": email,
            "fullName": row["full_name"],
            "full_name": row["full_name"],
            "role": "employee",
            "jobTitle": row["designation"],
            "job_title": row["designation"],
            "designation": row["designation"],
            "department": row["department"],
            "employeeId": emp_id,
            "employee_id": emp_id,
            "phone": row["phone"],
            "managerName": row["manager_name"],
            "manager_name": row["manager_name"],
            "officeLocation": row["office_location"],
            "office_location": row["office_location"],
            "workMode": row["work_mode"],
            "work_mode": row["work_mode"],
            "employmentStatus": row["status"],
            "is_active": True,
            "isActive": True,
            "years_with_company": row["years_with_company"],
            "performance_rating": row["performance_rating"],
            "skills": row["skills"],
            "certifications": row["certifications"],
            "date_of_joining": "2024-01-15",
            "updated_at": now_iso,
            "updatedAt": now_iso,
            # Legacy summary dictionary for existing UI
            "leave_balance": {
                "casual_leave_total": row["casual_leave"]["allocated"],
                "casual_leave_used": row["casual_leave"]["used"],
                "casual_leave_remaining": row["casual_leave"]["remaining"],
                "sick_leave_total": row["sick_leave"]["allocated"],
                "sick_leave_used": row["sick_leave"]["used"],
                "sick_leave_remaining": row["sick_leave"]["remaining"],
                "privilege_leave_total": row["privilege_leave"]["allocated"],
                "privilege_leave_used": row["privilege_leave"]["used"],
                "privilege_leave_remaining": row["privilege_leave"]["remaining"],
                "floating_holidays_total": row["floating_holiday"]["allocated"],
                "floating_holidays_used": row["floating_holiday"]["used"],
                "floating_holidays_remaining": row["floating_holiday"]["remaining"],
            },
            # Canonical atomic dictionary for Stage 1.3 / Phase 1
            "leave_balances": {
                "casual_leave": {
                    "allocated": row["casual_leave"]["allocated"],
                    "used": row["casual_leave"]["used"],
                    "pending": 0,
                    "available": row["casual_leave"]["remaining"],
                },
                "sick_leave": {
                    "allocated": row["sick_leave"]["allocated"],
                    "used": row["sick_leave"]["used"],
                    "pending": 0,
                    "available": row["sick_leave"]["remaining"],
                },
                "privilege_leave": {
                    "allocated": row["privilege_leave"]["allocated"],
                    "used": row["privilege_leave"]["used"],
                    "pending": 0,
                    "available": row["privilege_leave"]["remaining"],
                },
                "floating_holiday": {
                    "allocated": row["floating_holiday"]["allocated"],
                    "used": row["floating_holiday"]["used"],
                    "pending": 0,
                    "available": row["floating_holiday"]["remaining"],
                },
            },
        }

        if existing_user:
            await db.users.update_one({"_id": existing_user["_id"]}, {"$set": user_doc_update})
        else:
            user_doc_update["_id"] = user_id
            user_doc_update["id"] = user_id
            user_doc_update["passwordHash"] = default_password_hash
            user_doc_update["password_hash"] = default_password_hash
            user_doc_update["tokenVersion"] = 1
            user_doc_update["token_version"] = 1
            user_doc_update["createdAt"] = now_iso
            user_doc_update["created_at"] = now_iso
            await db.users.insert_one(user_doc_update)

        stats["users_upserted"] += 1

        # ----------------------------------------------------
        # 2. Upsert db.employees (Canonical System of Record)
        # ----------------------------------------------------
        emp_record = {
            "company_id": company_id,
            "user_id": user_id,
            "employee_id": emp_id,
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "designation": row["designation"],
            "department": row["department"],
            "manager_name": row["manager_name"],
            "join_date": "2024-01-15",
            "employment_type": "full_time",
            "phone": row["phone"],
            "office_location": row["office_location"],
            "work_mode": row["work_mode"],
            "status": "active",
            "skills": row["skills"],
            "certifications": row["certifications"],
            "updated_at": now_dt,
        }
        await db.employees.update_one(
            {"company_id": company_id, "user_id": user_id},
            {"$set": emp_record, "$setOnInsert": {"_id": f"emp_{emp_id.lower()}", "created_at": now_dt}},
            upsert=True,
        )
        stats["employees_upserted"] += 1

        # ----------------------------------------------------
        # 3. Upsert db.attendance (Real MongoDB Collection)
        # ----------------------------------------------------
        att_record = {
            "company_id": company_id,
            "user_id": user_id,
            "employee_id": emp_id,
            "employee_name": row["full_name"],
            "date": row["att_date"],
            "status": row["att_status"],
            "hours_worked": row["hours_worked"],
            "check_in_time": row["check_in"] or ("09:00" if row["att_status"] == "Present" else ""),
            "check_out_time": row["check_out"] or ("17:30" if row["att_status"] == "Present" else ""),
            "location": row["att_location"],
            "remarks": row["remarks"],
            "updated_at": now_iso,
        }
        att_id = f"att_{emp_id.lower()}_{row['att_date']}"
        await db.attendance.update_one(
            {"company_id": company_id, "user_id": user_id, "date": row["att_date"]},
            {"$set": att_record, "$setOnInsert": {"_id": att_id, "created_at": now_iso}},
            upsert=True,
        )
        stats["attendance_upserted"] += 1

        # ----------------------------------------------------
        # 4. Upsert db.leave_balances (Canonical 2026 record)
        # ----------------------------------------------------
        lb_record = {
            "company_id": company_id,
            "user_id": user_id,
            "year": 2026,
            "balances": {
                "casual": {
                    "allocated": row["casual_leave"]["allocated"],
                    "used": row["casual_leave"]["used"],
                    "pending": 0,
                    "available": row["casual_leave"]["remaining"],
                },
                "sick": {
                    "allocated": row["sick_leave"]["allocated"],
                    "used": row["sick_leave"]["used"],
                    "pending": 0,
                    "available": row["sick_leave"]["remaining"],
                },
                "privilege": {
                    "allocated": row["privilege_leave"]["allocated"],
                    "used": row["privilege_leave"]["used"],
                    "pending": 0,
                    "available": row["privilege_leave"]["remaining"],
                },
                "floating": {
                    "allocated": row["floating_holiday"]["allocated"],
                    "used": row["floating_holiday"]["used"],
                    "pending": 0,
                    "available": row["floating_holiday"]["remaining"],
                },
            },
            "updated_at": now_dt,
        }
        lb_id = f"lb_{company_id}_{user_id}_2026"
        await db.leave_balances.update_one(
            {"company_id": company_id, "user_id": user_id, "year": 2026},
            {"$set": lb_record, "$setOnInsert": {"_id": lb_id, "created_at": now_dt}},
            upsert=True,
        )
        stats["leave_balances_upserted"] += 1

    logger.info("=== CSV MIGRATION TO DATABASE COMPLETED ===")
    logger.info(f"Users upserted:          {stats['users_upserted']}")
    logger.info(f"Employees upserted:      {stats['employees_upserted']}")
    logger.info(f"Attendance upserted:     {stats['attendance_upserted']}")
    logger.info(f"Leave balances upserted: {stats['leave_balances_upserted']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate employee CSV to MongoDB")
    parser.add_argument(
        "--file",
        required=True,
        help="Path to employee data CSV/TSV file to import into MongoDB",
    )
    args = parser.parse_args()
    asyncio.run(migrate_csv(args.file))
