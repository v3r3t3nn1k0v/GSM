import asyncio
import logging

from aiohttp import ClientError
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from python_socks import ProxyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.applications.models import Application
from app.applications.service import ApplicationService
from app.config import get_settings
from app.reminders.celery_app import celery_app
from app.telegram import create_bot

logger = logging.getLogger(__name__)

REMINDER_TEXT = (
    "⏳ Вы начали заполнять заявку на топливо, но не закончили.\n\n"
    "Вернитесь в бота и завершите анкету — это займёт не больше минуты, "
    "и менеджер сразу свяжется с Вами."
)


@celery_app.task(name="reminders.send_pending")
def send_pending_reminders() -> int:
    """Отправка напоминаний по брошенным заявкам (запускается по расписанию beat)."""
    return asyncio.run(_send_pending_reminders())


async def _send_pending_reminders() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    pool = async_sessionmaker(bind=engine, expire_on_commit=False)
    sent = 0
    try:
        async with pool() as session:
            service = ApplicationService(session)
            stale = await service.collect_for_reminder(
                delay_minutes=settings.reminder_delay_minutes,
                max_count=settings.reminder_max_count,
            )
            if not stale:
                return 0
            logger.info("Заявок к напоминанию: %s", len(stale))
            async with create_bot(settings) as bot:
                for application in stale:
                    delivered = await _remind_user(bot, application)
                    await service.mark_reminder_sent(application, delivered=delivered)
                    if delivered:
                        sent += 1
            await session.commit()
    finally:
        await engine.dispose()
    return sent


async def _remind_user(bot: Bot, application: Application) -> bool:
    try:
        await bot.send_message(application.user.telegram_id, REMINDER_TEXT)
    except (TelegramAPIError, ClientError, ProxyError) as exc:
        logger.warning(
            "Напоминание по заявке №%s не доставлено (telegram_id=%s): %r",
            application.id,
            application.user.telegram_id,
            exc,
        )
        return False
    return True
