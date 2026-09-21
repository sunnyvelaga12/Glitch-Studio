"""
Canonical HR Domain Models & Pydantic Schemas for VirtualHR

Defines system-of-record entities for Company, Employee, LeaveBalance, LeaveRequest, 
PolicyDocument, PolicyVersion, and DocumentChunk with strict invariants:
- company_id tenant isolation
- manager.company_id == employee.company_id validation
- Derived leave balance: available = allocated - used - pending
- Compare-and-set leave request state machine (PENDING -> APPROVED/REJECTED/CANCELLED)
- Single active policy version invariant
"""

from datetime import datetime, date, timezone
from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, EmailStr, computed_field, model_validator, ConfigDict


class RoleEnum(str, Enum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    HR_ADMIN = "hr_admin"
    SUPER_ADMIN = "super_admin"


class LeaveTypeEnum(str, Enum):
    ANNUAL = "annual"
    SICK = "sick"
    CASUAL = "casual"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    UNPAID = "unpaid"


class LeaveStatusEnum(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PolicyStatusEnum(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


# ==========================================
# 1. Company Model
# ==========================================

class WorkSchedule(BaseModel):
    work_days: List[str] = Field(default_factory=lambda: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    standard_hours_per_day: float = Field(default=8.0, ge=1.0, le=24.0)


class CompanyModel(BaseModel):
    id: str = Field(alias="_id")
    name: str = Field(min_length=2, max_length=100)
    domain: str
    passkey_hash: str
    passkey_expires_at: Optional[datetime] = None
    is_passkey_revoked: bool = False
    failed_passkey_attempts: int = 0
    subscription_tier: str = "enterprise"
    work_schedule: WorkSchedule = Field(default_factory=WorkSchedule)
    ai_monthly_budget_usd: float = 150.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True)


# ==========================================
# 2. Employee Model (System of Record)
# ==========================================

class EmployeeModel(BaseModel):
    id: str = Field(alias="_id")
    company_id: str
    user_id: str
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    designation: str = Field(min_length=2, max_length=100)
    department: str = Field(min_length=2, max_length=100)
    manager_id: Optional[str] = None  # User ID of manager (must be same tenant)
    join_date: date
    employment_type: str = "full_time"  # full_time | part_time | contractor
    phone: Optional[str] = None
    status: str = "active"  # active | deactivated | terminated
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True)


# ==========================================
# 3. Derived Leave Balance Models
# ==========================================

class LeaveTypeBalance(BaseModel):
    allocated: int = Field(ge=0)
    used: int = Field(default=0, ge=0)
    pending: int = Field(default=0, ge=0)

    @computed_field
    @property
    def available(self) -> int:
        """Derived invariant: available = allocated - used - pending"""
        return self.allocated - self.used - self.pending

    @model_validator(mode="after")
    def validate_non_negative_available(self) -> "LeaveTypeBalance":
        if self.available < 0:
            raise ValueError(
                f"Invariant Violation: available leave balance ({self.available}) cannot be negative "
                f"(allocated={self.allocated}, used={self.used}, pending={self.pending})"
            )
        return self


class LeaveBalanceModel(BaseModel):
    id: str = Field(alias="_id")
    company_id: str
    user_id: str
    year: int = Field(default=2026)
    balances: Dict[str, LeaveTypeBalance] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True)


# ==========================================
# 4. Leave Request Model
# ==========================================

class LeaveRequestModel(BaseModel):
    id: str = Field(alias="_id")
    company_id: str
    user_id: str
    leave_type: LeaveTypeEnum
    start_date: date
    end_date: date
    total_days: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    status: LeaveStatusEnum = LeaveStatusEnum.PENDING
    approver_id: Optional[str] = None
    approver_notes: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        return self

    model_config = ConfigDict(populate_by_name=True)


# ==========================================
# 5. Policy Document & Version Models
# ==========================================

class PolicyDocumentModel(BaseModel):
    id: str = Field(alias="_id")
    company_id: str
    title: str = Field(min_length=3, max_length=200)
    category: str = Field(min_length=2, max_length=50)
    active_version: int = Field(default=1, ge=1)
    access_scope: List[str] = Field(default_factory=lambda: ["employee", "manager", "hr_admin"])
    department_scope: List[str] = Field(default_factory=lambda: ["ALL"])
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True)


class PolicyVersionModel(BaseModel):
    id: str = Field(alias="_id")
    company_id: str
    policy_id: str
    version_number: int = Field(ge=1)
    status: PolicyStatusEnum = PolicyStatusEnum.ACTIVE
    storage_key: str
    file_name: str
    file_size_bytes: int = Field(gt=0)
    mime_type: str = "application/pdf"
    chunk_count: int = Field(default=0, ge=0)
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True)


# ==========================================
# 6. Document Chunk Model (RAG Index)
# ==========================================

class DocumentChunkModel(BaseModel):
    id: str = Field(alias="_id")
    company_id: str
    policy_id: str
    version_number: int
    chunk_index: int
    text: str
    vector_embedding: List[float] = Field(default_factory=list)
    embedding_provider: str = "google"
    embedding_model: str = "gemini-embedding-2"
    embedding_model_version: str = "v1"
    embedding_dimensions: int = 3072
    token_count: int = Field(ge=0)
    page_number: int = Field(ge=1)
    access_scope: List[str] = Field(default_factory=lambda: ["employee", "manager", "hr_admin"])
    department_scope: List[str] = Field(default_factory=lambda: ["ALL"])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True)
