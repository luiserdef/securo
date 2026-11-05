import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuthConnectionBase(BaseModel):
    provider: str
    auth_type: str
    status: str = "active"


class AuthConnectionCreate(AuthConnectionBase):
    user_id: uuid.UUID
    credentials: str
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class AuthConnectionUpdate(BaseModel):
    provider: Optional[str] = None
    auth_type: Optional[str] = None
    credentials: Optional[str] = None
    status: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class AuthConnectionRead(AuthConnectionBase):
    id: uuid.UUID
    user_id: uuid.UUID
    credentials: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
