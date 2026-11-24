import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import ANSWER_FIELDS, Application, ApplicationStatus
from app.applications.repository import ApplicationRepository
from app.applications.schemas import ApplicationStats
from app.logs.models import LogEvent
from app.logs.service import LogService
from app.users.models import User

logger = logging.getLogger(__name__)


class ApplicationService:
    """Заявки: создание, дозаполнение, напоминания, статистика."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ApplicationRepository(session)
        self.logs = LogService(session)

    async def start_for_user(self, user: User) -> tuple[Application, bool]:
        """Открытая заявка, если есть, иначе новая (с записью в журнал).

        Возвращает (заявка, создана_ли_только_что).
        """
        open_application = await self.repository.get_open_by_user(user.id)
        if open_application is not None:
            return open_application, False
        application = await self.repository.create(user.id)
        await self.logs.log(
            LogEvent.new_application,
            user_id=user.id,
            application_id=application.id,
        )
        return application, True

    async def get_by_avito_chat_id(self, chat_id: str) -> Application | None:
        return await self.repository.get_by_avito_chat_id(chat_id)

    async def create_avito_lead(
        self,
        *,
        chat_id: str,
        last_message_id: int,
        listing_title: str | None,
        full_name: str | None,
        phone: str | None,
    ) -> Application:
        """Лид с Авито: создаём сразу «ждёт обработки» и пишем в журнал."""
        application = await self.repository.create_avito_lead(
            chat_id=chat_id,
            last_message_id=last_message_id,
            listing_title=listing_title,
            full_name=full_name,
            phone=phone,
        )
        await self.logs.log(
            LogEvent.new_application,
            user_id=None,
            application_id=application.id,
            payload={"source": "avito", "chat_id": chat_id, "listing": listing_title},
        )
        return application

    async def get_open_application(
        self, *, application_id: int, telegram_id: int
    ) -> Application | None:
        """Открытая заявка по id с проверкой владельца."""
        application = await self.repository.get(application_id)
        if application is None:
            return None
        if application.user.telegram_id != telegram_id:
            return None
        if application.status != ApplicationStatus.partly_filled:
            return None
        return application

    async def save_answer(
        self, application: Application, field_name: str, value: str
    ) -> None:
        if field_name not in ANSWER_FIELDS:
            raise ValueError(f"Недопустимое поле анкеты: {field_name}")
        setattr(application, field_name, value)
        await self.session.flush()

    async def complete(self, application: Application) -> None:
        application.status = ApplicationStatus.filled
        await self.session.flush()

    async def get_application(self, application_id: int) -> Application | None:
        """Заявка по id без проверок (для панели менеджера)."""
        return await self.repository.get(application_id)

    async def mark_processed(self, application: Application) -> bool:
        """Отметить обработанной; False, если уже обработана."""
        if application.status == ApplicationStatus.processed:
            return False
        application.status = ApplicationStatus.processed
        await self.session.flush()
        await self.logs.log(
            LogEvent.application_processed,
            user_id=application.user_id,
            application_id=application.id,
        )
        return True

    async def collect_for_reminder(
        self, *, delay_minutes: int, max_count: int
    ) -> list[Application]:
        """Заявки, пора отправить напоминание (по updated_at и лимиту)."""
        before = datetime.now(timezone.utc) - timedelta(minutes=delay_minutes)
        return await self.repository.stale_partly_filled(
            before=before, max_reminders=max_count
        )

    async def mark_reminder_sent(
        self, application: Application, *, delivered: bool
    ) -> None:
        application.reminders_sent += 1
        application.last_reminder_at = datetime.now(timezone.utc)
        await self.session.flush()
        if delivered:
            await self.logs.log(
                LogEvent.reminder_sent,
                user_id=application.user_id,
                application_id=application.id,
            )
        else:
            logger.warning(
                "Напоминание по заявке №%s не доставлено", application.id
            )

    async def list_page(
        self,
        *,
        limit: int,
        offset: int,
        status: ApplicationStatus | None = None,
    ) -> tuple[list[Application], int]:
        applications = await self.repository.recent(
            limit=limit, offset=offset, status=status
        )
        total = await self.repository.count_all(status=status)
        return applications, total

    async def stats(self) -> ApplicationStats:
        by_status = await self.repository.count_by_status()
        total = await self.repository.count_all()
        return ApplicationStats(
            total=total,
            partly_filled=by_status.get(ApplicationStatus.partly_filled, 0),
            filled=by_status.get(ApplicationStatus.filled, 0),
            processed=by_status.get(ApplicationStatus.processed, 0),
        )
