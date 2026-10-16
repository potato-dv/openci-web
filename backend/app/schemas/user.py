from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.utils.names import normalize_user_name


UserRole = Literal["admin", "supervisor", "agent"]


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=128)
    role: UserRole = "agent"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = normalize_user_name(value)
        if not normalized:
            raise ValueError("Name cannot be empty")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    is_active: bool

class UserLogin(BaseModel):
    email: str
    password: str


class UserActivationUpdate(BaseModel):
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: UserRole
