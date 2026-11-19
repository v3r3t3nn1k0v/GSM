import asyncio
import logging

from aiohttp import ClientError
from alembic import command
from alembic.config import Config as AlembicConfig
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.redis import RedisStorage
from python_socks import ProxyError

from app.config import get_settings
from app.db.session import make_session_pool
from app.telegram import create_bot
from bot.admin.routers import router as admin_router
from bot.application.routers import router as application_router
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.partnership.routers import router as partnership_router
from bot.users.routers import router as users_router

logger = logging.getLogger(__name__)

# Пауза между попытками достучаться до Telegram API
RECONNECT_DELAY_SECONDS = 15


def run_migrations() -> None:
    """Применяем миграции до старта polling."""
    alembic_cfg = AlembicConfig("alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def wait_for_telegram(bot: Bot) -> None:
    """Ждём доступности Telegram API перед стартом polling.

    На VPS без прямого доступа к api.telegram.org первый запрос (get_me)
    падает по таймауту и убивает процесс. Вместо этого повторяем с паузой —
    контейнер остаётся живым и подключается, когда связь появится.
    """
    while True:
        try:
            me = await bot.get_me()
            logger.info("Связь с Telegram установлена: @%s (id=%s)", me.username, me.id)
            return
        except (TelegramNetworkError, ClientError, ProxyError) as exc:
            logger.error(
                "Нет доступа к api.telegram.org: %s. Повтор через %s с. "
                "Если хостинг блокирует Telegram, укажите TG_PROXY_URL в .env.",
                exc,
                RECONNECT_DELAY_SECONDS,
            )
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()

    await asyncio.to_thread(run_migrations)

    session_pool = make_session_pool(settings.database_url)
    storage = RedisStorage.from_url(settings.redis_url)

    bot = create_bot(settings)
    dp = Dispatcher(storage=storage)
    dp.update.middleware(DbSessionMiddleware(session_pool))
    # Гейт подписки на канал: до хендлеров доходит только подписанный
    # (TELEGRAM_CHANNEL_ID пуст — проверка не выполняется)
    subscription_mw = SubscriptionMiddleware(settings)
    dp.message.outer_middleware(subscription_mw)
    dp.callback_query.outer_middleware(subscription_mw)

    # Порядок важен: /start должен перехватываться раньше state-хендлеров анкеты
    dp.include_router(users_router)
    dp.include_router(admin_router)
    dp.include_router(partnership_router)
    dp.include_router(application_router)

    try:
        await wait_for_telegram(bot)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
