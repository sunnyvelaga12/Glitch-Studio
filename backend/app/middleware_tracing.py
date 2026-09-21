import re
import uuid
from contextvars import ContextVar
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# ContextVar storage for request tracing
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
company_id_var: ContextVar[Optional[str]] = ContextVar("company_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)

# Regex validation for X-Request-ID (prevent log injection)
REQUEST_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

def get_current_request_id() -> Optional[str]:
    return request_id_var.get()

def get_current_company_id() -> Optional[str]:
    return company_id_var.get()

def get_current_user_id() -> Optional[str]:
    return user_id_var.get()

def set_current_context(company_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    if company_id is not None:
        company_id_var.set(company_id)
    if user_id is not None:
        user_id_var.set(user_id)

class RequestTracingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for X-Request-ID validation and ContextVar propagation.
    - Validates incoming X-Request-ID against regex ^[A-Za-z0-9_-]{1,64}$.
    - Generates fresh UUIDv4 if invalid or missing.
    - Injects X-Request-ID into response headers.
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        inbound_req_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
        
        if inbound_req_id and REQUEST_ID_REGEX.match(inbound_req_id):
            req_id = inbound_req_id
        else:
            req_id = f"req-{uuid.uuid4()}"

        token_req = request_id_var.set(req_id)
        token_comp = company_id_var.set(None)
        token_user = user_id_var.set(None)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_var.reset(token_req)
            company_id_var.reset(token_comp)
            user_id_var.reset(token_user)
