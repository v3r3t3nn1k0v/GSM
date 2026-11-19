import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserStatus(str, enum.Enum):
    consumer = "consumer"  # потребитель (топливо для бизнеса)
    agent = "agent"        # агент (зарабатывает на рекомендациях)


class User(Base):
    """Пользователь бота."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    nickname: Mapped[str] = mapped_column(String(128), default="")
    premium: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False, length=16),
        default=UserStatus.consumer,
        server_default=UserStatus.consumer.value,
        nullable=False,
    )
    # Телефон нужен агентам (анкета агента состоит только из него)
    phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id}>"
