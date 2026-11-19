from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.models import LogEvent
from app.logs.service import LogService
from app.users.models import User, UserStatus
from app.users.repository import UserRepository
from app.users.schemas import UserStats


class UserService:
    """Пользователи: регистрация, обновление профиля, статистика."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = UserRepository(session)
        self.logs = LogService(session)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.repository.get_by_telegram_id(telegram_id)

    async def get_or_create(
        self,
        *,
        telegram_id: int,
        username: str | None,
        nickname: str,
        premium: bool,
    ) -> tuple[User, bool]:
        """Возвращает (пользователь, создан_ли_только_что). Профиль обновляется при изменении."""
        user = await self.repository.get_by_telegram_id(telegram_id)
        if user is None:
            user = await self.repository.create(
                telegram_id=telegram_id,
                username=username,
                nickname=nickname,
                premium=premium,
            )
            await self.logs.log(
                LogEvent.new_user,
                user_id=user.id,
                payload={"username": username, "nickname": nickname},
            )
            return user, True

        if (user.username, user.nickname, user.premium) != (username, nickname, premium):
            user.username = username
            user.nickname = nickname
            user.premium = premium
        return user, False

    async def stats(self) -> UserStats:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        total = await self.repository.count_all()
        new_today = await self.repository.count_created_since(today_start)
        return UserStats(total=total, new_today=new_today)

    async def set_status(self, user: User, status: UserStatus) -> None:
        """Меняем роль пользователя (потребитель/агент)."""
        user.status = status

    async def register_agent(self, user: User, phone: str) -> None:
        """Анкета агента завершена: фиксируем статус, телефон и событие в журнале."""
        user.status = UserStatus.agent
        user.phone = phone
        await self.logs.log(
            LogEvent.agent_registered,
            user_id=user.id,
            payload={"phone": phone, "username": user.username},
        )

    async def all_telegram_ids(self, status: UserStatus | None = None) -> list[int]:
        return await self.repository.all_telegram_ids(status)
