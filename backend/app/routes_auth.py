"""
routes_auth.py — Authentication: signup, login, logout, workspace passkey lookup, forgot/reset password
"""

import logging
import secrets
import string
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query

logger = logging.getLogger(__name__)

from app.db import get_db
from app.config import settings
from app.cache import auth_rate_limiter
from app.auth import (
    create_access_token,
    decode_access_token,
    async_hash_password,
    async_verify_password,
    hash_reset_token,
    generate_secure_token,
)
from app.deps import require_role, get_current_user
from app.email_service import get_email_service
from app.schemas_auth import (
    LoginRequest,
    LoginResponse,
    SignupResponse,
    SignupRequest,
    WorkspaceInfoResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_passkey(length: int = 8) -> str:
    """Generate a short, memorable workspace passkey (uppercase alphanumeric)."""
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace("O", "").replace("I", "").replace("0", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _format_passkey(raw: str) -> str:
    """Format passkey as XXXX-XXXX for readability."""
    raw = raw.upper()
    if len(raw) == 8:
        return f"{raw[:4]}-{raw[4:]}"
    return raw


def _normalize_passkey(pk: str) -> str:
    """Strip dashes, uppercase — canonical form for DB storage and lookup."""
    return pk.replace("-", "").upper()


def _check_rate_limit(request: Request, endpoint: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not auth_rate_limiter.is_allowed(client_ip):
        logger.warning(f"Auth rate limit exceeded for IP: {client_ip} on endpoint {endpoint}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication requests. Please try again later.",
        )


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=SignupResponse)
async def signup(payload: SignupRequest, request: Request):
    _check_rate_limit(request, "/api/auth/signup")
    db = get_db()

    import re
    email = payload.email.strip().lower()
    existing_user = await db.users.find_one({"$or": [{"email": email}, {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}]})
    if existing_user:
        # Check if this is an employee account pre-created / imported by HR Admin
        if payload.role == "employee" and existing_user.get("role") == "employee":
            if not payload.passkey or not payload.passkey.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Workspace passkey is required to activate your employee account.",
                )
            normalised = _normalize_passkey(payload.passkey)
            company = await db.companies.find_one({"passkey": normalised})
            user_comp_id = str(existing_user.get("companyId") or existing_user.get("company_id") or "")
            if not company or str(company["_id"]) != user_comp_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Workspace passkey does not match this employee account's company.",
                )
            # Legitimate employee claiming / activating account
            hashed_pwd = await async_hash_password(payload.password)
            now = datetime.now(timezone.utc).isoformat()
            update_data = {
                "passwordHash": hashed_pwd,
                "tempPassword": None,
                "isActive": True,
                "is_active": True,
                "updated_at": now,
            }
            if payload.fullName and payload.fullName.strip():
                update_data["fullName"] = payload.fullName.strip()
            await db.users.update_one({"_id": existing_user["_id"]}, {"$set": update_data})
            return SignupResponse(
                message="Account successfully activated! You can now log in with your credentials and workspace passkey.",
                companyId=str(company["_id"]),
                companyName=company.get("name", "Your Company"),
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    company_id = payload.companyId
    company_name = "My Company"
    now = datetime.now(timezone.utc).isoformat()

    # ── Employee ──────────────────────────────────────────────────────────────
    if payload.role == "employee":
        company_id = None
        company_name = "Your Company"

        if payload.passkey:
            normalised = _normalize_passkey(payload.passkey)
            company = await db.companies.find_one({"passkey": normalised})
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Invalid workspace passkey. Please check with your HR admin.",
                )
            company_id = str(company["_id"])
            company_name = company.get("name", "Your Company")
        elif payload.companyId:
            company = await db.companies.find_one({"_id": payload.companyId})
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Company workspace not found.",
                )
            company_id = str(company["_id"])
            company_name = company.get("name", "Your Company")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee accounts require a workspace passkey or company ID.",
            )

        hashed_pwd = await async_hash_password(payload.password)
        user_id = str(uuid.uuid4())

        await db.users.insert_one({
            "_id": user_id,
            "email": email,
            "passwordHash": hashed_pwd,
            "role": "employee",
            "companyId": company_id,
            "company_id": company_id,
            "fullName": payload.fullName or email.split("@")[0].title(),
            "department": getattr(payload, "department", "General") or "General",
            "jobTitle": getattr(payload, "jobTitle", "Team Member") or "Team Member",
            "phone": getattr(payload, "phone", "") or "",
            "managerName": getattr(payload, "managerName", "") or "",
            "officeLocation": getattr(payload, "officeLocation", "") or "",
            "workMode": getattr(payload, "workMode", "Hybrid") or "Hybrid",
            "tokenVersion": 1,
            "token_version": 1,
            "isActive": True,
            "createdAt": now,
            "created_at": now,
        })

        return SignupResponse(
            message="Employee account created successfully. You can now log in.",
            companyId=company_id,
            companyName=company_name,
        )

    # ── HR Admin ──────────────────────────────────────────────────────────────
    elif payload.role == "hr_admin":
        if payload.companyName and not company_id:
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
        elif company_id:
            company = await db.companies.find_one({"_id": company_id})
            if not company:
                raise HTTPException(status_code=404, detail="Company not found.")
            company_name = company.get("name", "My Company")
        else:
            company_name = f"{payload.fullName or 'HRAdmin'}'s Workspace"
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

        hashed_pwd = await async_hash_password(payload.password)
        user_id = str(uuid.uuid4())

        await db.users.insert_one({
            "_id": user_id,
            "email": email,
            "passwordHash": hashed_pwd,
            "role": "hr_admin",
            "companyId": company_id,
            "company_id": company_id,
            "fullName": payload.fullName or email.split("@")[0].title(),
            "department": "Human Resources",
            "jobTitle": "HR Administrator",
            "tokenVersion": 1,
            "token_version": 1,
            "isActive": True,
            "createdAt": now,
            "created_at": now,
        })

        return SignupResponse(
            message="HR Admin account created successfully.",
            companyId=company_id,
            companyName=company_name,
        )

    raise HTTPException(status_code=400, detail="Invalid role specified.")


# ---------------------------------------------------------------------------
# Workspace passkey lookup
# ---------------------------------------------------------------------------

@router.get("/workspace/{passkey}", response_model=WorkspaceInfoResponse)
async def get_workspace_by_passkey(passkey: str, request: Request):
    _check_rate_limit(request, "/api/auth/workspace")
    normalised = _normalize_passkey(passkey)
    db = get_db()
    company = await db.companies.find_one({"passkey": normalised})
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No workspace found with this passkey.",
        )
    return WorkspaceInfoResponse(
        companyId=str(company["_id"]),
        companyName=company.get("name", "Unknown Workspace"),
        passkey=_format_passkey(normalised),
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, response: Response):
    _check_rate_limit(request, "/api/auth/login")
    import re
    email = payload.email.strip().lower()
    db = get_db()

    user = await db.users.find_one({"$or": [{"email": email}, {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}]})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.get("isActive", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account disabled")

    role = user.get("role", "employee")
    company_id = user.get("companyId") or user.get("company_id")
    user_id = str(user["_id"])
    token_version = user.get("tokenVersion") or user.get("token_version", 1)

    if role not in ("hr_admin", "employee") or not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user record")

    # ── Workspace Passkey Verification for Employee Login ─────────────────────
    if role == "employee" or payload.role == "employee":
        if not payload.passkey or not payload.passkey.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workspace passkey is required for employee login.",
            )

        company = await db.companies.find_one({"$or": [{"_id": company_id}, {"id": company_id}]})
        if not company or not company.get("passkey"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Company workspace configuration error. Please contact your HR administrator.",
            )

        norm_user_pk = _normalize_passkey(payload.passkey)
        norm_comp_pk = _normalize_passkey(company.get("passkey", ""))
        if norm_user_pk != norm_comp_pk:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid workspace passkey for this company.",
            )

    # ── Password Verification ──────────────────────────────────────────────────
    is_valid = await async_verify_password(payload.password, user.get("passwordHash") or "")

    # Seamless first-time onboarding for imported employees:
    # If the user still has an initial tempPassword (or uses their email as initial password)
    # and has passed the secret workspace passkey verification above:
    if not is_valid and user.get("tempPassword"):
        if payload.password == user.get("tempPassword") or payload.password.strip().lower() == email:
            is_valid = True
            new_hash = await async_hash_password(payload.password)
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"passwordHash": new_hash, "tempPassword": None, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. If this is your first time signing in, activate your account via 'Create account' using your workspace passkey.",
        )

    # Create session document in DB
    session_id = str(uuid.uuid4())
    now_dt = datetime.now(timezone.utc)
    exp_dt = now_dt + timedelta(minutes=settings.JWT_EXP_MINUTES)

    await db.sessions.insert_one({
        "session_id": session_id,
        "user_id": user_id,
        "company_id": company_id,
        "token_version": token_version,
        "created_at": now_dt.isoformat(),
        "expires_at": exp_dt.isoformat(),
        "revoked_at": None,
        "user_agent": request.headers.get("User-Agent", "unknown"),
        "client_ip": request.client.host if request.client else "unknown",
    })

    full_name = user.get("fullName") or email.split("@")[0].title()
    token = create_access_token(
        user_id=user_id,
        role=role,
        company_id=company_id,
        session_id=session_id,
        token_version=token_version,
        email=email,
        full_name=full_name,
    )

    # Set HttpOnly Session Cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_EXP_MINUTES * 60,
        path="/",
    )

    # Set Double-Submit CSRF Cookie
    csrf_token = generate_secure_token(16)
    response.set_cookie(
        key="virtualhr_csrf",
        value=csrf_token,
        httponly=False,  # Readable by JS to pass in X-CSRF-Token header
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_EXP_MINUTES * 60,
        path="/",
    )

    return LoginResponse(
        accessToken=token,
        role=role,
        companyId=company_id,
    )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    all_sessions: bool = Query(default=False, description="Revoke all active sessions across devices"),
    user: dict = Depends(get_current_user),
):
    """
    Logout current session or all active sessions.
    Clears HttpOnly authentication cookies.
    """
    db = get_db()
    user_id = user.get("sub") or user.get("user_id")
    session_id = user.get("session_id")
    now_iso = datetime.now(timezone.utc).isoformat()

    if all_sessions and user_id:
        # Increment tokenVersion on user document -> invalidates ALL JWT tokens globally
        await db.users.update_one(
            {"_id": user_id},
            {"$inc": {"tokenVersion": 1, "token_version": 1}}
        )
        await db.sessions.update_many(
            {"user_id": user_id, "revoked_at": None},
            {"$set": {"revoked_at": now_iso}}
        )
        logger.info(f"User {user_id} revoked all active sessions.")
    elif session_id:
        # Revoke current session
        await db.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"revoked_at": now_iso}}
        )
        logger.info(f"User {user_id} logged out session {session_id}.")

    # Clear Cookies
    response.delete_cookie(key=settings.COOKIE_NAME, path="/")
    response.delete_cookie(key="virtualhr_csrf", path="/")

    return {"message": "Successfully logged out."}


# ---------------------------------------------------------------------------
# Forgot & Reset Password
# ---------------------------------------------------------------------------

@router.post("/forgot-password", response_model=ForgotPasswordResponse, status_code=status.HTTP_200_OK)
async def forgot_password(payload: ForgotPasswordRequest, request: Request):
    _check_rate_limit(request, "/api/auth/forgot-password")
    email = payload.email.strip().lower()
    db = get_db()

    user = await db.users.find_one({"email": email})
    if not user:
        # Return generic success to prevent email enumeration
        return ForgotPasswordResponse(
            message="If an account with that email exists, reset instructions have been issued.",
        )

    # Generate secure reset token
    raw_token = generate_secure_token(16)
    hashed_token = hash_reset_token(raw_token)
    exp_dt = datetime.now(timezone.utc) + timedelta(minutes=60)

    # Store hashed reset token in password_resets collection
    await db.password_resets.insert_one({
        "token_hash": hashed_token,
        "user_id": str(user["_id"]),
        "email": email,
        "company_id": user.get("companyId") or user.get("company_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": exp_dt.isoformat(),
        "used": False,
    })

    # Dispatch via EmailService
    email_service = get_email_service()
    await email_service.send_password_reset_email(email, raw_token)

    return ForgotPasswordResponse(
        message="Password reset instructions issued successfully. Check your email.",
        resetToken=raw_token if settings.is_development else None,
    )


@router.post("/reset-password", response_model=ResetPasswordResponse, status_code=status.HTTP_200_OK)
async def reset_password(payload: ResetPasswordRequest, request: Request):
    _check_rate_limit(request, "/api/auth/reset-password")
    raw_token = payload.token.strip()
    token_hash = hash_reset_token(raw_token)
    db = get_db()

    reset_record = await db.password_resets.find_one({"token_hash": token_hash, "used": False})
    if not reset_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    exp_dt = datetime.fromisoformat(reset_record["expires_at"])
    if datetime.now(timezone.utc) > exp_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one.",
        )

    user_id = reset_record["user_id"]
    new_hash = await async_hash_password(payload.newPassword)

    # 1. Update password
    # 2. Mark reset token used
    # 3. Increment tokenVersion -> invalidates all existing active user sessions
    from bson import ObjectId
    user_filter = {"_id": user_id}
    if ObjectId.is_valid(user_id):
        existing_doc = await db.users.find_one({"_id": user_id})
        if not existing_doc:
            user_filter = {"_id": ObjectId(user_id)}

    await db.users.update_one(
        user_filter,
        {
            "$set": {"passwordHash": new_hash},
            "$inc": {"tokenVersion": 1, "token_version": 1},
        }
    )
    await db.password_resets.update_one(
        {"_id": reset_record["_id"]},
        {"$set": {"used": True}}
    )

    logger.info(f"Password reset completed for user_id={user_id}. All existing sessions invalidated.")

    return ResetPasswordResponse(
        message="Your password has been reset successfully. All existing active sessions have been logged out. Please sign in with your new password.",
    )
