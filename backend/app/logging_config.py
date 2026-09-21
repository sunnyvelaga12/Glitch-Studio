import json
import logging
import re
from typing import Any, Dict
from app.middleware_tracing import get_current_request_id, get_current_company_id, get_current_user_id

# Class A (Secrets) & Class B (Direct PII) sensitive keys to redact prior to serialization
SENSITIVE_KEYS = {
    "password", "token", "secret", "authorization", "cookie", "set-cookie", "csrf", "x-csrf-token",
    "ssn", "salary", "phone", "date_of_birth", "dob", "medical_info", "address", "query_text",
    "prompt", "prompt_text", "completion_text", "raw_policy_content"
}

class JSONFormatter(logging.Formatter):
    """
    Production-grade single-line JSON log formatter with 3-tier redaction governance.
    - Class A (Secrets) & Class B (Direct PII): Redacted prior to serialization.
    - Class C (Operational Identifiers): company_id, user_id, request_id allowed.
    """
    def __init__(self, environment: str = "development", service_name: str = "virtualhr-api", version: str = "1.0.0"):
        super().__init__()
        self.environment = environment
        self.service_name = service_name
        self.version = version

    def redact_data(self, data: Any) -> Any:
        if isinstance(data, dict):
            redacted_dict = {}
            for key, val in data.items():
                if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                    if key.lower() == "authorization" and isinstance(val, str) and (val.startswith("Bearer ") or val.startswith("Token ")):
                        prefix = val.split(" ")[0]
                        redacted_dict[key] = f"{prefix} [REDACTED]"
                    else:
                        redacted_dict[key] = "[REDACTED]"
                else:
                    redacted_dict[key] = self.redact_data(val)
            return redacted_dict
        elif isinstance(data, list):
            return [self.redact_data(item) for item in data]
        elif isinstance(data, str):
            # Redact Authorization Bearer strings if present in text
            if "Bearer " in data or "Token " in data:
                return re.sub(r'(Bearer|Token)\s+[A-Za-z0-9._\~+/-]+=*', r'\1 [REDACTED]', data)
        return data

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "environment": self.environment,
            "service": self.service_name,
            "version": self.version,
            "request_id": get_current_request_id() or getattr(record, "request_id", None),
            "company_id": get_current_company_id() or getattr(record, "company_id", None),
            "user_id": get_current_user_id() or getattr(record, "user_id", None),
            "logger": record.name,
            "message": record.getMessage()
        }

        # Include additional extra record attributes if passed
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_payload.update(record.extra_fields)

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Apply 3-tier redaction before JSON serialization
        redacted_payload = self.redact_data(log_payload)
        return json.dumps(redacted_payload)


def setup_logging(level: str = "INFO", environment: str = "development") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Clear existing handlers to avoid duplicate output
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = JSONFormatter(environment=environment)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def sentry_before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sentry before-send hook ensuring Class A (Secrets) & Class B (PII) are recursively scrubbed
    prior to outbound transmission.
    """
    formatter = JSONFormatter()
    return formatter.redact_data(event)
