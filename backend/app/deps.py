"""
deps.py — Dependency Injection & Authorization Helpers for VirtualHR

Features:
  - Hybrid Auth Extraction: Inspects HttpOnly session cookie (virtualhr_session) OR Authorization Bearer header
  - Token Version Validation: Verifies JWT token_version against MongoDB user document
  - Session Revocation Check: Verifies session is active and not revoked in MongoDB sessions collection
  - CSRF Protection Strategy: Enforces Double-Submit Anti-CSRF check on state-changing requests ONLY for cookie-authenticated browser clients (Bearer header requests exempt)
  - Tenant Boundary Authorization: Enforces company_id boundary isolation across API endpoints
"""

from typing import Any, Optional
import logging

from fastapi import Depends, Header, HTTPException, Request, status

from app.auth import decode_access_token
from app.config import settings

logger = logging.getLogger(__name__)


def extract_token_from_request(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> tuple[str, str]:
    """
    Extract authentication token and source type.
    
    Returns:
        (token: str, auth_source: "cookie" | "bearer")
    """
    # 1. Check Authorization Bearer header FIRST (active SPA token)
    if authorization:
        parts = authorization.split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1], "bearer"

    # 2. Check HttpOnly cookie fallback
    cookie_token = request.cookies.get(settings.COOKIE_NAME)
    if cookie_token:
        return cookie_token, "cookie"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication credentials. Please log in.",
    )


async def get_current_user(
    request: Request,
    token_and_source: tuple[str, str] = Depends(extract_token_from_request),
) -> dict[str, Any]:
    """
    Authenticate user and validate session and token_version against MongoDB.
    """
    token, auth_source = token_and_source
    payload = decode_access_token(token)

    user_id = payload.get("sub")
    role = payload.get("role")
    company_id = payload.get("company_id") or payload.get("companyId")
    session_id = payload.get("session_id") or payload.get("sessionId")
    token_version = payload.get("token_version") or payload.get("tokenVersion", 1)

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload structure",
        )

    # Super-admin bypass (credential based, no DB session)
    if role == "super_admin":
        payload["auth_source"] = auth_source
        return payload

    # Database validation against users and sessions collections
    from app.db import get_db
    db = get_db()

    from bson import ObjectId
    user_doc = await db.users.find_one({"_id": user_id})
    if not user_doc and user_id and ObjectId.is_valid(user_id):
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user_doc and payload.get("email"):
        user_doc = await db.users.find_one({"email": payload.get("email").strip().lower()})

    if not user_doc or not user_doc.get("isActive", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or no longer exists",
        )

    # Validate token_version
    db_token_version = user_doc.get("tokenVersion") or user_doc.get("token_version", 1)
    if token_version != db_token_version:
        logger.warning(
            f"Token version mismatch for user {user_id}: token={token_version}, DB={db_token_version}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired due to password change or global logout. Please log in again.",
        )

    # Validate individual session status
    if session_id:
        session_doc = await db.sessions.find_one({"session_id": session_id})
        if session_doc and session_doc.get("revoked_at") is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This session has been logged out",
            )

    # Attach verified identity and auth source to returned dict
    user_payload = dict(payload)
    user_payload["auth_source"] = auth_source
    user_payload["user_id"] = user_id
    user_payload["company_id"] = company_id
    user_payload["fullName"] = user_doc.get("fullName", payload.get("fullName", ""))
    return user_payload


def verify_csrf_token(
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
    user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """
    Anti-CSRF Strategy:
    CSRF validation applies STRICTLY to cookie-authenticated browser requests on state-changing methods.
    Bearer-token API clients are authenticated via Authorization header and exempt from CSRF checks.
    """
    auth_source = user.get("auth_source")
    if auth_source != "cookie":
        # Bearer header API client — exempt from browser CSRF check
        return

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        cookie_csrf = request.cookies.get("virtualhr_csrf")
        if not cookie_csrf or not x_csrf_token or cookie_csrf != x_csrf_token:
            logger.warning(f"CSRF validation failed for user {user.get('sub')} on {request.method} {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token for state-changing request",
            )


def verify_tenant_access(user: dict[str, Any], target_company_id: str) -> None:
    """
    Enforce multi-tenant boundary isolation at data access layer.
    Raises 403 Forbidden if user company_id does not match target_company_id.
    """
    user_company = user.get("company_id") or user.get("companyId")
    if user.get("role") == "super_admin":
        return

    if not user_company or user_company != target_company_id:
        logger.warning(
            f"Tenant Boundary Security Denial: user {user.get('sub')} (company: {user_company}) "
            f"attempted to access target company: {target_company_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Cross-tenant resource access denied",
        )


def require_role(role: str):
    def _dep(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user.get("role") != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep


def require_super_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Super admin credentials required.",
        )
    return user
