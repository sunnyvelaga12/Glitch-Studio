import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError, OperationFailure
from pymongo.write_concern import WriteConcern
from app.db import get_db
from app.metrics import OUTBOX_DEAD_LETTER_CURRENT, TELEMETRY_ERRORS_TOTAL

logger = logging.getLogger("virtualhr.ai_cost_tracker")

# Default Pricing Registry Fallback Table (USD per 1M tokens)
DEFAULT_MODEL_PRICING = {
    "gemini": {
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "default": {"input": 1.00, "output": 3.00}
    },
    "openai": {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "default": {"input": 2.00, "output": 8.00}
    }
}

async def add_pricing_version(
    provider: str,
    model: str,
    pricing_version: str,
    input_price_per_1m_tokens: float,
    output_price_per_1m_tokens: float,
    effective_from: datetime,
    effective_until: Optional[datetime] = None,
    currency: str = "USD"
) -> Dict[str, Any]:
    """
    Concurrency-safe transactional pricing version creation.
    Acquires lock on ai_pricing_locks and validates non-overlapping interval logic.
    """
    db = get_db()
    client = db.client
    provider_clean = provider.lower()
    model_clean = model.lower()

    # Ensure effective_from & effective_until are UTC datetime objects
    if effective_from.tzinfo is None:
        effective_from = effective_from.replace(tzinfo=timezone.utc)
    if effective_until and effective_until.tzinfo is None:
        effective_until = effective_until.replace(tzinfo=timezone.utc)

    if effective_until and effective_from >= effective_until:
        raise HTTPException(status_code=400, detail="effective_from must be earlier than effective_until")

    # Transactional pricing creation with lock serialization and bounded retries
    max_retries = 5
    for attempt in range(max_retries):
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    # 1. Acquire lock on ai_pricing_locks
                    lock_id = f"{provider_clean}_{model_clean}"
                    await db.ai_pricing_locks.update_one(
                        {"_id": lock_id},
                        {
                            "$set": {
                                "provider": provider_clean,
                                "model": model_clean,
                                "locked_at": datetime.now(timezone.utc)
                            }
                        },
                        upsert=True,
                        session=session
                    )

                    # 2. Overlap validation query
                    cursor = db.ai_pricing_registry.find(
                        {"provider": provider_clean, "model": model_clean},
                        session=session
                    )
                    existing_records = await cursor.to_list(length=100)

                    for rec in existing_records:
                        ex_from = rec["effective_from"]
                        if ex_from.tzinfo is None:
                            ex_from = ex_from.replace(tzinfo=timezone.utc)
                        ex_until = rec.get("effective_until")
                        if ex_until and ex_until.tzinfo is None:
                            ex_until = ex_until.replace(tzinfo=timezone.utc)

                        # Overlap check: existing.from < new.until AND (existing.until IS NULL OR existing.until > new.from)
                        overlap_cond1 = (effective_until is None) or (ex_from < effective_until)
                        overlap_cond2 = (ex_until is None) or (ex_until > effective_from)

                        if overlap_cond1 and overlap_cond2:
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=f"Pricing version date range overlaps with existing pricing version '{rec.get('pricing_version')}'"
                            )

                    # 3. Insert new pricing version
                    doc_id = f"pricing_{provider_clean}_{model_clean}_{pricing_version}"
                    pricing_doc = {
                        "_id": doc_id,
                        "provider": provider_clean,
                        "model": model_clean,
                        "pricing_version": pricing_version,
                        "input_price_per_1m_tokens": input_price_per_1m_tokens,
                        "output_price_per_1m_tokens": output_price_per_1m_tokens,
                        "currency": currency,
                        "effective_from": effective_from,
                        "effective_until": effective_until,
                        "created_at": datetime.now(timezone.utc)
                    }
                    await db.ai_pricing_registry.insert_one(pricing_doc, session=session)
                    return pricing_doc
        except HTTPException:
            raise
        except (OperationFailure, Exception) as err:
            if attempt == max_retries - 1:
                raise err
            import random
            await asyncio.sleep(0.05 * (2 ** attempt) + random.uniform(0.01, 0.05))

async def get_active_pricing(provider: str, model: str, dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Fetches active pricing from ai_pricing_registry for a given provider, model, and timestamp.
    Falls back to default pricing table if no database record exists.
    """
    db = get_db()
    provider_clean = provider.lower()
    model_clean = model.lower()
    target_dt = dt or datetime.now(timezone.utc)
    if target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=timezone.utc)

    # Search database registry
    query = {
        "provider": provider_clean,
        "model": model_clean,
        "effective_from": {"$lte": target_dt},
        "$or": [
            {"effective_until": None},
            {"effective_until": {"$gt": target_dt}}
        ]
    }
    rec = await db.ai_pricing_registry.find_one(query, sort=[("effective_from", -1)])
    if rec:
        return rec

    # Fallback to in-memory default rates
    prov_defaults = DEFAULT_MODEL_PRICING.get(provider_clean, DEFAULT_MODEL_PRICING["gemini"])
    rates = prov_defaults.get(model_clean, prov_defaults["default"])
    return {
        "provider": provider_clean,
        "model": model_clean,
        "pricing_version": "fallback_default",
        "input_price_per_1m_tokens": rates["input"],
        "output_price_per_1m_tokens": rates["output"],
        "currency": "USD"
    }

async def record_ai_usage_event_outbox(
    company_id: str,
    user_id: str,
    request_id: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    execution_time_ms: float = 0.0
) -> str:
    """
    Durably writes usage event to ai_usage_events outbox with WriteConcern(w="majority", j=True).
    MUST complete synchronously before API handler returns successful HTTP response!
    """
    db = get_db()
    event_id = f"evt-{uuid.uuid4()}"
    now_utc = datetime.now(timezone.utc)

    event_doc = {
        "_id": event_id,
        "event_id": event_id,
        "company_id": company_id,
        "user_id": user_id,
        "request_id": request_id,
        "timestamp": now_utc,
        "provider": provider.lower(),
        "model": model.lower(),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "execution_time_ms": execution_time_ms,
        "status": "PENDING",
        "lease_token": None,
        "lease_expires_at": None,
        "attempt_count": 0,
        "next_attempt_at": now_utc,
        "created_at": now_utc
    }

    try:
        # Enforce majority durable write concern
        coll = db.ai_usage_events.with_options(write_concern=WriteConcern(w="majority", j=True))
        await coll.insert_one(event_doc)
        logger.info(f"AI usage event persisted to durable outbox: {event_id}")
        return event_id
    except Exception as e:
        logger.error(f"Failed to persist AI usage event to durable outbox: {str(e)}")
        TELEMETRY_ERRORS_TOTAL.labels(subsystem="ai_outbox").inc()
        # Per specification: Outbox failure blocks AI response for accounting safety!
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI usage telemetry persistence failed; operation aborted for accounting safety"
        )

async def process_outbox_event(event: Dict[str, Any]) -> bool:
    """
    Processes a claimed outbox event atomically using a MongoDB transaction.
    Guarantees exactly one committed accounting effect in tenant_usage, preventing double-counting on retries.
    """
    db = get_db()
    client = db.client
    event_id = event["event_id"]
    company_id = event["company_id"]
    user_id = event["user_id"]
    request_id = event["request_id"]
    provider = event["provider"]
    model = event["model"]
    prompt_tokens = event["prompt_tokens"]
    completion_tokens = event["completion_tokens"]
    total_tokens = event["total_tokens"]
    event_ts = event["timestamp"]
    if event_ts.tzinfo is None:
        event_ts = event_ts.replace(tzinfo=timezone.utc)

    billing_period = event_ts.strftime("%Y-%m")

    # Fetch active pricing version
    pricing = await get_active_pricing(provider, model, event_ts)
    input_rate = pricing["input_price_per_1m_tokens"]
    output_rate = pricing["output_price_per_1m_tokens"]

    # Calculate estimated USD cost
    cost_usd = round(
        (prompt_tokens * input_rate / 1_000_000.0) + (completion_tokens * output_rate / 1_000_000.0),
        7
    )

    usage_log_doc = {
        "_id": event_id,
        "event_id": event_id,
        "company_id": company_id,
        "user_id": user_id,
        "request_id": request_id,
        "timestamp": event_ts,
        "billing_period": billing_period,
        "provider": provider,
        "model": model,
        "pricing_version": pricing.get("pricing_version", "unknown"),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "usage_source": "provider_reported",
        "input_rate_per_1m": input_rate,
        "output_rate_per_1m": output_rate,
        "estimated_cost_usd": cost_usd,
        "cost_status": "calculated",
        "execution_time_ms": event.get("execution_time_ms", 0.0),
        "created_at": datetime.now(timezone.utc)
    }

    # Bounded retries for transient transaction errors
    max_retries = 15
    for attempt in range(max_retries):
        is_duplicate = False
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    # 1. Insert into ai_usage_logs (unique event_id index checks for double-counting)
                    try:
                        await db.ai_usage_logs.insert_one(usage_log_doc, session=session)
                    except DuplicateKeyError:
                        is_duplicate = True
                        await session.abort_transaction()

                    if is_duplicate:
                        break

                    # 2. Atomic rollup on tenant_usage ($inc)
                    tenant_usage_id = f"{company_id}_{billing_period}"
                    await db.tenant_usage.update_one(
                        {"_id": tenant_usage_id},
                        {
                            "$set": {
                                "company_id": company_id,
                                "billing_period": billing_period,
                                "updated_at": datetime.now(timezone.utc)
                            },
                            "$inc": {
                                "ai_requests": 1,
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                                "total_tokens": total_tokens,
                                "estimated_ai_cost_usd": cost_usd
                            }
                        },
                        upsert=True,
                        session=session
                    )

                    # 3. Mark outbox event COMPLETED
                    await db.ai_usage_events.update_one(
                        {"_id": event_id},
                        {"$set": {"status": "COMPLETED", "completed_at": datetime.now(timezone.utc)}},
                        session=session
                    )
                    return True
        except (OperationFailure, Exception) as err:
            if attempt == max_retries - 1:
                logger.error(f"Transaction failed after {max_retries} attempts for event {event_id}: {str(err)}")
                raise err
            import random
            await asyncio.sleep(0.05 * (2 ** attempt) + random.uniform(0.01, 0.05))

    if is_duplicate:
        await db.ai_usage_events.update_one(
            {"_id": event_id},
            {"$set": {"status": "COMPLETED", "completed_at": datetime.now(timezone.utc)}}
        )
        return True

    return False

async def run_outbox_worker_single_pass() -> int:
    """
    Executes a single processing pass over pending/failed/expired outbox events.
    Claims events with lease tokens and processes them transactionally.
    """
    db = get_db()
    now_utc = datetime.now(timezone.utc)
    lease_expiry = now_utc + timedelta(seconds=60)
    worker_lease_id = f"worker-{uuid.uuid4()}"

    processed_count = 0
    # Query pending, failed, or expired processing leases
    query = {
        "$or": [
            {"status": {"$in": ["PENDING", "FAILED"]}, "next_attempt_at": {"$lte": now_utc}},
            {"status": "PROCESSING", "lease_expires_at": {"$lt": now_utc}}
        ],
        "attempt_count": {"$lt": 5}
    }

    max_batch = 50
    while processed_count < max_batch:
        claimed_event = await db.ai_usage_events.find_one_and_update(
            query,
            {
                "$set": {
                    "status": "PROCESSING",
                    "lease_token": worker_lease_id,
                    "lease_expires_at": lease_expiry
                },
                "$inc": {"attempt_count": 1}
            }
        )

        if not claimed_event:
            break

        event_id = claimed_event["event_id"]
        attempt_count = claimed_event.get("attempt_count", 1)

        try:
            success = await process_outbox_event(claimed_event)
            if success:
                processed_count += 1
        except Exception as e:
            logger.error(f"Error processing outbox event {event_id} (attempt {attempt_count}): {str(e)}")
            next_attempt = now_utc + timedelta(seconds=min(300, (2 ** attempt_count) * 5))
            if attempt_count >= 5:
                # Transition to DEAD_LETTER and update Gauge
                await db.ai_usage_events.update_one(
                    {"_id": event_id},
                    {"$set": {"status": "DEAD_LETTER", "last_error": str(e), "failed_at": now_utc}}
                )
                await update_dlq_gauge()
            else:
                await db.ai_usage_events.update_one(
                    {"_id": event_id},
                    {"$set": {"status": "FAILED", "last_error": str(e), "next_attempt_at": next_attempt}}
                )

    await update_dlq_gauge()
    return processed_count

async def update_dlq_gauge() -> int:
    """
    Updates the Prometheus OUTBOX_DEAD_LETTER_CURRENT Gauge with active DLQ depth.
    """
    db = get_db()
    dlq_count = await db.ai_usage_events.count_documents({"status": "DEAD_LETTER"})
    OUTBOX_DEAD_LETTER_CURRENT.set(dlq_count)
    return dlq_count

async def get_dead_letter_events(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves events currently in DEAD_LETTER state.
    """
    db = get_db()
    cursor = db.ai_usage_events.find({"status": "DEAD_LETTER"}).limit(limit)
    return await cursor.to_list(length=limit)

async def replay_dead_letter_event(event_id: str) -> bool:
    """
    Replays a dead-letter event by resetting status to PENDING and attempt_count to 0.
    """
    db = get_db()
    res = await db.ai_usage_events.update_one(
        {"_id": event_id, "status": "DEAD_LETTER"},
        {
            "$set": {
                "status": "PENDING",
                "attempt_count": 0,
                "next_attempt_at": datetime.now(timezone.utc)
            }
        }
    )
    await update_dlq_gauge()
    return res.modified_count > 0
