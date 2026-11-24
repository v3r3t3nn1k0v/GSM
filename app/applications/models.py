import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.users.models import User


class ApplicationStatus(str, enum.Enum):
    partly_filled = "partly_filled"
    filled = "filled"
    processed = "processed"


class ApplicationSource(str, enum.Enum):
    tg = "tg"        # заявка из Telegram-воронки
    avito = "avito"  # лид из чата по объявлению на Авито


# Поля-ответы анкеты в порядке следования вопросов
ANSWER_FIELDS = (
    "fuel_type",
    "gas_networks",
    "monthly_volume",
    "region",
    "delivery_needed",
    "full_name",
    "phone",
)


class Application(Base):
    """Заявка на топливо (анкета пользователя)."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Не заполняется для лидов с Авито (там нет пользователя бота)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[ApplicationSource] = mapped_column(
        Enum(ApplicationSource, native_enum=False, length=8),
        default=ApplicationSource.tg,
        server_default=ApplicationSource.tg.value,
        nullable=False,
    )
    # Привязка чата Авито: один чат по объявлению = одна заявка
    avito_chat_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    avito_last_message_id: Mapped[str | None] = mapped_column(BigInteger)
    listing_title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=20),
        default=ApplicationStatus.partly_filled,
        server_default=ApplicationStatus.partly_filled.value,
        index=True,
    )
    fuel_type: Mapped[str | None] = mapped_column(String(8))
    gas_networks: Mapped[str | None] = mapped_column(Text)
    monthly_volume: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    delivery_needed: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))

    reminders_sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<Application id={self.id} status={self.status}>"
