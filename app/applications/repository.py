from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import Application, ApplicationStatus


class ApplicationRepository:
    """Доступ к данным заявок."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, application_id: int) -> Application | None:
        return await self.session.get(Application, application_id)

    async def get_open_by_user(self, user_id: int) -> Application | None:
        """Последняя незавершённая заявка пользователя."""
        stmt = (
            select(Application)
            .where(
                Application.user_id == user_id,
                Application.status == ApplicationStatus.partly_filled,
            )
            .order_by(Application.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, user_id: int) -> Application:
        application = Application(user_id=user_id)
        self.session.add(application)
        await self.session.flush()
        return application

    async def stale_partly_filled(
        self,
        *,
        before: datetime,
        max_reminders: int,
        limit: int = 100,
    ) -> list[Application]:
        """Незавершённые заявки без активности после `before` и с лимитом напоминаний."""
        stmt = (
            select(Application)
            .where(
                Application.status == ApplicationStatus.partly_filled,
                Application.reminders_sent < max_reminders,
                Application.updated_at < before,
            )
            .order_by(Application.id)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def recent(
        self,
        *,
        limit: int,
        offset: int = 0,
        status: ApplicationStatus | None = None,
    ) -> list[Application]:
        stmt = select(Application).order_by(Application.id.desc())
        if status is not None:
            stmt = stmt.where(Application.status == status)
        stmt = stmt.offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_all(self, status: ApplicationStatus | None = None) -> int:
        stmt = select(func.count()).select_from(Application)
        if status is not None:
            stmt = stmt.where(Application.status == status)
        return (await self.session.execute(stmt)).scalar_one()

    async def count_by_status(self) -> dict[ApplicationStatus, int]:
        stmt = select(Application.status, func.count()).group_by(Application.status)
        rows = (await self.session.execute(stmt)).all()
        return {status: count for status, count in rows}
