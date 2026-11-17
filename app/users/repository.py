from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User


class UserRepository:
    """Доступ к данным пользователей."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        telegram_id: int,
        username: str | None,
        nickname: str,
        premium: bool,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            nickname=nickname,
            premium=premium,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def count_all(self) -> int:
        stmt = select(func.count()).select_from(User)
        return (await self.session.execute(stmt)).scalar_one()

    async def count_created_since(self, since: datetime) -> int:
        stmt = select(func.count()).select_from(User).where(User.created_at >= since)
        return (await self.session.execute(stmt)).scalar_one()

    async def all_telegram_ids(self) -> list[int]:
        stmt = select(User.telegram_id).order_by(User.id)
        return list((await self.session.execute(stmt)).scalars().all())
