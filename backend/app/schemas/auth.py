from pydantic import Field, field_validator

from app.schemas.base import StrictBaseModel


class RegisterRequest(StrictBaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if " " in value or "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("A valid email address is required")
        return value


class LoginRequest(StrictBaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthResponse(StrictBaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str


class LogoutResponse(StrictBaseModel):
    status: str = "logged_out"
