import os
import re
from typing import Any, Dict, Optional

SENSITIVE_KEYS_SENTRY = {
    "password", "token", "secret", "authorization", "cookie", "set-cookie", "csrf", "x-csrf-token",
    "ssn", "salary", "phone", "date_of_birth", "dob", "medical_info", "address", "email", "query_text",
    "prompt", "completion_text", "raw_policy_content"
}

def sanitize_recursively(data: Any) -> Any:
    """
    Recursively scrubs nested dictionaries, lists, breadcrumbs, and exception details for Sentry events.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if isinstance(k, str) and k.lower() in SENSITIVE_KEYS_SENTRY:
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_recursively(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_recursively(item) for item in data]
    elif isinstance(data, str):
        if "Bearer " in data or "Token " in data:
            return re.sub(r'(Bearer|Token)\s+[A-Za-z0-9._\~+/-]+=*', r'\1 [REDACTED]', data)
    return data

def sentry_before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Sentry before_send hook that recursively sanitizes request headers, cookies, payloads, stack traces, and breadcrumbs.
    """
    if not event:
        return event

    # Sanitize request details
    if "request" in event and isinstance(event["request"], dict):
        req = event["request"]
        if "headers" in req:
            req["headers"] = sanitize_recursively(req["headers"])
        if "cookies" in req:
            req["cookies"] = "[REDACTED]"
        if "data" in req:
            req["data"] = sanitize_recursively(req["data"])
        if "query_string" in req:
            req["query_string"] = "[REDACTED]"

    # Sanitize breadcrumbs, extra, exception, tags, contexts, and user details
    for section in ["breadcrumbs", "extra", "exception", "tags", "contexts", "user"]:
        if section in event and event[section]:
            event[section] = sanitize_recursively(event[section])

    return event

def init_sentry(dsn: Optional[str] = None, environment: str = "development", release: str = "1.0.0") -> None:
    sentry_dsn = dsn or os.getenv("SENTRY_DSN")
    if not sentry_dsn:
        return

    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            release=release,
            send_default_pii=False,
            before_send=sentry_before_send,
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
        )
    except ImportError:
        pass
