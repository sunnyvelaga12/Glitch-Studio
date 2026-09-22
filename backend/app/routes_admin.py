import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import get_current_user, require_role
from app.auth import create_access_token, async_verify_password, async_hash_password
from app.config import settings
from app.db import get_db
from app.routes_auth import _generate_passkey, _normalize_passkey
from app.ai_cost_tracker import (
    add_pricing_version,
    get_dead_letter_events,
    replay_dead_letter_event,
)

router = APIRouter(prefix="/api/admin", tags=["Admin & Telemetry"])


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminCreateAccountRequest(BaseModel):
    email: str
    password: str
    role: str
    fullName: str
    companyName: Optional[str] = None
    companyId: Optional[str] = None
    passkey: Optional[str] = None


@router.post("/login")
async def admin_login(payload: AdminLoginRequest):
    """
    Authenticate super administrator or HR administrator for portal account provisioning.
    """
    email = payload.email.strip().lower()
    db = get_db()

    # 1. Check super-admin env credentials if configured
    if (
        settings.ADMIN_EMAIL
        and email == settings.ADMIN_EMAIL.strip().lower()
        and settings.ADMIN_PASSWORD_HASH
    ):
        if await async_verify_password(payload.password, settings.ADMIN_PASSWORD_HASH):
            token = create_access_token(
                user_id="super_admin",
                role="super_admin",
                company_id="global",
                token_version=1,
                email=email,
                full_name="Super Administrator"
            )
            return {"accessToken": token, "token_type": "bearer"}

    # 2. Check DB for hr_admin or super_admin account
    user = await db.users.find_one({"email": email})
    if not user or user.get("role") not in ("hr_admin", "admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or insufficient admin privileges."
        )

    if not await async_verify_password(payload.password, user.get("passwordHash") or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials."
        )

    company_id = user.get("companyId") or user.get("company_id") or "global"
    token = create_access_token(
        user_id=str(user["_id"]),
        role=user.get("role", "hr_admin"),
        company_id=company_id,
        token_version=user.get("tokenVersion", 1),
        email=email,
        full_name=user.get("fullName", "HR Administrator")
    )
    return {"accessToken": token, "token_type": "bearer"}


@router.post("/create-account")
async def admin_create_account(
    payload: AdminCreateAccountRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Admin-authorized account creation endpoint for HR admins and employees.
    """
    if current_user.get("role") not in ("hr_admin", "admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create accounts via this portal."
        )

    db = get_db()
    email = payload.email.strip().lower()

    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists."
        )

    hashed_pwd = await async_hash_password(payload.password)
    now = datetime.now(timezone.utc).isoformat()
    company_id = None
    company_name = ""

    if payload.role == "hr_admin":
        if payload.companyName:
            company_name = payload.companyName.strip()
            company_id = str(uuid.uuid4())
            passkey = _generate_passkey()
            await db.companies.insert_one({
                "_id": company_id,
                "name": company_name,
                "passkey": passkey,
                "createdAt": now,
                "created_at": now,
                "settings": {},
            })
        elif payload.companyId:
            company_id = payload.companyId.strip()
            from bson import ObjectId
            c_doc = await db.companies.find_one({"_id": company_id})
            if not c_doc and ObjectId.is_valid(company_id):
                c_doc = await db.companies.find_one({"_id": ObjectId(company_id)})
            company_name = c_doc.get("name", "Company") if c_doc else "Company Workspace"
        else:
            company_id = current_user.get("company_id")
            c_doc = await db.companies.find_one({"_id": company_id})
            company_name = c_doc.get("name", "Company") if c_doc else "Company Workspace"

        user_id = str(uuid.uuid4())
        await db.users.insert_one({
            "_id": user_id,
            "email": email,
            "passwordHash": hashed_pwd,
            "role": "hr_admin",
            "companyId": company_id,
            "company_id": company_id,
            "fullName": payload.fullName.strip() or email.split("@")[0].title(),
            "department": "Human Resources",
            "jobTitle": "HR Administrator",
            "tokenVersion": 1,
            "token_version": 1,
            "isActive": True,
            "createdAt": now,
            "created_at": now,
        })
        return {
            "email": email,
            "role": "hr_admin",
            "companyName": company_name,
        }

    elif payload.role == "employee":
        if payload.passkey:
            pk = _normalize_passkey(payload.passkey.strip())
            c_doc = await db.companies.find_one({"passkey": pk})
            if not c_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No workspace found with this passkey."
                )
            company_id = str(c_doc["_id"])
            company_name = c_doc.get("name", "Company")
        elif payload.companyId:
            company_id = payload.companyId.strip()
            from bson import ObjectId
            c_doc = await db.companies.find_one({"_id": company_id})
            if not c_doc and ObjectId.is_valid(company_id):
                c_doc = await db.companies.find_one({"_id": ObjectId(company_id)})
            company_name = c_doc.get("name", "Company") if c_doc else "Company"
        else:
            company_id = current_user.get("company_id")
            c_doc = await db.companies.find_one({"_id": company_id})
            company_name = c_doc.get("name", "Company") if c_doc else "Company"

        user_id = str(uuid.uuid4())
        await db.users.insert_one({
            "_id": user_id,
            "email": email,
            "passwordHash": hashed_pwd,
            "role": "employee",
            "companyId": company_id,
            "company_id": company_id,
            "fullName": payload.fullName.strip() or email.split("@")[0].title(),
            "department": "General",
            "jobTitle": "Team Member",
            "tokenVersion": 1,
            "token_version": 1,
            "isActive": True,
            "createdAt": now,
            "created_at": now,
        })
        return {
            "email": email,
            "role": "employee",
            "companyName": company_name,
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid role specified."
    )


class PricingCreateRequest(BaseModel):
    provider: str = Field(..., json_schema_extra={"example": "gemini"})
    model: str = Field(..., json_schema_extra={"example": "gemini-1.5-pro"})
    pricing_version: str = Field(..., json_schema_extra={"example": "v1.2026.08"})
    input_price_per_1m_tokens: float = Field(..., json_schema_extra={"example": 1.25})
    output_price_per_1m_tokens: float = Field(..., json_schema_extra={"example": 5.00})
    effective_from: datetime
    effective_until: Optional[datetime] = None
    currency: str = Field("USD")

@router.get("/ai-usage/dead-letters", response_model=List[Dict[str, Any]])
async def list_dlq_events(
    limit: int = 50,
    current_user: dict = Depends(require_role("hr_admin"))
):
    """
    List events currently in the AI usage dead-letter queue (DLQ).
    """
    return await get_dead_letter_events(limit=limit)

@router.post("/ai-usage/dead-letters/{event_id}/replay")
async def replay_dlq_event(
    event_id: str,
    current_user: dict = Depends(require_role("hr_admin"))
):
    """
    Replay a dead-letter event by resetting state to PENDING.
    """
    success = await replay_dead_letter_event(event_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dead-letter event '{event_id}' not found or not in DEAD_LETTER state"
        )
    return {"message": f"Dead-letter event '{event_id}' reset to PENDING for replay"}

@router.post("/ai-pricing")
async def create_pricing_version(
    payload: PricingCreateRequest,
    current_user: dict = Depends(require_role("hr_admin"))
):
    """
    Create a new versioned AI model pricing record with concurrency-serialized overlap check.
    """
    res = await add_pricing_version(
        provider=payload.provider,
        model=payload.model,
        pricing_version=payload.pricing_version,
        input_price_per_1m_tokens=payload.input_price_per_1m_tokens,
        output_price_per_1m_tokens=payload.output_price_per_1m_tokens,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        currency=payload.currency
    )
    # Serialize datetime objects in response
    if isinstance(res.get("effective_from"), datetime):
        res["effective_from"] = res["effective_from"].isoformat()
    if isinstance(res.get("effective_until"), datetime):
        res["effective_until"] = res["effective_until"].isoformat()
    if isinstance(res.get("created_at"), datetime):
        res["created_at"] = res["created_at"].isoformat()
    return res
