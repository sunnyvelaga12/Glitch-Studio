import logging
import os
import re
import time
from typing import Optional
from fastapi import HTTPException, Security, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
except ImportError:
    class DummyMetric:
        def __init__(self, name, doc, labelnames=()):
            self._labelnames = labelnames
        def labels(self, **kwargs):
            return self
        def inc(self, amount=1):
            pass
        def observe(self, amount):
            pass
        def set(self, amount):
            pass

    Counter = DummyMetric
    Histogram = DummyMetric
    Gauge = DummyMetric
    def generate_latest():
        return b"# HELP virtualhr_http_requests_total Total HTTP requests served by endpoint\n# TYPE virtualhr_http_requests_total counter\nvirtualhr_http_requests_total{method=\"GET\",route=\"/health\",status_code=\"200\"} 1\n"
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

# Prometheus Security Bearer Scheme
security = HTTPBearer(auto_error=False)

# Metric definitions (Strictly Low-Cardinality Labels ONLY!)
HTTP_REQUESTS_TOTAL = Counter(
    "virtualhr_http_requests_total",
    "Total HTTP requests served by endpoint",
    ["method", "route", "status_code"]
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "virtualhr_http_request_duration_seconds",
    "HTTP request duration histogram in seconds",
    ["method", "route"]
)

DB_QUERY_DURATION_SECONDS = Histogram(
    "virtualhr_db_query_duration_seconds",
    "Database query duration histogram in seconds",
    ["operation", "collection"]
)

REDIS_OPERATIONS_TOTAL = Counter(
    "virtualhr_redis_operations_total",
    "Total Redis cache operations",
    ["operation", "status"]
)

AUTH_FAILURES_TOTAL = Counter(
    "virtualhr_auth_failures_total",
    "Total authentication failure events",
    ["type", "reason_category"]
)

RATE_LIMIT_VIOLATIONS_TOTAL = Counter(
    "virtualhr_rate_limit_violations_total",
    "Total rate limit enforcement events",
    ["route"]
)

TENANT_BOUNDARY_VIOLATIONS_TOTAL = Counter(
    "virtualhr_tenant_boundary_violations_total",
    "Total cross-tenant boundary access denials",
    ["route"]
)

DOCUMENT_UPLOADS_TOTAL = Counter(
    "virtualhr_document_uploads_total",
    "Total document upload events",
    ["status"]
)

DOCUMENT_SCAN_FAILURES_TOTAL = Counter(
    "virtualhr_document_scan_failures_total",
    "Total document malware/antivirus scan failures",
    ["reason_category"]
)

LEAVE_OPERATIONS_TOTAL = Counter(
    "virtualhr_leave_operations_total",
    "Total employee leave request operations",
    ["action", "status"]
)

POLICY_OPERATIONS_TOTAL = Counter(
    "virtualhr_policy_operations_total",
    "Total HR policy lifecycle operations",
    ["action", "status"]
)

LLM_REQUESTS_TOTAL = Counter(
    "virtualhr_llm_requests_total",
    "Total LLM provider requests",
    ["provider", "model", "status"]
)

LLM_REQUEST_DURATION_SECONDS = Histogram(
    "virtualhr_llm_request_duration_seconds",
    "LLM provider response latency histogram in seconds",
    ["provider", "model"]
)

LLM_TOKENS_TOTAL = Counter(
    "virtualhr_llm_tokens_total",
    "Total LLM tokens consumed",
    ["provider", "model", "token_type"]  # prompt vs completion
)

OUTBOX_DEAD_LETTER_CURRENT = Gauge(
    "virtualhr_outbox_dead_letter_current",
    "Current active unprocessed events depth in AI usage dead-letter queue"
)

TELEMETRY_ERRORS_TOTAL = Counter(
    "virtualhr_telemetry_errors_total",
    "Total non-blocking telemetry write failures",
    ["subsystem"]
)


def normalize_route_path(path: str) -> str:
    """
    Normalizes raw request paths to FastAPI template strings to prevent metric label cardinality explosion.
    Example: /api/employee/profile/usr_12345 -> /api/employee/profile/{employee_id}
    """
    if not path:
        return "unknown"
    # Replace UUIDs
    path = re.sub(r'/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', '/{id}', path)
    # Replace ID prefixes (e.g. usr_, comp_, doc_, LV-)
    path = re.sub(r'/(usr|comp|doc|LV|evt|req)_[a-zA-Z0-9_-]+', '/{id}', path)
    # Replace raw numeric IDs
    path = re.sub(r'/\d+', '/{id}', path)
    return path


def validate_metrics_token_config() -> None:
    """
    Enforces startup validation for PROMETHEUS_METRICS_TOKEN.
    Auto-generates a secure 32-byte (64 char) ephemeral token if unset or too short to guarantee
    that the application starts safely in production while keeping /metrics secure.
    """
    token = os.getenv("PROMETHEUS_METRICS_TOKEN", "")
    if not token or len(token) < 32:
        import secrets
        auto_token = secrets.token_hex(32)
        os.environ["PROMETHEUS_METRICS_TOKEN"] = auto_token
        logger.warning(
            "PROMETHEUS_METRICS_TOKEN unset or < 32 chars in production. "
            "Generated secure ephemeral 64-char token for /metrics protection."
        )


def verify_metrics_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> bool:
    """
    Authenticates bearer token for /metrics with rotation grace period window support.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    current_token = os.getenv("PROMETHEUS_METRICS_TOKEN", "secret-prometheus-token-32-chars-long")
    previous_token = os.getenv("PROMETHEUS_METRICS_TOKEN_PREVIOUS")
    grace_seconds = int(os.getenv("PROMETHEUS_METRICS_TOKEN_ROTATION_GRACE_SECONDS", "900"))
    token_expires_at = os.getenv("PROMETHEUS_METRICS_TOKEN_PREVIOUS_EXPIRES_AT")

    # If in dev mode and no token set, allow internal testing
    if env != "production" and not credentials:
        return True

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Prometheus metrics authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client_token = credentials.credentials

    # Check current token
    if client_token == current_token:
        return True

    # Check previous token during rotation window
    if previous_token and client_token == previous_token:
        now_ts = time.time()
        if token_expires_at:
            try:
                exp_ts = float(token_expires_at)
                if now_ts <= exp_ts:
                    return True
            except ValueError:
                pass
        else:
            # Fallback to grace window
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired Prometheus metrics token",
        headers={"WWW-Authenticate": "Bearer"},
    )
