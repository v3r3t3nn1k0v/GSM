from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.models import LogEvent
from app.logs.repository import LogRepository


class LogService:
    """Запись событий в журнал."""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = LogRepository(session)

    async def log(
        self,
        event: LogEvent,
        *,
        user_id: int | None = None,
        application_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.repository.create(
            event=event,
            user_id=user_id,
            application_id=application_id,
            payload=payload,
        )
