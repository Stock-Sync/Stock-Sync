from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import re


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        """Validate password has at least one number and one symbol."""
        if not re.search(r"\d", v):
            raise ValueError("A senha deve conter pelo menos um número")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", v):
            raise ValueError("A senha deve conter pelo menos um símbolo (!@#$%^&*...)")
        return v


class RegisterResponse(BaseModel):
    message: str = "User registered successfully"
    user_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    pass  # Token comes from cookie


class RefreshResponse(BaseModel):
    message: str = "Token refreshed successfully"


class LogoutResponse(BaseModel):
    message: str = "Logged out successfully"


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True