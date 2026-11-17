import asyncio
import logging

from alembic import command
from alembic.config import Config as AlembicConfig
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from app.config import get_settings
from app.db.session import make_session_pool
from bot.admin.routers import router as admin_router
from bot.application.routers import router as application_router
from bot.middlewares.db import DbSessionMiddleware
from bot.partnership.routers import router as partnership_router
from bot.users.routers import router as users_router


def run_migrations() -> None:
    """Применяем миграции до старта polling."""
    alembic_cfg = AlembicConfig("alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()

    await asyncio.to_thread(run_migrations)

    session_pool = make_session_pool(settings.database_url)
    storage = RedisStorage.from_url(settings.redis_url)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )
    dp = Dispatcher(storage=storage)
    dp.update.middleware(DbSessionMiddleware(session_pool))

    # Порядок важен: /start должен перехватываться раньше state-хендлеров анкеты
    dp.include_router(users_router)
    dp.include_router(admin_router)
    dp.include_router(partnership_router)
    dp.include_router(application_router)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
