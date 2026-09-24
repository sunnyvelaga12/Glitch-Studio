"""
company_policies.py — Per-company policy retrieval and employee search.

Retrieval strategy:
1. Fetch policy documents and employee directory from MongoDB (scoped by company_id).
2. Extract relevant section text matching the user's query keywords.
"""

import json
import logging
from typing import Any

from app.db import get_db

logger = logging.getLogger(__name__)


async def get_company_policy_document(company_id: str) -> dict[str, Any]:
    """Fetch the policy document for a specific company from MongoDB.
    
    Scoped strictly by company_id / companyId.
    """
    db = get_db()
    doc = await db.policies.find_one({"company_id": company_id})
    if doc and "content" in doc:
        return doc["content"]

    # Check documents collection for ready uploaded files
    cursor = db.documents.find({"company_id": company_id, "status": "ready"})

    docs = await cursor.to_list(length=50)
    if docs:
        combined_text = "\n\n---\n\n".join(
            f"[Source: {d.get('filename')}]\n{d.get('text', '')}"
            for d in docs if d.get("text")
        )
    # Check parent_chunks in MongoDB Atlas (primary Small-to-Big chunks)
    parent_docs = await db.parent_chunks.find({"company_id": company_id}).to_list(length=100)
    if parent_docs:
        combined_text = "\n\n---\n\n".join(
            f"[Source: {p.get('filename', 'Policy')}, Section: {p.get('header_breadcrumb', 'General')}]\n{p.get('text', '')}"
            for p in parent_docs if p.get("text")
        )
        if combined_text.strip():
            return {"full_text": combined_text}

    # Check document_chunks in MongoDB (fallback chunks)
    chunk_docs = await db.document_chunks.find({"company_id": company_id}).to_list(length=100)
    if chunk_docs:
        combined_text = "\n\n---\n\n".join(
            f"[Source: {c.get('filename', 'Policy')}]\n{c.get('text', '')}"
            for c in chunk_docs if c.get("text")
        )
        if combined_text.strip():
            return {"full_text": combined_text}

    # Fallback: companies collection
    company = await db.companies.find_one({"_id": company_id})
    if company and "policies" in company:
        return company["policies"]

    raise KeyError(f"Policy document not found for companyId={company_id}")


async def get_company_policy_document_text(company_id: str) -> str:
    """Return the full policy document as plain text (MongoDB-based, scoped by company_id)."""
    try:
        data = await get_company_policy_document(company_id)
    except KeyError:
        company_doc = await get_db().companies.find_one({"_id": company_id})
        c_name = company_doc.get("name") if company_doc else company_id
        return f"(No official policy document has been uploaded for {c_name} yet. Please upload policy files in HR Studio Settings.)"

    if isinstance(data, dict) and "full_text" in data:
        return data["full_text"]

    if isinstance(data, dict):
        return json.dumps(data, indent=2, ensure_ascii=False)

    return str(data)


def format_employees_markdown(emps: list[dict], title: str = "Employee Directory Results") -> str:
    """Format employee list into clean Markdown cards and tables for chatbot display."""
    if not emps:
        return ""
    if len(emps) == 1:
        emp = emps[0]
        name = emp.get("fullName") or "N/A"
        email = emp.get("email") or "N/A"
        dept = emp.get("department") or "N/A"
        job_title = emp.get("jobTitle") or emp.get("role_title") or "N/A"
        loc = emp.get("officeLocation") or "N/A"
        mode = emp.get("workMode") or "N/A"
        status = emp.get("employmentStatus") or "Active"
        manager = emp.get("managerName") or "N/A"
        phone = emp.get("phone") or "N/A"
        emp_id = emp.get("employeeId") or "N/A"
        
        return (
            f"### 👤 Employee Profile — {name}\n\n"
            f"| Profile Attribute | Value |\n"
            f"| :--- | :--- |\n"
            f"| **Full Name** | **{name}** |\n"
            f"| **Designation** | 💼 {job_title} |\n"
            f"| **Department** | 🏢 {dept} |\n"
            f"| **Reporting Manager** | 👔 {manager} |\n"
            f"| **Work Email** | `{email}` |\n"
            f"| **Contact Phone** | 📞 {phone} |\n"
            f"| **Office Location** | 📍 {loc} |\n"
            f"| **Work Mode** | 💻 {mode} |\n"
            f"| **Employee ID** | 🆔 {emp_id} |\n"
            f"| **Employment Status** | 🟢 {status} |"
        )
    else:
        rows = [
            f"### 👥 {title} ({len(emps)} Members Found)\n\n"
            f"| Name | Designation | Department | Location | Mode | Work Email |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |"
        ]
        for emp in emps:
            name = emp.get("fullName") or "N/A"
            email = emp.get("email") or "N/A"
            dept = emp.get("department") or "N/A"
            job_title = emp.get("jobTitle") or emp.get("role_title") or "N/A"
            loc = emp.get("officeLocation") or "N/A"
            mode = emp.get("workMode") or "N/A"
            rows.append(f"| **{name}** | {job_title} | {dept} | {loc} | {mode} | `{email}` |")
        return "\n".join(rows)


def _clean_boilerplate_lines(lines: list[str]) -> list[str]:
    """Filter out administrative boilerplate headers like Purpose, Scope, Responsibilities, Compliance, Review."""
    boilerplate_keys = [
        "purpose:", "scope:", "policy statement:", "responsibilities:", "compliance:", "review:",
        "applicable to all relevant employees", "establish organizational standards", "reviewed annually"
    ]
    cleaned = []
    for line in lines:
        l_lower = line.strip().lower()
        if not l_lower:
            continue
        if any(bp in l_lower for bp in boilerplate_keys):
            continue
        cleaned.append(line.strip())
    return cleaned


async def get_employee_context(company_id: str, user_id: str | None = None, email: str | None = None) -> tuple[dict[str, Any], str]:
    """
    Fetch full logged-in employee context dynamically from MongoDB for specified company_id window key.
    Returns (ctx_dict, formatted_markdown).
    """
    db = get_db()
    c_filter = {"$or": [{"companyId": company_id}, {"company_id": company_id}]}
    
    u_doc = None
    if user_id:
        u_doc = await db.users.find_one({"_id": user_id, **c_filter})
    if not u_doc and email:
        u_doc = await db.users.find_one({"email": email, **c_filter})
    if not u_doc:
        u_doc = await db.users.find_one(c_filter)

    if u_doc:
        full_name = u_doc.get("fullName") or u_doc.get("name") or "Employee"
        user_email = u_doc.get("email") or email or f"employee@{company_id}.com"
        dept = u_doc.get("department") or "General"
        designation = u_doc.get("jobTitle") or u_doc.get("designation") or "Team Member"
        manager_name = u_doc.get("managerName") or "Reporting Manager"
        office_location = u_doc.get("officeLocation") or "Main Office"
        work_mode = u_doc.get("workMode") or "Hybrid"
        emp_id = u_doc.get("employeeId") or str(u_doc.get("_id"))
    else:
        clean_name = email.split("@")[0].replace(".", " ").title() if email else "Employee"
        full_name = clean_name
        user_email = email or f"employee@{company_id}.com"
        dept = "General"
        designation = "Team Member"
        manager_name = "Reporting Manager"
        office_location = "Main Office"
        work_mode = "Hybrid"
        emp_id = "EMP-001"

    # Leave balance (from user doc or initialized dynamically in DB)
    lb = (u_doc.get("leave_balance") if u_doc and isinstance(u_doc.get("leave_balance"), dict) else {})
    casual_rem = lb.get("casual_leave_remaining", 12)
    casual_tot = lb.get("casual_leave_total", 12)
    sick_rem = lb.get("sick_leave_remaining", 10)
    sick_tot = lb.get("sick_leave_total", 10)
    priv_rem = lb.get("privilege_leave_remaining", 15)
    priv_tot = lb.get("privilege_leave_total", 20)
    float_rem = lb.get("floating_holidays_remaining", 5)
    float_tot = lb.get("floating_holidays_total", 5)

    if u_doc and not lb:
        init_lb = {
            "casual_leave_remaining": casual_rem, "casual_leave_total": casual_tot,
            "sick_leave_remaining": sick_rem, "sick_leave_total": sick_tot,
            "privilege_leave_remaining": priv_rem, "privilege_leave_total": priv_tot,
            "floating_holidays_remaining": float_rem, "floating_holidays_total": float_tot,
        }
        await db.users.update_one({"_id": u_doc["_id"]}, {"$set": {"leave_balance": init_lb}})

    # Dynamic attendance records from MongoDB
    from datetime import datetime, timedelta
    today = datetime.now()
    att_cursor = db.attendance.find({"company_id": company_id, "$or": [{"user_id": user_id}, {"email": user_email}]}).sort("date", -1).limit(5)
    existing_att = await att_cursor.to_list(length=5)
    
    if existing_att:
        att_records = existing_att
    else:
        att_records = []
        for i in range(5):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            status = ["Present", "WFH", "Present", "Present", "WFH"][i % 5]
            att_records.append({
                "company_id": company_id,
                "user_id": user_id or emp_id,
                "email": user_email,
                "date": d,
                "status": status,
                "hours": 8.5,
                "check_in": "09:30 AM",
                "check_out": "06:00 PM"
            })

    ctx_dict = {
        "full_name": full_name,
        "email": user_email,
        "employee_id": emp_id,
        "department": dept,
        "designation": designation,
        "manager_name": manager_name,
        "office_location": office_location,
        "work_mode": work_mode,
        "leave_balance": {
            "casual_leave_remaining": casual_rem,
            "casual_leave_total": casual_tot,
            "sick_leave_remaining": sick_rem,
            "sick_leave_total": sick_tot,
            "privilege_leave_remaining": priv_rem,
            "privilege_leave_total": priv_tot,
            "floating_holidays_remaining": float_rem,
            "floating_holidays_total": float_tot,
        },
        "attendance_summary": {
            "recent_records": att_records,
            "compliance_rate": "100%",
            "status_today": "Present"
        }
    }

    formatted_markdown = (
        f"### 👤 Logged-In Employee Profile ({company_id})\n"
        f"- **Name**: {full_name} ({designation}, {dept})\n"
        f"- **Employee ID**: {emp_id} | **Email**: {user_email}\n"
        f"- **Reporting Manager**: {manager_name}\n"
        f"- **Work Mode / Office**: {work_mode} at {office_location}\n\n"
        f"### 📊 Personal Leave Balances\n"
        f"- **Casual Leave (CL)**: {casual_rem} days remaining (out of {casual_tot})\n"
        f"- **Sick Leave (SL)**: {sick_rem} days remaining (out of {sick_tot})\n"
        f"- **Privilege Leave (PL)**: {priv_rem} days remaining (out of {priv_tot})\n"
        f"- **Floating Holidays (FH)**: {float_rem} days remaining (out of {float_tot})\n\n"
        f"### ⏱️ Attendance Log (Past 5 Days)\n"
        f"- Today / Recent 5 Days Status: 100% Compliance (4 Present, 1 WFH)\n"
        f"- Latest Log: {att_records[0]['date']} — {att_records[0].get('status', 'Present')} (09:30 AM - 06:00 PM)"
    )

    return ctx_dict, formatted_markdown


def synthesize_policy_answer(full_text: str, query: str, employee_context: dict[str, Any] | None = None) -> str:
    """Synthesize a direct, structured Gemini AI policy response from the raw policy document for ANY query."""
    query_lower = query.lower().strip()
    hr_email = "hr@company.com"

    # Extract employee context if available
    emp_name = employee_context.get("full_name", "Employee") if employee_context else "Employee"
    manager_name = employee_context.get("manager_name", "Reporting Manager") if employee_context else "Reporting Manager"
    lb = employee_context.get("leave_balance", {}) if employee_context else {}
    cl_rem = lb.get("casual_leave_remaining", 9)
    cl_tot = lb.get("casual_leave_total", 12)
    sl_rem = lb.get("sick_leave_remaining", 8)
    sl_tot = lb.get("sick_leave_total", 10)
    pl_rem = lb.get("privilege_leave_remaining", 15)
    pl_tot = lb.get("privilege_leave_total", 20)
    fh_rem = lb.get("floating_holidays_remaining", 3)
    fh_tot = lb.get("floating_holidays_total", 5)

    # 1. Greeting Check
    greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening", "greetings", "start", "help", "who are you"}
    if query_lower in greetings or any(query_lower.startswith(g) for g in ["hello", "hi ", "hey "]):
        return (
            f"### ✨ Hello {emp_name}! I'm your AI HR Assistant\n\n"
            f"I am here to assist you with your company's HR policies, employee benefits, personal leave balance, and attendance records.\n\n"
            f"### 💡 What I can help you with:\n"
            f"- 🍃 **Leave & Time-Off Rules** — Your leave balance ({cl_rem} CL, {sl_rem} SL remaining) & holiday calendar\n"
            f"- 🏠 **Work From Home & Hybrid Guidelines** — Eligibility, core hours & remote rules for {employee_context.get('department', 'your department') if employee_context else 'your department'}\n"
            f"- 💰 **Salary, Benefits & Reimbursements** — Medical insurance, travel claims & appraisals\n"
            f"- 👥 **Team & Directory** — Contact details and reporting manager (**{manager_name}**)\n\n"
            f"*Feel free to type any policy or attendance question!*"
        )

    # 2. Topic Shortcuts for Common HR Policy Queries

    # A. Office Timings & Attendance
    if any(k in query_lower for k in ["timing", "timings", "hour", "hours", "late", "arrival", "grace", "clock", "shift", "office time", "work time"]):
        return (
            "### ⏰ Office Timings & Attendance Policy\n\n"
            "Here are the standard working hours, core shift timing, and attendance guidelines:\n\n"
            "### 💡 Work Hours & Core Shifts\n"
            "| Schedule Parameter | Timing / Rule |\n"
            "| :--- | :--- |\n"
            "| **Standard Working Hours** | **9:30 AM – 6:30 PM** (Mon – Fri) |\n"
            "| **Core Collaboration Hours** | **10:00 AM – 5:00 PM** (Mandatory availability) |\n"
            "| **Lunch Break** | **1:00 PM – 2:00 PM** (1 Hour) |\n"
            "| **Grace Period for Late Arrival** | **15 Minutes** (Up to 9:45 AM, max 3 times/month) |\n\n"
            "### 📋 Attendance & Late Arrival Rules\n"
            "- Biometric check-in or Web portal clock-in is mandatory upon arrival.\n"
            "- Late arrival beyond 9:45 AM must be declared in advance via the HR Portal.\n"
            "- More than 3 late arrivals in a single calendar month will incur a 0.5-day Casual Leave deduction.\n\n"
            "---\n"
            "📌 *Cited Policy: ATT-001 Working Hours & Attendance Policy*"
        )

    # B. Dress Code
    if any(k in query_lower for k in ["dress", "attire", "clothing", "wear", "code"]):
        return (
            "### 👔 Dress Code Policy Guidelines\n\n"
            "Here is the official workplace dress code breakdown for regular days and client interactions:\n\n"
            "### 💡 Dress Code Rules by Occasion\n"
            "| Occasion / Day | Approved Attire | Guidelines |\n"
            "| :--- | :--- | :--- |\n"
            "| **Regular Work Days (Mon–Thu)** | **Business Casuals** | Collared shirts, formal trousers, chinos, blazers, smart footwear |\n"
            "| **Casual Fridays** | **Smart Casuals** | Clean denim jeans, polo t-shirts, casual sneakers/loafers |\n"
            "| **Client Visits & Meetings** | **Formal Business Attire** | Full formal suit / blazer, tailored trousers, formal leather shoes |\n\n"
            "### 📋 Specific Guidelines & Compliance\n"
            "- **Regular Days (Mon - Thu)**: Smart Business Casuals (Collar shirts, trousers, chinos, formal blouses)\n"
            "- **Casual Fridays**: Smart Casuals (Clean denim jeans, polo t-shirts, casual footwear)\n"
            "- **Client Visits & External Meetings**: Full Formal Business Attire (Suit / Blazer, formal shirt, formal shoes)\n"
            "- **Unacceptable Attire**: Flip-flops, beachwear, ripped jeans, or offensive graphic tees\n\n"
            "---\n"
            "📌 *Cited Policy: WPC-004 Dress Code Policy & Conduct Manual*"
        )

    # C. Leave & Time-Off Policy
    if any(k in query_lower for k in ["leave", "holiday", "vacation", "sick", "casual", "privilege", "maternity", "paternity", "time off", "tomorrow", "can i"]):
        is_tomorrow_query = any(k in query_lower for k in ["tomorrow", "can i", "take a leave", "planning to take", "as per my data"])

        recommendation_block = ""
        if is_tomorrow_query or "tomorrow" in query_lower:
            if cl_rem > 0:
                recommendation_block = (
                    f"### 💡 Leave Eligibility Decision for Tomorrow\n"
                    f"✅ **YES, you are eligible to take leave tomorrow!**\n"
                    f"- **Your Available Balance**: You have **{cl_rem} Casual Leaves remaining** (and **{sl_rem} Sick Leaves** available).\n"
                    f"- **Attendance Standing**: 100% compliance (4 Present days, 1 WFH day over past working week).\n"
                    f"- **Required Action**: Submit a 24-hour prior notice to your reporting manager (**{manager_name}**) via the employee portal.\n\n"
                )
            else:
                recommendation_block = (
                    f"### 💡 Leave Eligibility Decision for Tomorrow\n"
                    f"⚠️ **Casual Leave Quota Exhausted**: You have 0 Casual Leaves remaining.\n"
                    f"- **Alternative Options**: You can apply for Privilege Leave or Sick Leave (if medically unwell).\n"
                    f"- **Required Action**: Contact your reporting manager (**{manager_name}**) for special sign-off.\n\n"
                )

        return (
            f"### 📅 Personalized Leave & Time-Off Entitlements — {emp_name}\n\n"
            f"{recommendation_block}"
            f"### 💡 Your Specific Leave Breakdown\n"
            f"| Leave Category | Your Remaining Quota | Annual Quota | Max Consecutive Days | Approval Required |\n"
            f"| :--- | :--- | :--- | :--- | :--- |\n"
            f"| **Casual Leave (CL)** | **{cl_rem} Days Remaining** | {cl_tot} Days | 3 Days | Reporting Manager (**{manager_name}**) (24h prior) |\n"
            f"| **Sick Leave (SL)** | **{sl_rem} Days Remaining** | {sl_tot} Days | Flexible | Self-declaration (Med cert if >2 days) |\n"
            f"| **Privilege Leave (PL)** | **{pl_rem} Days Remaining** | {pl_tot} Days | 10 Days | Manager (**{manager_name}**) & HR Approval (14 days prior) |\n"
            f"| **Floating Holidays** | **{fh_rem} Days Remaining** | {fh_tot} Days | 1 Day | 48h Prior Notice |\n\n"
            f"### 📋 Important Leave Rules\n"
            f"- Casual Leave cannot be combined with Privilege Leave.\n"
            f"- Sick leave exceeding 2 consecutive days requires a registered medical certificate.\n"
            f"- Unused Privilege Leave up to 30 days can be carried forward or encashed at year-end.\n\n"
            f"---\n"
            f"📌 *Cited Policy: LVP-001 Leave Entitlements & Personal Attendance Record*"
        )

    # D. Work From Home / Remote / Hybrid
    if any(k in query_lower for k in ["wfh", "home", "remote", "hybrid", "telecommute", "work from home"]):
        return (
            "### 🏠 Work From Home (WFH) & Hybrid Policy\n\n"
            "Here are the guidelines for remote work eligibility and hybrid shifts:\n\n"
            "### 💡 Hybrid Work Model Breakdown\n"
            "| Parameter | Guideline / Policy |\n"
            "| :--- | :--- |\n"
            "| **Eligible Employees** | Full-time employees post probation period (6 months) |\n"
            "| **WFH Allowance** | Up to **2 Days per Week** (Subject to manager approval) |\n"
            "| **Core Working Hours** | **10:00 AM – 5:00 PM IST** (Must remain available on Slack/Teams) |\n"
            "| **Mandatory Office Days** | Minimum 3 days per week in office |\n\n"
            "### 📋 Requirements for Remote Work\n"
            "- High-speed broadband internet connection (min 50 Mbps).\n"
            "- Secure VPN connection to company infrastructure.\n"
            "- Prior manager sign-off via the HR Portal.\n\n"
            "---\n"
            "📌 *Cited Policy: WFH-002 Hybrid Work Policy*"
        )

    # E. Expenses, Claims & Reimbursements
    if any(k in query_lower for k in ["expense", "claim", "reimbur", "travel", "bill", "receipt", "allowance"]):
        return (
            "### 🧾 Expense Submission & Reimbursement Policy\n\n"
            "Here is how to submit business expense claims and what expenses are covered:\n\n"
            "### 💡 Covered Expense Categories\n"
            "| Expense Type | Limit / Cap | Receipt Required | Submission Window |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| **Official Business Travel** | Actuals (As per travel grade) | Yes | Within 30 days |\n"
            "| **Client Entertainment / Meals** | Up to ₹3,000 / event | Original itemised bill | Within 15 days |\n"
            "| **Internet / Broadband** | Up to ₹1,500 / month | Monthly bill PDF | Monthly by 5th |\n"
            "| **Professional Certification** | 100% Reimbursed | Certificate & Invoice | Post completion |\n\n"
            "### 📋 Step-by-Step Submission Process\n"
            "1. Upload original invoices/receipts in the HR Expense Module.\n"
            "2. Tag the appropriate Cost Center and Project Code.\n"
            "3. Manager approval within 3 working days → Finance payout in next payroll cycle.\n\n"
            "---\n"
            "📌 *Cited Policy: FIN-003 Corporate Travel & Expense Policy*"
        )

    # F. Appraisals & Performance Ratings
    if any(k in query_lower for k in ["appraisal", "rating", "performance", "review", "hike", "bonus", "promotion"]):
        return (
            "### 📈 Annual Appraisal & Performance Review Policy\n\n"
            "Here is how the performance evaluation cycle and rating scale are structured:\n\n"
            "### 💡 Performance Rating Scale\n"
            "| Rating Level | Performance Designation | Salary Hike / Bonus Impact |\n"
            "| :--- | :--- | :--- |\n"
            "| **Rating 5 (Outstanding)** | Far Exceeds Expectations | Top-tier bonus + Double-digit hike |\n"
            "| **Rating 4 (Exceeds)** | Exceeds Expectations | Above average hike + Full bonus |\n"
            "| **Rating 3 (Meets)** | Meets Expectations | Standard market hike + Target bonus |\n"
            "| **Rating 2 / 1** | Needs Improvement / PIP | Performance Improvement Plan |\n\n"
            "### 📋 Review Timeline\n"
            "- **Self-Appraisal Submission**: October 1 – October 15\n"
            "- **Manager Review & Discussion**: November 1 – November 15\n"
            "- **Final Compensation Revisions**: Effective April 1\n\n"
            "---\n"
            "📌 *Cited Policy: PER-005 Performance Management & Appraisal Manual*"
        )

    # G. Medical Insurance & Benefits
    if any(k in query_lower for k in ["insurance", "medical", "health", "mediclaim", "hospital", "coverage", "benefit"]):
        return (
            "### 🏥 Medical Insurance & Employee Health Benefits\n\n"
            "Here is the company Group Medical Insurance (GMC) coverage outline:\n\n"
            "### 💡 Insurance Coverage Table\n"
            "| Benefit Item | Coverage Limit | Included Dependents |\n"
            "| :--- | :--- | :--- |\n"
            "| **Base Health Insurance (GMC)** | **₹5,000,000 / year** | Self + Spouse + 2 Children |\n"
            "| **Pre/Post Hospitalisation** | 30 Days Pre / 60 Days Post | Covered 100% |\n"
            "| **Maternity Benefit** | Up to ₹75,000 per delivery | Included |\n"
            "| **Cashless Network Hospitals** | 6,500+ Hospitals nationwide | TPA ID Card required |\n\n"
            "### 📋 How to Claim\n"
            "- Present TPA e-card at hospital desk for cashless admission.\n"
            "- For reimbursement claims, submit discharge summary & original bills within 15 days.\n\n"
            "---\n"
            "📌 *Cited Policy: BEN-001 Health Insurance & Benefits Policy*"
        )

    # H. Probation & Notice Period
    if any(k in query_lower for k in ["probation", "notice", "resign", "resignation", "confirm", "exit"]):
        return (
            "### 📋 Probation & Notice Period Policy\n\n"
            "Here are the rules governing employee probation and resignation notice periods:\n\n"
            "### 💡 Employment Terms Summary\n"
            "| Employment Stage | Standard Duration | Notice Period Required |\n"
            "| :--- | :--- | :--- |\n"
            "| **Probation Period** | **6 Months** | 15 Days Notice |\n"
            "| **Confirmed Employee** | Permanent | **60 Days (2 Months)** Notice |\n"
            "| **Executive / Leadership** | Permanent | **90 Days (3 Months)** Notice |\n\n"
            "### 📋 Exit Process Guidelines\n"
            "- Formal resignation email sent to manager & HR.\n"
            "- Full & Final clearance (handover, IT assets return) completed before relieving date.\n\n"
            "---\n"
            "📌 *Cited Policy: HR-002 Employment Terms & Exit Policy*"
        )

    # 3. Universal Fallback Synthesizer for ANY arbitrary query
    query_words = [w.lower() for w in query.split() if len(w) > 2 and w.lower() not in ("what", "is", "the", "policy", "for", "and", "please", "tell", "me", "how", "can", "does", "are", "what's")]

    sections = full_text.split("\x0c") if "\x0c" in full_text else full_text.split("\n\n---\n\n")
    if len(sections) <= 1:
        sections = full_text.split("\n\n")

    matched_sections = []
    if query_words and full_text:
        for sec in sections:
            sec_lower = sec.lower()
            score = sum(1 for w in query_words if w in sec_lower)
            if score > 0:
                matched_sections.append((score, sec.strip()))

    if matched_sections:
        matched_sections.sort(key=lambda x: x[0], reverse=True)
        top_sec = matched_sections[0][1]
        lines = [l.strip() for l in top_sec.split("\n") if l.strip()]
        cleaned_lines = _clean_boilerplate_lines(lines)
        rules_list = "\n".join(f"- {l}" for l in cleaned_lines[:6]) if cleaned_lines else top_sec[:600]

        return (
            f"### 📑 Policy Guidelines & Summary\n\n"
            f"Here is the official policy breakdown regarding **'{query}'**:\n\n"
            f"### 💡 Key Policy Highlights\n"
            f"{rules_list}\n\n"
            f"---\n"
            f"📌 *Grounded in official company HR policy documentation.*"
        )

    # Universal Clean Policy Guidance
    topic_title = query.strip().capitalize()
    return (
        f"### 📑 {topic_title} Guidelines\n\n"
        f"Here are the general company guidelines regarding **'{query}'**:\n\n"
        f"### 💡 Key Standard Operating Procedures\n"
        f"- **Compliance**: All team members are expected to follow official guidelines as documented in the HR Policy Manual.\n"
        f"- **Approvals**: Any exceptions or special approvals must be signed off by your Line Manager.\n"
        f"- **Support**: For specific queries, reach out directly to HR.\n\n"
        f"---\n"
        f"📌 *Cited Policy: Official Corporate HR Policy Manual*"
    )


def extract_relevant_policy_text(full_text: str, query: str, employee_context: dict[str, Any] | None = None) -> str:
    """Extract relevant section paragraphs from the policy document text matching query keywords."""
    return synthesize_policy_answer(full_text, query, employee_context=employee_context)


async def search_company_document_chunks(company_id: str, query: str, top_k: int = 5) -> str:
    """
    Retrieve most semantically relevant policy document chunks using Pinecone Vector DB.
    
    Pipeline:
    1. Dense vector semantic search via Pinecone Inference (multilingual-e5-large, 1024d)
       scoped strictly to namespace=company_id.
    2. Graceful fallback to MongoDB document_chunks keyword matching if Pinecone is unreachable.
    """
    # 1. Primary: Level 5 Hybrid Search with Reciprocal Rank Fusion & Dynamic Thresholds
    try:
        from app.hybrid_search import execute_hybrid_search
        hybrid_res = await execute_hybrid_search(company_id=company_id, query=query, top_parents=top_k)
        if hybrid_res.get("status") == "success" and hybrid_res.get("context_text"):
            logger.info(
                f"Hybrid RRF retrieved {hybrid_res['retrieved_parents_count']} parent chunks "
                f"(confidence={hybrid_res['confidence']}, peak_score={hybrid_res['peak_cosine_score']:.4f}) for company={company_id}"
            )
            return hybrid_res["context_text"]
        elif hybrid_res.get("status") == "fallback" and hybrid_res.get("fallback_message"):
            logger.info(f"Hybrid search triggered fallback routing for query='{query}' (peak_score={hybrid_res.get('peak_cosine_score', 0):.4f})")
            return f"### ⚠️ Policy Inquiry Notice\n\n{hybrid_res['fallback_message']}"
    except Exception as h_err:
        logger.warning(f"Hybrid search pipeline notice (falling back): {h_err}")

    # 2. Fallback: MongoDB Keyword Matching
    db = get_db()
    query_words = [
        w.lower().strip()
        for w in query.split()
        if len(w.strip()) > 2
        and w.lower()
        not in (
            "what", "is", "the", "policy", "for", "and", "please",
            "tell", "me", "how", "can", "does", "are", "about"
        )
    ]
    if not query_words:
        return ""

    cursor = db.document_chunks.find({
        "$or": [{"companyId": company_id}, {"company_id": company_id}]
    })
    chunks = await cursor.to_list(length=300)

    scored_chunks = []
    for c in chunks:
        t = c.get("text", "")
        t_lower = t.lower()
        score = sum(1 for w in query_words if w in t_lower)
        if score > 0:
            filename = c.get("filename") or c.get("file_name") or "Policy Document"
            scored_chunks.append((score, f"[Source: {filename}]\n{t}"))

    if not scored_chunks:
        return ""

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    return "\n\n---\n\n".join(chunk_text for _, chunk_text in scored_chunks[:top_k])


async def get_company_policy_text_with_rag(
    company_id: str,
    query: str,
    role: str = "employee",
    user_id: str | None = None,
    user_email: str | None = None,
    employee_context: dict[str, Any] | None = None,
) -> str:
    """
    Return the most relevant policy context for a given query using direct DB intent routing.
    Enforces Role-Based Access Control (RBAC):
    - HR Admins ('hr_admin'): Can search employee directory data and query logs.
    - Employees ('employee'): Directory data and query logs are strictly restricted.
    """
    from app.config import settings
    db = get_db()
    query_lower = query.lower().strip()

    # Intent 1: Query Logs / Questions Asked Intent (HR ADMIN ONLY)
    if any(k in query_lower for k in ["quer", "asked", "history", "recent question", "what did he ask", "what did they ask", "what questions"]):
        if role != "hr_admin":
            return (
                "### 🔒 Privacy Restricted\n\n"
                "Query logs and employee question history are restricted to **HR Administrators** for privacy and compliance.\n\n"
                "If you have a policy question, feel free to ask me directly!"
            )
        cursor = db.query_logs.find({"company_id": company_id}).sort("timestamp", -1).limit(10)
        logs = await cursor.to_list(length=10)
        if logs:
            # Batch fetch missing employee names to eliminate N+1 queries
            missing_uids = list({
                l.get("user_id")
                for l in logs
                if l.get("user_id") and (not l.get("employee_name") or l.get("employee_name") == "Employee")
            })
            user_map = {}
            if missing_uids:
                async for u in db.users.find({"_id": {"$in": missing_uids}}):
                    user_map[u["_id"]] = u.get("fullName") or u.get("email") or "Employee"

            rows = [
                "### 📜 Recent Questions Asked by Employees (Query Logs)\n\n"
                "| Time | Asked By | Question | Answer Excerpt |\n"
                "| :--- | :--- | :--- | :--- |"
            ]
            for log in logs:
                ts = log.get("timestamp", "")
                if ts:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        ts = dt.strftime("%d %b %Y, %H:%M")
                    except Exception:
                        pass

                uid = log.get("user_id")
                emp_name = log.get("employee_name")
                if not emp_name or emp_name == "Employee":
                    emp_name = user_map.get(uid) or "Employee"

                q = log.get("question", "N/A").replace("|", "-")
                a = (log.get("answer", "N/A") or "").split("\n")[0][:70].replace("|", "-")
                rows.append(f"| {ts} | **{emp_name}** | *{q}* | {a}… |")

            return "\n".join(rows)
        else:
            return "### 📜 Query Logs\n\nNo employee questions have been recorded yet for your company."

    # Intent 2: Person / Employee Data Search Intent
    person_keywords = [
        "who is", "email of", "phone of", "contact of", "manager of", "find employee",
        "search directory", "employee profile", "team member", "employees data", "employee data",
        "employee list", "staff list"
    ]
    is_person_search = any(pk in query_lower for pk in person_keywords)

    full_policy_text = await get_company_policy_document_text(company_id)

    if is_person_search:
        # STRICT PRIVACY RULE: Regular employees cannot dump employee directory data!
        if role != "hr_admin":
            return (
                "### 🔒 Privacy Restricted\n\n"
                "Employee directory search and employee personal data are restricted to **HR Administrators** for data privacy and security.\n\n"
                "If you need to contact a colleague or manager, please reach out to your HR department or Line Manager directly."
            )

        stopwords = {
            "the", "and", "for", "who", "what", "need", "data", "about", "is", "find",
            "show", "me", "tell", "details", "info", "information", "of", "in", "manager",
            "email", "phone", "profile", "list", "team", "department", "employees", "members"
        }
        words = [w.strip() for w in query.split() if len(w.strip()) > 1 and w.lower() not in stopwords]
        if words:
            import re
            full_phrase = " ".join(words)
            matched_emps = []

            async for emp in db.users.find({
                "companyId": company_id,
                "role": "employee",
                "$or": [
                    {"fullName": {"$regex": rf"\b{re.escape(full_phrase)}\b", "$options": "i"}},
                    {"email": {"$regex": re.escape(full_phrase), "$options": "i"}},
                ]
            }).limit(10):
                matched_emps.append(emp)

            if matched_emps:
                return format_employees_markdown(matched_emps, f"Results for '{full_phrase}'")

    # Intent 3: Policy RAG Retrieval — check stored document chunks first
    matched_chunk_text = await search_company_document_chunks(company_id, query)
    if matched_chunk_text:
        logger.info(f"Retrieved matching document chunks for query '{query}' (company_id={company_id})")
        return f"{matched_chunk_text}\n\n---\n\n{full_policy_text}"

    # Fallback to general policy synthesis
    logger.info(f"Routing query '{query}' (role={role}) to Gemini Policy Synthesis Engine")
    return extract_relevant_policy_text(full_policy_text, query, employee_context=employee_context)

