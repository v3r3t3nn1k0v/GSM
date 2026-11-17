import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LogEvent(str, enum.Enum):
    new_user = "new_user"
    new_application = "new_application"
    reminder_sent = "reminder_sent"
    application_processed = "application_processed"


class LogEntry(Base):
    """Журнал событий бота."""

    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[LogEvent] = mapped_column(
        Enum(LogEvent, native_enum=False, length=32), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
