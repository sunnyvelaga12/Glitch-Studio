from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, Dict, Any, List
from datetime import datetime


class ChatMessage(BaseModel):
    """A single message in a conversation."""

    role: Literal["user", "assistant"] = Field(
        ..., description="Who sent this message — must be 'user' or 'assistant'."
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Non-empty text content of the message.",
    )


class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The user's current question (1–4000 characters).",
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Recent conversation history sent from the client.",
    )

    @field_validator("history")
    @classmethod
    def cap_history(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        """Never accept more than 20 history messages to protect token limits."""
        return v[-20:] if len(v) > 20 else v


class ChatResponse(BaseModel):
    """Outgoing chat response sent to the frontend."""

    response: str = Field(..., description="Bot reply text.")
    error: Optional[str] = Field(None, description="Non-None if a recoverable error occurred.")


# ============================================================================
# Vector Database Schemas
# ============================================================================

class StorePolicyRequest(BaseModel):
    """Request to store a policy document in vector DB."""
    
    doc_id: str = Field(..., description="Unique document identifier")
    section: str = Field(..., description="Policy section name")
    policy_type: str = Field(..., description="Type of policy (e.g., leave_policy)")
    content: str = Field(..., description="Full policy text content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class StoreEmployeeRequest(BaseModel):
    """Request to store employee data in vector DB."""
    
    employee_id: str = Field(..., description="Unique employee identifier")
    name: str = Field(..., description="Employee full name")
    department: str = Field(..., description="Department name")
    designation: str = Field(..., description="Job designation")
    summary: str = Field(..., description="Employee profile summary")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class SearchResult(BaseModel):
    """A single search result from vector DB."""
    
    id: str = Field(..., description="Document/record ID")
    score: float = Field(..., description="Similarity score (0-1)")
    metadata: Dict[str, Any] = Field(..., description="Associated metadata")


class SearchPolicyRequest(BaseModel):
    """Request to search for policies."""
    
    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    score_threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum similarity score")


class SearchEmployeeRequest(BaseModel):
    """Request to search for employees."""
    
    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    score_threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum similarity score")


class SearchResponse(BaseModel):
    """Response containing search results."""
    
    policies: List[SearchResult] = Field(default_factory=list, description="Policy search results")
    employees: List[SearchResult] = Field(default_factory=list, description="Employee search results")
    total_results: int = Field(..., description="Total number of results")


class IngestResponse(BaseModel):
    """Response from data ingestion operation."""
    
    success: bool = Field(..., description="Whether ingestion was successful")
    count: int = Field(..., description="Number of records ingested")
    message: str = Field(..., description="Status message")


class DeleteRequest(BaseModel):
    """Request to delete a document or record."""
    
    id: str = Field(..., description="ID of document/record to delete")
    type: Literal["policy", "employee"] = Field(..., description="Type of data to delete")


class IndexStats(BaseModel):
    """Vector database index statistics."""
    
    index_name: str
    dimension: int
    stats: Dict[str, Any]


# ============================================================================
# Employee Management Schemas
# ============================================================================

class EmployeeProfileResponse(BaseModel):
    """Complete employee profile information."""
    
    employee_id: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    department: str
    designation: str
    manager_name: str
    office_location: str
    work_mode: str
    employment_status: str = "Active"
    years_with_company: int
    performance_rating: float
    skills: List[str] = []
    certifications: List[str] = []
    date_of_joining: Optional[str] = None


class LeaveBalanceResponse(BaseModel):
    """Employee leave balance details."""
    
    employee_id: str
    casual_leave_total: int
    casual_leave_used: int
    casual_leave_remaining: int
    sick_leave_total: int
    sick_leave_used: int
    sick_leave_remaining: int
    privilege_leave_total: int
    privilege_leave_used: int
    privilege_leave_remaining: int
    floating_holidays_total: int
    floating_holidays_used: int
    floating_holidays_remaining: int
    last_updated: str


class AttendanceRecordResponse(BaseModel):
    """Single attendance record."""
    
    date: str
    status: str  # Present, WFH, Half-Day, Leave, Absent
    hours_worked: float
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    location: Optional[str] = None


class EmployeeStatsResponse(BaseModel):
    """Company-wide employee statistics."""
    
    total_employees: int
    active_employees: int
    on_leave_today: int
    absent_today: int
    present_today: int
    work_from_home_today: int
    terminations_this_month: int
    new_hires_this_month: int
    average_performance_rating: float


class LeaveStatsResponse(BaseModel):
    """Leave management statistics."""
    
    pending_approvals: int
    approved_this_month: int
    rejected_this_month: int
    on_leave_today: int
    returning_tomorrow: int
    total_leaves_taken_this_year: int
