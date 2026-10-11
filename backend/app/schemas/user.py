from typing import Literal

from pydantic import BaseModel, ConfigDict


UserRole = Literal["admin", "supervisor", "agent"]


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: UserRole = "agent"


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
