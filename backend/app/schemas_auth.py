from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
import re


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    passkey: Optional[str] = None
    role: Optional[str] = None


class LoginResponse(BaseModel):
    accessToken: str
    role: Literal["hr_admin", "employee"]
    companyId: str


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    role: Literal["hr_admin", "employee"]
    fullName: Optional[str] = None
    companyName: Optional[str] = None
    companyId: Optional[str] = None
    # Employees can supply the workspace passkey instead of raw companyId
    passkey: Optional[str] = None


class SignupResponse(BaseModel):
    message: str = "created"
    companyId: Optional[str] = None
    companyName: Optional[str] = None


class WorkspaceInfoResponse(BaseModel):
    companyId: str
    companyName: str
    passkey: str


# ---------------------------------------------------------------------------
# Admin-specific schemas
# ---------------------------------------------------------------------------

class AdminLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, description="Super-admin email")
    password: str = Field(..., min_length=1, description="Super-admin password")


class AdminLoginResponse(BaseModel):
    accessToken: str
    role: Literal["super_admin"]
    expiresInMinutes: int


class CreateAccountRequest(BaseModel):
    email: str = Field(..., min_length=5, description="New user's email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    role: Literal["hr_admin", "employee"] = Field(..., description="Account role to create")
    fullName: Optional[str] = Field(None, max_length=100, description="User's full name")
    companyName: Optional[str] = Field(None, max_length=200, description="Company name (creates new company for hr_admin)")
    companyId: Optional[str] = Field(None, description="Existing company ID to assign the user to")
    passkey: Optional[str] = Field(None, description="Workspace passkey (for employee accounts)")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        email = v.strip().lower()
        # Basic email format check
        if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email):
            raise ValueError("Invalid email format")
        return email

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        errors = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            errors.append("at least one digit")
        if not re.search(r"[^a-zA-Z0-9]", v):
            errors.append("at least one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


class CreateAccountResponse(BaseModel):
    message: str
    userId: str
    email: str
    role: str
    companyId: Optional[str] = None
    companyName: Optional[str] = None
    createdAt: str


# ---------------------------------------------------------------------------
# Forgot & Reset Password Schemas
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3)


class ForgotPasswordResponse(BaseModel):
    message: str
    resetToken: Optional[str] = None  # Returned for testing/dev mode convenience


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=6)
    newPassword: str = Field(..., min_length=6)


class ResetPasswordResponse(BaseModel):
    message: str

