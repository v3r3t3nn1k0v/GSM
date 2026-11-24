"""Клиент Groq (OpenAI-совместимый API) для AI-автоответов.

Философия: LLM — улучшение, а не критический путь. Любой сбой Groq
(нет ключа, таймаут, лимиты) возвращает None, вызывающий откатывается
на шаблонный ответ — лид не теряется никогда.
"""
import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp_socks import ProxyConnector

from app.config import Settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def create_session(settings: Settings) -> aiohttp.ClientSession:
    """Сессия для Groq: при необходимости — через прокси (aiohttp-socks)."""
    connector: aiohttp.TCPConnector | ProxyConnector
    if settings.groq_proxy_url:
        connector = ProxyConnector.from_url(settings.groq_proxy_url)
    else:
        connector = aiohttp.TCPConnector()
    return aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=30),
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
    )


async def chat_completion(
    session: aiohttp.ClientSession,
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 200,
    temperature: float = 0.3,
) -> str | None:
    """Ответ модели или None при любой проблеме (не бросает исключений)."""
    if not settings.groq_api_key:
        return None
    try:
        async with session.post(
            GROQ_API_URL,
            json={
                "model": settings.groq_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        ) as response:
            if response.status != 200:
                logger.warning(
                    "Groq вернул HTTP %s: %s", response.status, await response.text()
                )
                return None
            payload: dict[str, Any] = await response.json()
        return str(payload["choices"][0]["message"]["content"]).strip() or None
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError):
        logger.warning("Groq недоступен, откатываемся на шаблонный ответ", exc_info=True)
        return None
