"""
Passkey Service — Argon2id Passkey Hashing, Verification & Rate-Limiting Governance

Enforces secure Argon2id password key derivation for company onboarding passkeys with:
- Argon2id salt & hashing (64MB memory cost, 2 iterations, 2 parallelism)
- Expiration timestamp validation
- Revocation status verification
- 5-attempt rate-limiting throttle per verification session
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from argon2 import PasswordHasher, exceptions


class PasskeyVerificationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    RATE_LIMITED = "RATE_LIMITED"


class PasskeyVerificationResult:
    def __init__(self, status: PasskeyVerificationStatus, message: str):
        self.status = status
        self.message = message
        self.is_valid = status == PasskeyVerificationStatus.SUCCESS


# Argon2id PasswordHasher configured according to OWASP / Phase 1 baseline
_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_passkey(raw_passkey: str) -> str:
    """Hashes a raw passkey string using Argon2id."""
    if not raw_passkey or len(raw_passkey) < 6:
        raise ValueError("Passkey must be at least 6 characters long")
    return _ph.hash(raw_passkey)


def verify_passkey(
    passkey_hash: str,
    raw_passkey: str,
    expires_at: Optional[datetime] = None,
    is_revoked: bool = False,
    failed_attempts: int = 0,
    max_attempts: int = 5,
) -> PasskeyVerificationResult:
    """
    Verifies a raw passkey against its Argon2id hash with expiration, revocation, 
    and failed-attempt throttling checks.
    """
    # 1. Check Rate Limit / Max Failed Attempts
    if failed_attempts >= max_attempts:
        return PasskeyVerificationResult(
            PasskeyVerificationStatus.RATE_LIMITED,
            f"Maximum passkey verification attempts ({max_attempts}) exceeded. Account throttled."
        )

    # 2. Check Revocation Status
    if is_revoked:
        return PasskeyVerificationResult(
            PasskeyVerificationStatus.REVOKED,
            "Passkey has been explicitly revoked by company administrator."
        )

    # 3. Check Expiration Timestamp
    if expires_at:
        now = datetime.now(timezone.utc)
        # Ensure expires_at is timezone-aware
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            return PasskeyVerificationResult(
                PasskeyVerificationStatus.EXPIRED,
                "Passkey has expired."
            )

    # 4. Verify Argon2id Hash
    try:
        _ph.verify(passkey_hash, raw_passkey)
        return PasskeyVerificationResult(
            PasskeyVerificationStatus.SUCCESS,
            "Passkey verified successfully."
        )
    except (exceptions.VerifyMismatchError, exceptions.VerificationError, exceptions.InvalidHashError):
        return PasskeyVerificationResult(
            PasskeyVerificationStatus.INVALID,
            "Invalid passkey provided."
        )
