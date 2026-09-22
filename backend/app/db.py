import logging
import os
from urllib.parse import quote_plus

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_mongodb_client():
    """Create (or reuse) an async MongoDB client with pooling.

    Uses motor (async). We keep a module-level singleton so the app can
    reuse connections efficiently.

    To avoid RFC 3986 escaping issues (e.g. @ : / ? # % in usernames/passwords),
    credentials are read from separate env vars and URL-encoded.
    """
    import asyncio
    global _client

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _client is not None:
        try:
            client_loop = _client.get_io_loop()
            if client_loop.is_closed() or (current_loop is not None and client_loop is not current_loop):
                _client = None
            else:
                return _client
        except Exception:
            _client = None

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError as exc:
        raise RuntimeError(
            "motor is not installed. Install backend dependencies before running."
        ) from exc

    # Backward compatible fallback: if MONGODB_URI is explicitly provided,
    # use it as-is.
    fallback_uri = os.getenv("MONGODB_URI") or settings.__dict__.get("MONGODB_URI")

    mongo_user = os.getenv("MONGO_USER") or settings.__dict__.get("MONGO_USER", "")
    mongo_password = os.getenv("MONGO_PASSWORD") or settings.__dict__.get(
        "MONGO_PASSWORD", ""
    )
    mongo_host = os.getenv("MONGO_HOST") or settings.__dict__.get("MONGO_HOST", "")
    mongo_db = os.getenv("MONGO_DB") or settings.__dict__.get("MONGO_DB", "")

    mongo_auth_source = os.getenv("MONGO_AUTH_SOURCE") or settings.__dict__.get(
        "MONGO_AUTH_SOURCE", ""
    )

    # Prefer separated credentials when present; otherwise fall back.
    if mongo_user and mongo_password and mongo_host and mongo_db:
        quoted_user = quote_plus(mongo_user)
        quoted_password = quote_plus(mongo_password)

        # Construct final URI safely.
        # Host should typically look like: cluster0.xxxxx.mongodb.net
        # (without scheme).
        auth_source_qs = (
            f"&authSource={quote_plus(mongo_auth_source)}"
            if mongo_auth_source
            else ""
        )
        uri = (
            f"mongodb+srv://{quoted_user}:{quoted_password}@{mongo_host}/{mongo_db}"
            f"?retryWrites=true&w=majority{auth_source_qs}"
        )
    else:
        if not fallback_uri:
            missing = [
                "MONGO_USER",
                "MONGO_PASSWORD",
                "MONGO_HOST",
                "MONGO_DB",
            ]
            provided = {
                "MONGO_USER": bool(mongo_user),
                "MONGO_PASSWORD": bool(mongo_password),
                "MONGO_HOST": bool(mongo_host),
                "MONGO_DB": bool(mongo_db),
            }
            missing = [k for k, ok in provided.items() if not ok]
            raise RuntimeError(
                "MongoDB configuration is missing required env vars. "
                f"Missing: {', '.join(missing)}. "
                "Set separated vars (MONGO_USER, MONGO_PASSWORD, MONGO_HOST, MONGO_DB) "
                "to avoid URI escaping issues. "
                "Alternatively, set MONGODB_URI (may fail if username/password contain special characters)."
            )

        uri = fallback_uri

    # Initialize client with connection pooling and SSL configuration
    tls_allow_invalid = os.getenv("MONGO_TLS_ALLOW_INVALID_CERTS", "false").lower() in ("true", "1", "yes")
    if settings.is_development and "MONGO_TLS_ALLOW_INVALID_CERTS" not in os.environ:
        tls_allow_invalid = True

    tls_kwargs = {
        "tls": True,
        "tlsAllowInvalidCertificates": tls_allow_invalid,
    }
    try:
        import certifi

        tls_kwargs["tlsCAFile"] = certifi.where()
    except ImportError:
        pass

    _client = AsyncIOMotorClient(
        uri,
        maxPoolSize=100,
        minPoolSize=10,
        maxIdleTimeMS=45000,
        serverSelectionTimeoutMS=15000,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        **tls_kwargs,
    )
    logger.info("MongoDB client initialized with connection pooling")
    return _client


def get_db():
    """Return an async database handle.

    Mongo Atlas connection string should include a default database.
    If not, we fall back to 'hrbot'.
    """
    client = _get_mongodb_client()

    # motor/AsyncIOMotorClient exposes get_default_database() when DB is in URI.
    try:
        db = client.get_default_database()
        if db is not None:
            return db
    except Exception:
        pass

    return client["hrbot"]


async def ensure_indexes() -> None:
    """Initialize essential MongoDB database indexes asynchronously on application startup.
    
    Prevents full collection scans across multi-tenant data lookups.
    """
    db = get_db()
    logger.info("Initializing MongoDB database indexes...")

    async def safe_create_index(collection, keys, unique=False, name=None, **extra_kwargs):
        kwargs = {"unique": unique, "background": True, **extra_kwargs}
        if name:
            kwargs["name"] = name
        try:
            await collection.create_index(keys, **kwargs)
        except Exception:
            try:
                # Find and drop any existing index on matching keys
                info = await collection.index_information()
                key_tuples = [tuple(k) for k in keys]
                for idx_name, idx_spec in info.items():
                    spec_keys = [tuple(k) for k in idx_spec.get("key", [])]
                    if spec_keys == key_tuples:
                        await collection.drop_index(idx_name)
                        break
                await collection.create_index(keys, **kwargs)
            except Exception as drop_exc:
                logger.warning(f"Could not recreate index {keys}: {drop_exc}")


    try:
        # 1. users indexes (4 custom indexes)
        await safe_create_index(db.users, [("email", 1)])
        await safe_create_index(db.users, [("company_id", 1), ("email", 1)], unique=True, name="idx_users_company_email_unique")
        await safe_create_index(db.users, [("company_id", 1), ("role", 1)])
        await safe_create_index(db.users, [("company_id", 1), ("is_active", 1)])

        # 2. companies indexes (1 custom index)
        await safe_create_index(db.companies, [("passkey", 1)], unique=True, name="idx_companies_passkey_unique")

        # 3. sessions indexes (2 custom indexes)
        await safe_create_index(db.sessions, [("session_id", 1)], unique=True, name="idx_sessions_id_unique")
        await safe_create_index(db.sessions, [("user_id", 1), ("revoked_at", 1)])

        # 4. leave_requests indexes (2 custom indexes)
        await safe_create_index(db.leave_requests, [("company_id", 1), ("user_id", 1), ("status", 1)])
        await safe_create_index(db.leave_requests, [("company_id", 1), ("created_at", -1)])

        # 5. documents indexes (1 custom index)
        await safe_create_index(db.documents, [("company_id", 1), ("status", 1)])

        # 6. policy_versions indexes (2 custom indexes)
        await safe_create_index(db.policy_versions, [("company_id", 1), ("policy_id", 1), ("version_number", -1)], unique=True, name="idx_policy_versions_unique")
        await safe_create_index(db.policy_versions, [("company_id", 1), ("status", 1)])

        # 7. query_logs indexes (1 custom index)
        await safe_create_index(db.query_logs, [("company_id", 1), ("timestamp", -1)])

        # 8. attendance indexes (1 custom index)
        await safe_create_index(db.attendance, [("company_id", 1), ("user_id", 1), ("date", -1)])

        # 9. Phase 0-C Telemetry & AI Economics Indexes
        await safe_create_index(db.ai_pricing_locks, [("provider", 1), ("model", 1)], unique=True, name="idx_pricing_locks_unique")
        await safe_create_index(db.ai_usage_events, [("event_id", 1)], unique=True, name="idx_ai_usage_events_unique")
        await safe_create_index(db.ai_usage_events, [("status", 1), ("next_attempt_at", 1)])
        await safe_create_index(db.ai_usage_logs, [("event_id", 1)], unique=True, name="idx_ai_usage_logs_event_unique")
        await safe_create_index(db.ai_usage_logs, [("company_id", 1), ("timestamp", -1)])
        await safe_create_index(db.ai_usage_logs, [("company_id", 1), ("billing_period", 1)])
        await safe_create_index(db.ai_usage_logs, [("request_id", 1)])
        await safe_create_index(db.tenant_usage, [("company_id", 1), ("billing_period", 1)], unique=True, name="idx_tenant_usage_unique")
        await safe_create_index(db.ai_pricing_registry, [("provider", 1), ("model", 1), ("effective_from", -1)], unique=True, name="idx_pricing_registry_unique")
        await safe_create_index(db.audit_logs, [("event_id", 1)], unique=True, name="idx_audit_logs_event_id_unique")
        await safe_create_index(db.audit_logs, [("company_id", 1), ("timestamp", -1)])
        await safe_create_index(db.audit_logs, [("event_type", 1), ("timestamp", -1)])
        await safe_create_index(db.audit_logs, [("actor_user_id", 1), ("timestamp", -1)])

        # 10. Phase 1 HR Domain Indexes
        await safe_create_index(db.employees, [("company_id", 1), ("user_id", 1)], unique=True, name="idx_employees_company_user")
        await safe_create_index(db.employees, [("company_id", 1), ("department", 1)])
        await safe_create_index(db.employees, [("company_id", 1), ("manager_id", 1)])
        await safe_create_index(db.leave_balances, [("company_id", 1), ("user_id", 1), ("year", 1)], unique=True, name="idx_leave_balances_unique")
        await safe_create_index(db.document_chunks, [("company_id", 1), ("policy_id", 1), ("version_number", 1)], name="idx_chunks_policy")

        # 11. Stage 1.3 Idempotency Indexes
        await safe_create_index(
            db.idempotency_keys,
            [("company_id", 1), ("user_id", 1), ("endpoint", 1), ("idempotency_key", 1)],
            unique=True,
            name="idx_idempotency_unique"
        )
        await safe_create_index(
            db.idempotency_keys,
            [("created_at", 1)],
            expireAfterSeconds=172800,
            name="idx_idempotency_ttl"
        )

        # 12. Level 2 & Level 5 RAG Parent Chunks Indexes
        await safe_create_index(
            db.parent_chunks,
            [("company_id", 1), ("parent_id", 1)],
            unique=True,
            name="idx_parent_chunks_company_parent"
        )
        await safe_create_index(
            db.parent_chunks,
            [("company_id", 1), ("policy_code", 1)],
            name="idx_parent_chunks_company_policy"
        )
        await safe_create_index(
            db.parent_chunks,
            [("company_id", 1), ("doc_id", 1)],
            name="idx_parent_chunks_company_doc"
        )
        await safe_create_index(
            db.parent_chunks,
            [("text", "text"), ("header_breadcrumb", "text")],
            name="idx_parent_chunks_text_search"
        )

        # 13. Policy & Chunking High-Throughput Indexes
        await safe_create_index(db.policies, [("company_id", 1)], name="idx_policies_company_id")
        await safe_create_index(db.policies, [("companyId", 1)], name="idx_policies_companyId")
        await safe_create_index(db.document_chunks, [("company_id", 1), ("chunk_id", 1)], name="idx_document_chunks_company_chunk")

        logger.info("MongoDB database indexes initialized successfully (P0-A, P0-B, P0-C, Phase 1, Stage 1.3, RAG parent_chunks & policies).")
    except Exception as exc:
        logger.warning(f"Failed to create MongoDB indexes (non-fatal): {exc}")
