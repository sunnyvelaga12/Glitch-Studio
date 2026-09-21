from pydantic import BaseModel, Field
from typing import Any, Optional


class CompanyCreateRequest(BaseModel):
    companyName: str = Field(..., min_length=2, max_length=120)


class PoliciesUpsertRequest(BaseModel):
    # full policy document JSON
    policies: dict[str, Any]


class DocumentStatusResponse(BaseModel):
    id: str
    filename: str
    size_bytes: int
    status: str   # "processing" | "ready" | "error"
    uploaded_at: str
