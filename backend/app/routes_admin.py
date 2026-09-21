from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import get_current_user, require_role
from app.ai_cost_tracker import (
    add_pricing_version,
    get_dead_letter_events,
    replay_dead_letter_event,
)

router = APIRouter(prefix="/api/admin", tags=["Admin & Telemetry"])

class PricingCreateRequest(BaseModel):
    provider: str = Field(..., json_schema_extra={"example": "gemini"})
    model: str = Field(..., json_schema_extra={"example": "gemini-1.5-pro"})
    pricing_version: str = Field(..., json_schema_extra={"example": "v1.2026.08"})
    input_price_per_1m_tokens: float = Field(..., json_schema_extra={"example": 1.25})
    output_price_per_1m_tokens: float = Field(..., json_schema_extra={"example": 5.00})
    effective_from: datetime
    effective_until: Optional[datetime] = None
    currency: str = Field("USD")

@router.get("/ai-usage/dead-letters", response_model=List[Dict[str, Any]])
async def list_dlq_events(
    limit: int = 50,
    current_user: dict = Depends(require_role("hr_admin"))
):
    """
    List events currently in the AI usage dead-letter queue (DLQ).
    """
    return await get_dead_letter_events(limit=limit)

@router.post("/ai-usage/dead-letters/{event_id}/replay")
async def replay_dlq_event(
    event_id: str,
    current_user: dict = Depends(require_role("hr_admin"))
):
    """
    Replay a dead-letter event by resetting state to PENDING.
    """
    success = await replay_dead_letter_event(event_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dead-letter event '{event_id}' not found or not in DEAD_LETTER state"
        )
    return {"message": f"Dead-letter event '{event_id}' reset to PENDING for replay"}

@router.post("/ai-pricing")
async def create_pricing_version(
    payload: PricingCreateRequest,
    current_user: dict = Depends(require_role("hr_admin"))
):
    """
    Create a new versioned AI model pricing record with concurrency-serialized overlap check.
    """
    res = await add_pricing_version(
        provider=payload.provider,
        model=payload.model,
        pricing_version=payload.pricing_version,
        input_price_per_1m_tokens=payload.input_price_per_1m_tokens,
        output_price_per_1m_tokens=payload.output_price_per_1m_tokens,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        currency=payload.currency
    )
    # Serialize datetime objects in response
    if isinstance(res.get("effective_from"), datetime):
        res["effective_from"] = res["effective_from"].isoformat()
    if isinstance(res.get("effective_until"), datetime):
        res["effective_until"] = res["effective_until"].isoformat()
    if isinstance(res.get("created_at"), datetime):
        res["created_at"] = res["created_at"].isoformat()
    return res
