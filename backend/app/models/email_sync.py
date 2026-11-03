import uuid
from app.core.database import Base
from datetime import date as _date, datetime, timezone

from sqlalchemy.dialects.postgresql import UUID

class EmailSyncTransaction(Base):
    __tablename__ = "transaction_email_sync"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    sender: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(String(600))
    description: Mapped[str] = mapped_column(String(600))
    label: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(10))  # debit, credit
    last_update_date: Mapped[Optional[_date]] = mapped_column(Date, nullable=True)