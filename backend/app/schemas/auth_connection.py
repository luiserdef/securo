import uuid
from datetime import date as _Date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

class AuthConnectionBase(BaseModel):
    provider: str
    auth_type: str
    status: str = "active"

class AuthConnectionCreate(AuthConnectionBase):
    user_id: uuid.UUID
    credentials: str
    expires_at: Optional[datetime] = None
    created_at: datetime

class AuthConnectionUpdate(BaseModel):
    provider: Optional[str] = None
    auth_type: Optional[str] = None
    credentials: Optional[dict] = None
    status: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class auth_connections(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    provider: str
    auth_type: str
    credentials:
    

    description: str
    amount: Decimal
    currency: str = "USD"
    type: str  # debit, credit
    frequency: str  # weekly, monthly, quarterly, yearly
    weekend_adjustment: WeekendAdjustment = "none"
    day_of_month: Optional[int] = None
    start_date: _Date
    end_date: Optional[_Date] = None
    account_id: uuid.UUID
    category_id: Optional[uuid.UUID] = None
    skip_first: bool = False  # Set true when first occurrence already created as a transaction
    auto_generate: bool = True  # Materialize occurrences; when false, wait for the real charge



class AuthConnection(Base):
    __tablename__ = "auth_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(50))
    auth_type: Mapped[str] = mapped_column(String(50))
    credentials: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Encrypted tokens
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, error, expired
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))