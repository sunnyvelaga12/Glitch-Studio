import hmac
import hashlib
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorClientSession
from app.db import get_db
from app.middleware_tracing import get_current_request_id

logger = logging.getLogger("virtualhr.audit")

FORBIDDEN_AUDIT_METADATA_KEYS = {
    "employee_id", "email", "name", "phone", "salary", "medical_info", "ssn", "dob", "address", "password"
}

def hash_ip_address(ip_address: Optional[str]) -> Optional[str]:
    """
    Anonymizes IP address using HMAC-SHA256 with IP_HASH_SECRET to prevent dictionary reversal.
    """
    if not ip_address:
        return None
    secret = os.getenv("IP_HASH_SECRET", "default-ip-hash-secret-key-change-in-prod").encode("utf-8")
    return hmac.new(secret, ip_address.encode("utf-8"), hashlib.sha256).hexdigest()

def sanitize_audit_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures audit metadata contains strictly non-PII operational fields.
    """
    sanitized = {}
    for k, v in metadata.items():
        if k.lower() in FORBIDDEN_AUDIT_METADATA_KEYS:
            continue
        sanitized[k] = v
    return sanitized

async def log_security_audit_event(
    event_type: str,
    company_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    result: str = "success",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    session: Optional[AsyncIOMotorClientSession] = None
) -> str:
    """
    Logs an append-only security audit event in the standardized envelope.
    Native UTC BSON Date object used for timestamp.
    """
    db = get_db()
    event_id = f"evt-{uuid.uuid4()}"
    now_utc = datetime.now(timezone.utc)
    
    audit_doc = {
        "_id": event_id,
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": now_utc,
        "company_id": company_id,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role or "system",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "request_id": get_current_request_id(),
        "result": result,
        "ip_hash": hash_ip_address(ip_address),
        "user_agent": user_agent,
        "metadata": sanitize_audit_metadata(metadata or {})
    }

    try:
        if session:
            await db.audit_logs.insert_one(audit_doc, session=session)
        else:
            await db.audit_logs.insert_one(audit_doc)
        logger.info(f"Audit event logged: {event_type} (event_id={event_id})")
    except Exception as e:
        logger.error(f"Failed to log security audit event {event_type}: {str(e)}")
        # Audit logging failure for critical security events is tracked
    
    return event_id
