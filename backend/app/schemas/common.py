from typing import Optional, List, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NotificationOut(BaseSchema):
    id: str
    user_id: str
    title: str
    message: str
    type: str
    is_read: bool
    link: Optional[str] = None
    created_at: Any


class AnnouncementCreate(BaseSchema):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=2000)
    # Groups to reach. When omitted, the older single-role ``target_role`` is used.
    audience: Optional[List[Literal["teacher", "student", "parent"]]] = None
    target_role: Optional[str] = None
    class_ids: Optional[List[str]] = None
    # Optional: also mark this on the calendar (ISO dates). Never touches Academic Config.
    event_start: Optional[str] = None
    event_end: Optional[str] = None

    @field_validator("title", "content")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field cannot be empty.")
        return v


class AnnouncementOut(BaseSchema):
    id: str
    school_id: str
    sender_id: str
    sender_name: str
    sender_role: Optional[str] = None
    title: str
    content: str
    target_role: str
    audience: List[str] = []
    class_ids: Optional[List[str]] = None
    class_names: List[str] = []
    event_start: Optional[str] = None
    event_end: Optional[str] = None
    can_delete: bool = False
    recipients: Optional[int] = None
    created_at: Any


class AuditEventOut(BaseSchema):
    id: str
    timestamp: str
    user_id: str
    user_name: str
    action: str
    details: str
    category: str
    ip_address: Optional[str] = None

