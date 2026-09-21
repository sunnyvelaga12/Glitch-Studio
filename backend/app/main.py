"""
main.py — FastAPI application for the Glitch HR Intelligence API.
"""

import logging
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from contextlib import asynccontextmanager
import json

from app.config import settings
from app.schemas import ChatRequest, ChatResponse
from app.bot import (
    AIRateLimitError,
    AIServiceError,
    generate_bot_response,
    close_groq_client,
    stream_groq_response,
    construct_hr_system_prompt,
    check_algorithmic_guardrails,
)
from app.routes_auth import router as auth_router
from app.routes_hr import router as hr_router, v1_hr_router
from app.routes_document_ingest import router as document_router
from app.routes_employee import router as employee_router
from app.routes_admin import router as admin_router
from app.deps import get_current_user
from app.db import get_db
from app.company_policies import (
    get_company_policy_document_text,
    get_company_policy_text_with_rag,
    get_employee_context,
)
from app.cache import rate_limiter, cache_key_for_query, response_cache
from app.utils import generate_request_id, sanitize_input, StructuredLogger

from app.logging_config import setup_logging
from app.middleware_tracing import RequestTracingMiddleware
from app.metrics import (
    validate_metrics_token_config,
    verify_metrics_token,
    normalize_route_path,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
    LLM_REQUEST_DURATION_SECONDS,
    LLM_TOKENS_TOTAL,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from app.sentry_integration import init_sentry
from app.ai_cost_tracker import record_ai_usage_event_outbox

# ---------------------------------------------------------------------------
# Logging & Sentry Initialisation
# ---------------------------------------------------------------------------
setup_logging(level=settings.LOG_LEVEL, environment=settings.ENVIRONMENT)
init_sentry(environment=settings.ENVIRONMENT)
std_logger = logging.getLogger(__name__)
logger = StructuredLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    std_logger.info("Starting VirtualHR API (v1.0.0)", extra={"environment": settings.ENVIRONMENT})
    
    # Enforce fail-fast security checks
    settings.validate_jwt_secret_on_startup()
    validate_metrics_token_config()

    if not settings.is_api_configured:
        std_logger.warning(
            "AI provider not configured — /api/chat will return 503"
        )

    # Initialize MongoDB database indexes
    try:
        from app.db import ensure_indexes
        await ensure_indexes()
    except Exception as exc:
        std_logger.warning(f"Failed to trigger index creation on startup: {exc}")

    yield

    std_logger.info("Shutting down VirtualHR API")
    close_groq_client()
    std_logger.info("Resources cleaned up")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="VirtualHR API",
    description="Your AI HR Department — Multi-tenant HR Management & Policy Intelligence API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware — request tracking (registered FIRST = innermost at runtime)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = generate_request_id()
    request.state.request_id = request_id

    # ✅ FIX: Safe IP extraction with full fallback chain
    forwarded_for = request.headers.get("X-Forwarded-For")
    real_ip = request.headers.get("X-Real-IP")

    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    elif real_ip:
        client_ip = real_ip.strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "unknown"

    request.state.client_ip = client_ip

    # Rate limiting
    if not rate_limiter.is_allowed(client_ip):
        std_logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"X-Request-ID": request_id},
            content={
                "detail": "Too many requests. Rate limit exceeded.",
                "request_id": request_id,
            },
        )

    try:
        response = await call_next(request)
    except Exception as exc:
        std_logger.error(f"Unhandled exception in request pipeline: {exc}", exc_info=True)
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": f"Internal Server Error: {str(exc)}" if settings.is_development else "An internal server error occurred."
            },
        )

    try:
        remaining = rate_limiter.get_remaining_requests(client_ip)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-RateLimit-Remaining"] = str(remaining.get("remaining_per_minute", 60))
    except Exception as exc:
        std_logger.warning(f"Failed setting response headers in middleware: {exc}")

    return response


# ---------------------------------------------------------------------------
# CORS — registered LAST = outermost at runtime
# ✅ This ensures CORS headers appear on ALL responses including 500s
# ---------------------------------------------------------------------------
CORS_ORIGINS = settings.allowed_origins_list or []

# Always ensure local dev origins (ports 3000, 3005) and matching localhost/127.0.0.1 pairs are allowed
_extra = []
for origin in list(CORS_ORIGINS):
    if "localhost:" in origin:
        port = origin.split("localhost:")[-1]
        alt = f"http://127.0.0.1:{port}"
        if alt not in CORS_ORIGINS:
            _extra.append(alt)
    elif "127.0.0.1:" in origin:
        port = origin.split("127.0.0.1:")[-1]
        alt = f"http://localhost:{port}"
        if alt not in CORS_ORIGINS:
            _extra.append(alt)

for default_origin in ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3005", "http://127.0.0.1:3005"]:
    if default_origin not in CORS_ORIGINS:
        _extra.append(default_origin)

CORS_ORIGINS = list(set(CORS_ORIGINS + _extra))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=3600,
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(hr_router)
app.include_router(v1_hr_router)
app.include_router(document_router)
app.include_router(employee_router)


from app.middleware_security import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestTracingMiddleware)

# ---------------------------------------------------------------------------
# Health checks (Liveness, Readiness, & Dependencies)
# ---------------------------------------------------------------------------
@app.get("/health", status_code=status.HTTP_200_OK, tags=["Operations"])
@app.get("/health/liveness", status_code=status.HTTP_200_OK, tags=["Operations"])
async def health_liveness(request: Request):
    """Liveness probe: verifies process responsiveness."""
    return {
        "status": "alive",
        "product": settings.PRODUCT_NAME,
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0"
    }

@app.get("/health/readiness", status_code=status.HTTP_200_OK, tags=["Operations"])
async def health_readiness(request: Request):
    """
    Readiness probe: verifies core database connectivity and transaction capability using modern 'hello' command.
    """
    db_connected = False
    transaction_supported = False
    try:
        from app.db import get_db
        mongodb = get_db()
        hello_res = await mongodb.command("hello")
        db_connected = True
        # Verify replica set topology or transaction support
        transaction_supported = bool(hello_res.get("setName") or hello_res.get("msg") == "isdbgrid" or hello_res.get("isWritablePrimary", True))
    except Exception as exc:
        std_logger.warning(f"Database readiness check failed: {exc}")

    is_ready = db_connected
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "database_connected": db_connected,
            "transaction_supported": transaction_supported,
            "environment": settings.ENVIRONMENT
        },
    )

@app.get("/health/dependencies", status_code=status.HTTP_200_OK, tags=["Operations"])
async def health_dependencies(authenticated: bool = Depends(verify_metrics_token)):
    """
    Protected dependency health probe: verifies operational status of optional feature dependencies.
    """
    dependencies = {}
    
    # 1. MongoDB check
    try:
        from app.db import get_db
        mongodb = get_db()
        await mongodb.command("ping")
        dependencies["mongodb"] = {"status": "healthy"}
    except Exception as e:
        dependencies["mongodb"] = {"status": "unhealthy", "error": str(e)}

    # 2. Storage check
    try:
        from app.storage_service import get_storage_service
        storage = get_storage_service()
        dependencies["object_storage"] = {"status": "healthy", "provider": getattr(storage, "provider_name", "local")}
    except Exception as e:
        dependencies["object_storage"] = {"status": "unhealthy", "error": str(e)}

    # 3. ClamAV check
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("localhost", 3310))
        s.close()
        dependencies["clamav"] = {"status": "healthy"}
    except Exception:
        dependencies["clamav"] = {"status": "degraded", "message": "antivirus socket unreachable"}

    # 4. LLM Configuration Check (No paid API call!)
    dependencies["llm_provider"] = {
        "status": "healthy" if settings.is_api_configured else "unconfigured",
        "provider": settings.active_provider,
        "configured": settings.is_api_configured
    }

    is_all_healthy = all(d["status"] == "healthy" for d in dependencies.values())
    return {
        "status": "healthy" if is_all_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": dependencies
    }

@app.get("/metrics", tags=["Operations"])
async def prometheus_metrics(authenticated: bool = Depends(verify_metrics_token)):
    """
    Exposes low-cardinality Prometheus operational metrics.
    Secured by PROMETHEUS_METRICS_TOKEN bearer token.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)



# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(
    request: ChatRequest,
    http_request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Send a user message and receive an HR-policy-grounded response.
    - 200  Success
    - 422  Validation error
    - 429  Rate limit exceeded
    - 503  API key not configured
    - 500  Unexpected error
    """
    request_id = getattr(http_request.state, "request_id", "unknown")
    client_ip = getattr(http_request.state, "client_ip", "unknown")

    logger.info(
        "Chat request received",
        request_id=request_id,
        client_ip=client_ip,
        message_len=len(request.message),
        history_len=len(request.history),
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    company_id = user.get("companyId")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing companyId in token",
        )

    if not settings.is_api_configured:
        logger.info("AI provider not configured — using local database/RAG fallback", request_id=request_id)

    try:
        sanitized_message = sanitize_input(request.message, max_length=4000)
    except ValueError as exc:
        logger.warning(f"Invalid user input: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    try:
        user_role = user.get("role", "employee")
        user_id = user.get("sub") or user.get("id")
        user_email = user.get("email") or ""

        db_instance = get_db()
        comp_doc = await db_instance.companies.find_one({"_id": company_id})
        comp_name = (comp_doc.get("name") if comp_doc else None) or company_id
        comp_hr_email = f"hr@{company_id}.com"

        emp_ctx_dict, emp_ctx_text = await get_employee_context(company_id, user_id, user_email)

        policy_document_text = await get_company_policy_text_with_rag(
            company_id,
            sanitized_message,
            role=user_role,
            user_id=user_id,
            user_email=user_email,
            employee_context=emp_ctx_dict,
        )
        bot_reply = generate_bot_response(
            message=sanitized_message,
            history=request.history,
            policy_document_text=policy_document_text,
            employee_context_text=emp_ctx_text,
            employee_context_dict=emp_ctx_dict,
            company_name=comp_name,
            hr_email=comp_hr_email,
            company_id=company_id,
            user_id=user_id,
            role=user_role,
        )
        logger.info("Chat response generated", request_id=request_id, response_len=len(bot_reply))

        # Log query to MongoDB with exact real employee identity
        try:
            from app.db import get_db
            from datetime import datetime, timezone
            db = get_db()
            user_id = user.get("sub") or user.get("id")
            user_email = user.get("email") or ""
            employee_name = user.get("fullName") or user.get("name") or ""
            
            if user_id:
                u_doc = await db.users.find_one({"_id": user_id})
                if u_doc:
                    employee_name = u_doc.get("fullName") or u_doc.get("name") or employee_name
                    if not user_email:
                        user_email = u_doc.get("email", "")
                elif "@" in str(user_id):
                    u_doc = await db.users.find_one({"email": user_id})
                    if u_doc:
                        employee_name = u_doc.get("fullName") or u_doc.get("name") or employee_name
                        user_email = u_doc.get("email", "")

            if not employee_name or employee_name == "User":
                employee_name = user_email.split("@")[0].replace(".", " ").title() if user_email else "Employee"

            await db.query_logs.insert_one({
                "company_id": company_id,
                "user_id": user_id,
                "user_email": user_email,
                "employee_name": employee_name,
                "role": user_role,
                "question": sanitized_message,
                "answer": bot_reply,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as log_exc:
            std_logger.error(f"Failed to log query: {log_exc}")

        # Record AI Usage Event to Durable Outbox with WriteConcern(w="majority", j=True)
        # Failure blocks response with HTTP 503 to guarantee AI accounting safety
        prompt_tokens = len(sanitized_message.split()) * 2  # Estimate or provider tokens
        completion_tokens = len(bot_reply.split()) * 2
        await record_ai_usage_event_outbox(
            company_id=company_id,
            user_id=str(user_id),
            request_id=request_id,
            provider=settings.active_provider,
            model="gemini-1.5-pro",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            execution_time_ms=120.0
        )

        return ChatResponse(response=bot_reply)

    except AIRateLimitError as exc:
        logger.warning(f"Rate-limit error: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API provider rate limit exceeded. Please try again later.",
        )
    except AIServiceError as exc:
        logger.error(f"AI service error: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service error. Please try again later.",
        )
    except ValueError as exc:
        logger.error(f"Configuration error: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service configuration error. Please contact administrator.",
        )
    except Exception as exc:
        logger.error(f"Unhandled error in /api/chat: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )


# ---------------------------------------------------------------------------
# Level 6: Server-Sent Events (SSE) Streaming Chat Endpoint
# ---------------------------------------------------------------------------
@app.post("/api/chat/stream", tags=["Chat"])
async def chat_stream_endpoint(
    request: ChatRequest,
    http_request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Level 6: Asynchronous streaming endpoint using Server-Sent Events (SSE).
    Orchestrates:
    - Step 1: Preemptive Algorithmic guardrails check.
    - Step 2: Level 5 Hybrid Retrieval (Dense Pinecone + Lexical MongoDB with RRF).
    - Step 3: Fetch Parent Chunks from MongoDB Atlas for compaction.
    - Step 4: Fetch Real-Time DB State for the Employee (balances, manager).
    - Step 5: Streaming generation via AsyncGroq with llama-3.3-70b-versatile (temp=0.0).
    """
    request_id = getattr(http_request.state, "request_id", "unknown")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    company_id = user.get("companyId") or user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing companyId in token")

    try:
        sanitized_message = sanitize_input(request.message, max_length=4000)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Step 1: Preemptive Algorithmic Guardrails
    refusal = check_algorithmic_guardrails(sanitized_message)
    if refusal:
        async def stream_refusal():
            payload = json.dumps({"token": refusal})
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            stream_refusal(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
        )

    # Step 2 & 3: Level 5 Hybrid Search with RRF and Parent Chunks
    from app.hybrid_search import execute_hybrid_search
    hybrid_res = await execute_hybrid_search(company_id=company_id, query=sanitized_message)

    if hybrid_res.get("status") == "fallback":
        fallback_text = hybrid_res.get("fallback_message") or (
            f"I could not find a specific policy matching your query. "
            f"Please open a ticket with the HR department at hr@glitch.com."
        )
        async def stream_fallback():
            payload = json.dumps({"token": fallback_text})
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            stream_fallback(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
        )

    context_payload = hybrid_res.get("context_text", "")
    disclaimer_required = hybrid_res.get("disclaimer_required", False)

    # Step 4: Real-time Employee Profile from MongoDB
    user_id = user.get("sub") or user.get("id")
    user_email = user.get("email") or ""
    emp_ctx_dict, _ = await get_employee_context(company_id, user_id, user_email)

    system_prompt = construct_hr_system_prompt(
        employee_state=emp_ctx_dict,
        retrieved_context=context_payload,
        disclaimer_required=disclaimer_required,
    )

    # Step 5: Build conversation messages and initiate streaming
    history_messages = [
        {"role": "user" if msg.role == "user" else "assistant", "content": msg.content}
        for msg in (request.history or [])[-6:]
    ]
    messages = [
        {"role": "system", "content": system_prompt},
        *history_messages,
        {"role": "user", "content": sanitized_message},
    ]

    return StreamingResponse(
        stream_groq_response(messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Global Exception Handlers (ensures CORS headers on all error responses)
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None) or generate_request_id()
    
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        content = exc.detail
        if isinstance(content.get("error"), dict) and not content["error"].get("request_id"):
            content["error"]["request_id"] = request_id
    else:
        code_map = {
            400: "INVALID_REQUEST",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "LEAVE_STATE_CONFLICT" if "leave" in str(exc.detail).lower() or "state" in str(exc.detail).lower() else "STATE_CONFLICT",
            429: "RATE_LIMITED",
            503: "SERVICE_UNAVAILABLE",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        content = {
            "error": {
                "code": code,
                "message": str(exc.detail),
                "request_id": request_id,
            },
            "detail": exc.detail,
        }

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=getattr(exc, "headers", None),
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    std_logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": f"Internal Server Error: {str(exc)}" if settings.is_development else "An internal server error occurred."
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation error", "detail": exc.errors()},
    )


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=9000, reload=True)