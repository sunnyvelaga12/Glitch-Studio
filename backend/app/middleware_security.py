import secrets
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("virtualhr.security_middleware")

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Production Security Headers & Cryptographic Nonce-based CSP Middleware.
    Injects per-request cryptographic nonces and production security headers into all HTTP responses.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate per-request cryptographic nonce (16 bytes hex string = 32 chars)
        request_nonce = secrets.token_hex(16)
        request.state.csp_nonce = request_nonce

        response = await call_next(request)

        # Inject Security Headers
        response.headers["X-Request-Nonce"] = request_nonce
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Per-request cryptographic nonce-based Content-Security-Policy (omitting unsafe-inline!)
        csp_policy = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{request_nonce}'; "
            f"style-src 'self' 'nonce-{request_nonce}'; "
            f"img-src 'self' data: blob:; "
            f"font-src 'self'; "
            f"connect-src 'self'; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"frame-ancestors 'none'; "
            f"form-action 'self'; "
            f"upgrade-insecure-requests;"
        )
        response.headers["Content-Security-Policy"] = csp_policy

        return response
