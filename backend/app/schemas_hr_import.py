from pydantic import BaseModel, Field
from typing import Optional, List, Any


class EmployeeImportRow(BaseModel):
    """Schema for a single employee row parsed from CSV/XLSX."""
    email: str = Field(..., min_length=3, max_length=120)
    fullName: str = Field(..., min_length=1, max_length=120)
    role: str = Field(default="employee")          # job title/role from CSV
    department: str = Field(default="")


class EmployeeImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = Field(default_factory=list)


class EmployeePreviewRow(BaseModel):
    email: str
    fullName: str
    role: str
    department: str


class EmployeeImportPreview(BaseModel):
    """First-N rows for the frontend preview table."""
    rows: List[EmployeePreviewRow] = Field(default_factory=list)
    total_rows: int = 0
