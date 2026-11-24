"""Клиент Groq (OpenAI-совместимый API): tool calling для сообщений Авито.

Философия: LLM — улучшение, а не критический путь. Любой сбой Groq
(нет ключа, таймаут, лимиты) возвращает пустой список вызовов, вызывающий
откатывается на шаблонный ответ — лид не теряется никогда.
"""
import asyncio
import json
import logging
from typing import Any

import aiohttp
from aiohttp_socks import ProxyConnector

from app.config import Settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# gpt-oss — reasoning-модель: на неоднозначных сообщениях она может долго
# рассуждать, и при малом лимите ответ обрезается до пустого
DEFAULT_MAX_TOKENS = 1500


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


async def _completion(
    session: aiohttp.ClientSession, settings: Settings, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Ответ chat/completions целиком или None при любой проблеме."""
    if not settings.groq_api_key:
        return None
    try:
        async with session.post(GROQ_API_URL, json=payload) as response:
            if response.status != 200:
                logger.warning(
                    "Groq вернул HTTP %s: %s", response.status, await response.text()
                )
                return None
            payload_out: dict[str, Any] = await response.json()
            return payload_out
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.warning("Groq недоступен, откатываемся на шаблонный ответ", exc_info=True)
        return None


async def chat_tool_calls(
    session: aiohttp.ClientSession,
    settings: Settings,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[tuple[str, dict[str, Any]]]:
    """Функции, выбранные моделью: [(имя, аргументы)]. Пусто при любом сбое."""
    payload = await _completion(
        session,
        settings,
        {
            "model": settings.groq_model,
            "messages": messages,
            "tools": tools,
            # Классификация и ответ — каждый шаг своей функцией, выбор всегда однозначен
            "tool_choice": "required",
            "max_tokens": max_tokens,
            "temperature": 0.0,
        },
    )
    if payload is None:
        return []
    choice: dict[str, Any] = {}
    try:
        choices = payload["choices"]
        choice = choices[0]
        raw_calls = choice["message"].get("tool_calls") or []
    except (KeyError, IndexError, TypeError, AttributeError):
        raw_calls = []

    calls: list[tuple[str, dict[str, Any]]] = []
    for raw in raw_calls:
        try:
            name = raw["function"]["name"]
            arguments = json.loads(raw["function"].get("arguments") or "{}")
        except (KeyError, TypeError, ValueError):
            # Обрезанный reasoning-бюджетом JSON или незнакомый формат — пропускаем
            logger.warning("Groq: аргументы функции не разобраны")
            continue
        if isinstance(name, str) and isinstance(arguments, dict):
            calls.append((name, arguments))
    if not calls:
        logger.warning(
            "Groq: модель %s не выбрала ни одной функции (finish_reason=%s, tokens=%s)",
            settings.groq_model,
            choice.get("finish_reason"),
            (payload.get("usage") or {}).get("completion_tokens"),
        )
    return calls
