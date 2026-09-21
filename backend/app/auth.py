import hashlib
import os
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

def _jwt_secret() -> str:
    secret = settings.JWT_SECRET
    if not secret or "dev-secret-key" in secret:
        if not settings.is_development:
            raise RuntimeError(
                "CRITICAL SECURITY ERROR: JWT_SECRET must be explicitly set to a strong secret in production/staging environments."
            )
        if not secret:
            logger.warning("JWT_SECRET is not set in .env — using fallback development key")
            return "dev-secret-key-virtualhr-ai-saas-2026"
    return secret


def _jwt_exp_minutes() -> int:
    return settings.JWT_EXP_MINUTES


def hash_password(password: str) -> str:
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is not installed") from exc

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is not installed") from exc

    if not hashed or not isinstance(hashed, str):
        return False

    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception as exc:
        logger.warning(f"Failed to verify password hash: {exc}")
        return False


async def async_hash_password(password: str) -> str:
    """Non-blocking async wrapper for CPU-bound password hashing."""
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(hash_password, password)


async def async_verify_password(password: str, hashed: str) -> bool:
    """Non-blocking async wrapper for CPU-bound password verification."""
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(verify_password, password, hashed)


def hash_reset_token(token: str) -> str:
    """Hash password reset token using SHA-256 before database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secure_token(length: int = 32) -> str:
    """Generate cryptographically secure random token."""
    return secrets.token_hex(length)


def create_access_token(
    *,
    user_id: str,
    role: str,
    company_id: str,
    session_id: str = "",
    token_version: int = 1,
    email: str = "",
    full_name: str = "",
) -> str:
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("pyjwt is not installed") from exc

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=_jwt_exp_minutes())

    payload = {
        "sub": user_id,
        "role": role,
        "companyId": company_id,
        "company_id": company_id,
        "sessionId": session_id,
        "session_id": session_id,
        "tokenVersion": token_version,
        "token_version": token_version,
        "email": email,
        "fullName": full_name,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    token = jwt.encode(payload, _jwt_secret(), algorithm="HS256")
    return token


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("pyjwt is not installed") from exc

    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ---------------------------------------------------------------------------
# Super-Admin Auth (env-credential based — never touches the DB)
# ---------------------------------------------------------------------------

def is_super_admin(email: str, password: str) -> bool:
    """Validate super-admin credentials against env-stored values.

    The super-admin account is NOT stored in MongoDB — it lives entirely
    in environment variables so it cannot be brute-forced via the DB.
    """
    admin_email = settings.ADMIN_EMAIL.strip().lower()
    admin_hash = settings.ADMIN_PASSWORD_HASH.strip()

    if not admin_email or not admin_hash:
        logger.error("ADMIN_EMAIL or ADMIN_PASSWORD_HASH not configured in .env")
        return False

    if email.strip().lower() != admin_email:
        return False

    return verify_password(password, admin_hash)


def create_admin_token() -> str:
    """Create a short-lived JWT for the super-admin session."""
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("pyjwt is not installed") from exc

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.ADMIN_JWT_EXP_MINUTES)

    payload = {
        "sub": "super_admin",
        "role": "super_admin",
        "companyId": "__system__",
        "company_id": "__system__",
        "sessionId": "system_admin_session",
        "tokenVersion": 1,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")

