"""Фабрика Bot с общими настройками подключения к Telegram API."""

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from app.config import Settings, get_settings


def create_bot(settings: Settings | None = None) -> Bot:
    """Создаёт Bot с прокси из TG_PROXY_URL, если он задан.

    На части VPS api.telegram.org недоступен напрямую (блокировка хостингом),
    и первый же запрос падает с TelegramNetworkError: Request timeout error.
    Через TG_PROXY_URL трафик бота идёт через прокси; поддерживаются
    socks5:// и socks4:// (нужен пакет aiohttp-socks), а также http(s)://.
    """
    if settings is None:
        settings = get_settings()
    session = AiohttpSession(proxy=settings.tg_proxy_url) if settings.tg_proxy_url else None
    return Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )
