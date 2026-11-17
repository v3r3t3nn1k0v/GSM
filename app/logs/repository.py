from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.models import LogEntry, LogEvent


class LogRepository:
    """Доступ к журналу событий."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        event: LogEvent,
        user_id: int | None = None,
        application_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> LogEntry:
        entry = LogEntry(
            event=event,
            user_id=user_id,
            application_id=application_id,
            payload=payload,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
