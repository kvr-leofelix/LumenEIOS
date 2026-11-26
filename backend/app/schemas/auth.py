from typing import Optional, List, Any, Literal
from pydantic import BaseModel, EmailStr, Field, field_validator
from backend.app.schemas.common import BaseSchema
from backend.app.core.config import settings


class LoginRequest(BaseModel):
    # Plain str so the development root username (e.g. LEOFELIX) is accepted.
    email: str = Field(min_length=1, max_length=255)
    password: str


class UserOut(BaseSchema):
    id: str
    email: str
    name: str
    role: str
    school_id: Optional[str] = None
    designation: Optional[str] = None
    avatar: Optional[str] = None
    assigned_class_ids: List[str] = []
    assigned_subject_ids: List[str] = []
    linked_child_ids: List[str] = []
    demo_root: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class SwitchSchoolRequest(BaseModel):
    school_id: str


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: Literal["admin", "principal", "teacher", "student", "parent"]
    school_id: Optional[str] = None
    designation: Optional[str] = None


    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if not settings.DEMO_MODE and value == "demo123":
            raise ValueError("The known demo password is not allowed.")
        if not 1 <= len(value.encode("utf-8")) <= 72:
            raise ValueError("Password must contain 1 to 72 UTF-8 bytes.")
        return value


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[Literal["admin", "principal", "teacher", "student", "parent"]] = None
    school_id: Optional[str] = None
    designation: Optional[str] = None
    avatar: Optional[str] = None


    @field_validator("name", "role")
    @classmethod
    def non_null_core_fields(cls, value):
        if value is None or value == "":
            raise ValueError("This field cannot be null or empty.")
        return value
