"""Поллинг чатов Авито: новые лиды и сообщения по существующим заявкам.

Ключевая идея: один chat_id Авито = одна заявка. Входящее сообщение из чата,
которого нет в базе, — первый контакт (создаём лид + ответ клиенту + уведомление
менеджерам). Сообщения из известного чата — переписка по существующей заявке.

Отвечает клиентам AI-ассистент на Groq (если задан GROQ_API_KEY): живые
контекстные ответы с жёстким промптом продавца топлива. Любой сбой Groq —
откат на шаблон (первый контакт) или тишина (переписка), лид не теряется.
"""
import asyncio
import json
import logging
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai import client as ai_client
from app.applications.models import Application, ApplicationStatus
from app.applications.service import ApplicationService
from app.avito import texts
from app.avito.client import AvitoApiError, AvitoClient, AvitoSubscriptionError
from app.config import Settings
from app.telegram import create_bot
from bot.application.keyboards import processed_keyboard

logger = logging.getLogger(__name__)

# Телефон, оставленный прямо в тексте сообщения (7+ цифр)
PHONE_IN_TEXT_RE = re.compile(r"\+?\d[\d\s\-()]{6,19}\d")

# Экономия лимитов Groq (free-тариф, 8000 токенов/мин): модель дёргаем
# одним вызовом и только при новых сообщениях; ответ клиенту — шаблоном
AI_REPLY_MAX_PER_CHAT = 15        # максимум наших ответов в одном чате
AI_HISTORY_LIMIT = 8              # сообщений в контексте extraction
AI_MESSAGE_TEXT_LIMIT = 300       # обрезаем реплики для экономии токенов

# Квалификация лида: менеджерам заявка падает, только когда собраны
# телефон + вид топлива + объём + регион (до этого бот общается сам)
LEAD_REQUIRED_FIELDS = ("fuel_type", "monthly_volume", "region", "phone")
# Клиент столько написал, а данных всё нет — поднимаем менеджеров несмотря ни на что
LEAD_ESCALATION_AFTER_MESSAGES = 10


def normalize_phone(raw: str | None) -> str | None:
    """Номер «8 921…» / «+7 921…» / «7921…» → «+7921…»; остальное не трогаем.

    Однозначно российский формат (11 цифр с 8 или 7 в начале) приводим к виду,
    который Telegram делает кликабельным. Короткие и иностранные номера
    оставляем ровно в тех цифрах, что написал клиент, — не угадываем код страны.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    return digits or None


def extract_phone(text: str) -> str | None:
    match = PHONE_IN_TEXT_RE.search(text)
    if match and len(re.sub(r"\D", "", match.group(0))) >= 7:
        return normalize_phone(match.group(0))
    return None


def _is_incoming(message: dict[str, Any], owner_user_id: str) -> bool:
    """Только сообщения от клиента: наши ответы и автоответы игнорируем."""
    if message.get("direction"):
        return message["direction"] == "in"
    return str(message.get("author_id") or message.get("user_id")) != owner_user_id


def _message_id(message: dict[str, Any]) -> str:
    # У Авито id сообщений — hex-строки, не числа
    return str(message["id"])


def _message_text(message: dict[str, Any]) -> str:
    return str((message.get("content") or {}).get("text") or "").strip()


def _message_time(message: dict[str, Any]) -> datetime | None:
    raw = message.get("created_at")
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):  # эпоха в секундах/миллисекундах
            seconds = raw / 1000 if raw > 1e11 else raw
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


_MIN_TIME = datetime.min.replace(tzinfo=timezone.utc)


def _sort_key(message: dict[str, Any]) -> datetime:
    """Порядок сообщений — по времени (как их ни отдал бы API)."""
    return _message_time(message) or _MIN_TIME


def _select_after(
    messages: list[dict[str, Any]],
    cursor_id: str | None,
    floor: datetime | None,
) -> list[dict[str, Any]]:
    """Сообщения после курсора.

    Курсор — id последнего обработанного сообщения. Если его нет в выдаче
    (длинная история/пагинация) — страховка от дубликатов по времени: только
    сообщения новее `floor` (последнее касание заявки минус минута).
    """
    if cursor_id is None:
        return messages
    for index, message in enumerate(messages):
        if _message_id(message) == cursor_id:
            return messages[index + 1 :]
    if floor is None:
        return messages
    return [
        m
        for m in messages
        if (time := _message_time(m)) is not None and time > floor
    ]


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _chat_title(chat: dict[str, Any]) -> str | None:
    context = chat.get("context") or {}
    value = context.get("value") or {}
    return value.get("title") or context.get("title")


def _buyer_name(chat: dict[str, Any], owner_user_id: str) -> str | None:
    for user in chat.get("users") or []:
        if str(user.get("id")) != owner_user_id:
            return user.get("name") or user.get("public_name")
    return None


@dataclass
class _PollContext:
    """Всё, что нужно для обработки чатов за один тик поллинга."""

    settings: Settings
    pool: async_sessionmaker
    client: AvitoClient
    http: aiohttp.ClientSession          # сессия Avito API
    bot: Bot                             # бот для уведомлений менеджерам
    ai: aiohttp.ClientSession | None     # сессия Groq (None — AI выключен)


async def poll_once() -> dict[str, Any]:
    """Один тик поллинга: обошли обновлённые чаты, вернули статистику.

    Redis-lock защищает от наложения тиков (beat стреляет каждые 30 секунд,
    а тик с 50 чатами может идти дольше — второй не должен стартовать параллельно).
    """
    settings = Settings()
    if not (
        settings.avito_client_id
        and settings.avito_client_secret
        and settings.avito_user_id
    ):
        return {"skipped": "ключи Авито не заданы — интеграция выключена"}

    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.redis_url)
    lock = redis_client.lock("avito:poll_lock", timeout=180)
    if not await lock.acquire(blocking=True, blocking_timeout=0.1):
        await redis_client.aclose()
        return {"skipped": "предыдущий тик ещё выполняется"}
    try:
        return await _poll(settings)
    finally:
        try:
            await lock.release()
        except Exception:  # lock истёк — не страшно
            pass
        await redis_client.aclose()


async def _poll(settings: Settings) -> dict[str, Any]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    pool = async_sessionmaker(bind=engine, expire_on_commit=False)
    stats: dict[str, Any] = {"chats": 0, "new_leads": 0, "followups": 0, "errors": 0}
    try:
        client = AvitoClient(
            settings.avito_client_id,
            settings.avito_client_secret,
            settings.avito_user_id,
        )
        async with AsyncExitStack() as stack:
            http = await stack.enter_async_context(
                aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
            )
            bot = await stack.enter_async_context(create_bot(settings))
            ai = (
                await stack.enter_async_context(ai_client.create_session(settings))
                if settings.groq_api_key
                else None
            )
            ctx = _PollContext(
                settings=settings, pool=pool, client=client, http=http, bot=bot, ai=ai
            )
            chats = await client.fetch_updated_chats(http)
            stats["chats"] = len(chats)
            for chat in chats:
                chat_id = str(chat.get("id"))
                try:
                    result = await _process_chat(ctx, chat)
                    stats[result] = stats.get(result, 0) + 1
                except AvitoSubscriptionError:
                    # 402: без подписки читать сообщения бессмысленно для всех чатов
                    logger.error(
                        "Авито: аккаунт без подписки на API мессенджера (HTTP 402) — "
                        "чтение сообщений недоступно, тик остановлен. "
                        "Нужен тариф Авито Pro «Максимальный» (для товаров)."
                    )
                    stats["subscription"] = True
                    break
                except AvitoApiError:
                    stats["errors"] += 1
                    logger.exception("Чат Авито %s: ошибка API", chat_id)
                except Exception:
                    stats["errors"] += 1
                    logger.exception("Чат Авито %s: неожиданная ошибка", chat_id)
                await asyncio.sleep(0.2)  # мягкий темп между чатами
    finally:
        await engine.dispose()
    if stats["new_leads"] or stats["followups"] or stats["errors"] or stats.get("subscription"):
        logger.info("Поллинг Авито: %s", stats)
    return stats


async def _process_chat(ctx: _PollContext, chat: dict[str, Any]) -> str:
    """Обрабатываем один чат. Возвращает 'new_leads' / 'followups' / ''."""
    chat_id = str(chat.get("id"))
    messages = sorted(
        await ctx.client.fetch_chat_messages(ctx.http, chat_id), key=_sort_key
    )
    incoming = [
        m for m in messages if _is_incoming(m, ctx.client.user_id) and _message_text(m)
    ]
    if not incoming:
        return ""
    # Калибровка формата на живых данных: если текст ни у одного сообщения
    # не распознан — ругаемся в лог с ключами, чтобы поправить парсер
    if not any(_message_text(m) for m in messages):
        logger.warning(
            "Чат Авито %s: %s сообщений без распознанного текста, keys=%s",
            chat_id,
            len(messages),
            sorted(messages[-1].keys()) if messages else [],
        )

    async with ctx.pool() as session:
        service = ApplicationService(session)
        application = await service.get_by_avito_chat_id(chat_id)

        if application is None:
            await _create_lead(ctx, session, service, chat, messages, incoming[0])
            return "new_leads"

        return await _process_followup(ctx, session, application, chat, messages)


async def _create_lead(
    ctx: _PollContext,
    session,
    service: ApplicationService,
    chat: dict[str, Any],
    messages: list[dict[str, Any]],
    first_message: dict[str, Any],
) -> str:
    """Первый контакт: тихий лид (partly_filled) + просьба данных + извлечение.

    Менеджерам заявка упадёт только когда будут собраны все обязательные поля
    (телефон, топливо, объём, регион) — до этого бот квалифицирует клиента сам.
    """
    message_text = _message_text(first_message)
    application = await service.create_avito_lead(
        chat_id=str(chat.get("id")),
        last_message_id=_message_id(first_message),
        listing_title=_chat_title(chat),
        full_name=_buyer_name(chat, ctx.client.user_id),
        phone=extract_phone(message_text),
    )
    await _qualify_step(ctx, session, application, chat, messages, extract=True)
    if _lead_is_ready(application):
        await _complete_lead(ctx, application, message_text)
        return "new_leads"
    logger.info(
        "Квалификация лида с Авито: заявка №%s ждёт данные (чат %s)",
        application.id,
        chat.get("id"),
    )
    return "qualifying"


async def _process_followup(
    ctx: _PollContext,
    session,
    application: Application,
    chat: dict[str, Any],
    messages: list[dict[str, Any]],
) -> str:
    """Переписка: двигаем курсор, извлекаем данные, менеджерам — по готовности."""
    chat_id = str(chat.get("id"))
    floor = (
        _as_utc(application.updated_at) - timedelta(minutes=1)
        if application.updated_at
        else None
    )
    new_messages = _select_after(
        messages, application.avito_last_message_id, floor
    )
    fresh = [
        m
        for m in new_messages
        if _is_incoming(m, ctx.client.user_id) and _message_text(m)
    ]
    if not fresh and application.status != ApplicationStatus.partly_filled:
        return ""

    # Заявка ещё собирается: бот допрашивает, менеджеров не дёргаем
    if application.status == ApplicationStatus.partly_filled:
        if fresh:
            application.avito_last_message_id = _message_id(fresh[-1])
            # Клиент мог оставить телефон прямо в тексте сообщения
            if not application.phone:
                for message in fresh:
                    phone = extract_phone(_message_text(message))
                    if phone:
                        application.phone = phone
                        break
        # Извлекаем данные только при новых сообщениях — на пустых тиках
        # Groq не дёргаем (иначе лимит токенов выбивался на 50 чатах × 30 сек)
        # Инвариант «ответить на висящее входящее» работает и без extraction
        answered = await _qualify_step(
            ctx, session, application, chat, messages, extract=bool(fresh)
        )
        if _lead_is_ready(application):
            await _complete_lead(ctx, application, _message_text(fresh[-1]) if fresh else "")
            return "new_leads"
        if fresh:
            incoming_total = len(
                [m for m in messages if _is_incoming(m, ctx.client.user_id) and _message_text(m)]
            )
            if incoming_total == LEAD_ESCALATION_AFTER_MESSAGES:
                await _notify_managers(
                    ctx.bot,
                    ctx.settings,
                    texts.escalation_text(
                        application_id=application.id,
                        listing_title=application.listing_title,
                        name=application.full_name,
                        phone=application.phone,
                        fuel_type=application.fuel_type,
                        monthly_volume=application.monthly_volume,
                        region=application.region,
                        message=_message_text(fresh[-1]),
                    ),
                    keyboard=processed_keyboard(application.id),
                )
                logger.info(
                    "Эскалация по заявке №%s: %s сообщений без полных данных",
                    application.id,
                    incoming_total,
                )
        return "qualifying" if (fresh or answered) else ""

    if not fresh:
        return ""

    # Заполненная/обработанная заявка: менеджеры видят каждое новое сообщение,
    # дальше общается человек (AI-переписка отключена)
    returned = application.status == ApplicationStatus.processed
    await _notify_managers(
        ctx.bot,
        ctx.settings,
        texts.followup_text(
            application_id=application.id,
            messages=[_message_text(m) for m in fresh],
            returned=returned,
        ),
        # Кнопка нужна, только если заявка ещё не обработана
        keyboard=processed_keyboard(application.id) if not returned else None,
    )
    return "followups"


def _outgoing(messages: list[dict[str, Any]], owner_user_id: str) -> list[dict[str, Any]]:
    """Наши ответы (бота и менеджеров) в чате."""
    return [m for m in messages if not _is_incoming(m, owner_user_id)]


def _needs_answer(messages: list[dict[str, Any]], owner_user_id: str) -> bool:
    """Последнее сообщение в чате — от клиента и без ответа."""
    if not messages:
        return False
    return _is_incoming(messages[-1], owner_user_id)


async def _qualify_step(
    ctx: _PollContext,
    session,
    application: Application,
    chat: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    extract: bool,
) -> bool:
    """Шаг квалификации. True — отправили клиенту сообщение.

    Нейронка (один дешёвый вызов, только при новых сообщениях) извлекает
    данные заявки; если всё собрано — `_lead_is_ready` и пересыл менеджерам.
    Клиенту отвечает только шаблон: AI-переписка отключена ради лимитов Groq.
    Ответ уходит, только если последнее сообщение чата — от клиента
    (наши ответы и реплики менеджеров его закрывают).
    """
    chat_id = str(chat.get("id"))
    if extract:
        extracted = await _extract_lead_data(ctx, messages) if ctx.ai else {}
        _apply_extracted(application, extracted)

    if not _needs_answer(messages, ctx.client.user_id):
        await session.commit()
        return False
    if len(_outgoing(messages, ctx.client.user_id)) >= AI_REPLY_MAX_PER_CHAT:
        await session.commit()
        return False  # лимит исчерпан — дальше эскалация менеджерам

    try:
        await ctx.client.send_message(
            ctx.http, chat_id, texts.ask_missing_text(application)
        )
        return True
    except AvitoApiError:
        logger.warning(
            "Заявка №%s: ответ в чат %s не отправлен, повторим в следующий тик",
            application.id,
            chat_id,
        )
        return False
    finally:
        await session.commit()


async def _complete_lead(
    ctx: _PollContext, application: Application, last_message: str
) -> None:
    """Данные собраны: заявка ждёт обработки, менеджерам летит карточка."""
    application.status = ApplicationStatus.filled
    await _notify_managers(
        ctx.bot,
        ctx.settings,
        texts.new_lead_text(
            application_id=application.id,
            listing_title=application.listing_title,
            name=application.full_name,
            phone=application.phone,
            fuel_type=application.fuel_type,
            monthly_volume=application.monthly_volume,
            region=application.region,
            message=last_message,
        ),
        keyboard=processed_keyboard(application.id),
    )
    logger.info(
        "Новый лид с Авито готов: заявка №%s (чат %s)",
        application.id,
        application.avito_chat_id,
    )


def _lead_is_ready(application: Application) -> bool:
    """Все обязательные данные заявки собраны."""
    return all(getattr(application, field) for field in LEAD_REQUIRED_FIELDS)


def _normalize_fuel(value: str) -> str:
    lowered = value.strip().lower()
    if "дт" in lowered or "диз" in lowered:
        return "ДТ"
    if "аи" in lowered or "бенз" in lowered:
        return "АИ"
    return value.strip()[:8]


def _parse_extraction(reply: str | None) -> dict[str, str]:
    """JSON из ответа модели (терпим Markdown-ограды). Пусто при любом сбое."""
    if not reply:
        return {}
    cleaned = reply.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "fuel_type": _normalize_fuel(str(data.get("fuel_type") or "")),
        "monthly_volume": str(data.get("monthly_volume") or "").strip()[:200],
        "region": str(data.get("region") or "").strip()[:200],
        "phone": extract_phone(str(data.get("phone") or "")) or "",
    }


async def _extract_lead_data(
    ctx: _PollContext, messages: list[dict[str, Any]]
) -> dict[str, str]:
    """Groq читает переписку и возвращает поля заявки. Сбой — пустой словарь."""
    if ctx.ai is None:
        return {}
    dialogue = [
        {
            "role": "user" if _is_incoming(m, ctx.client.user_id) else "assistant",
            "content": _message_text(m)[:AI_MESSAGE_TEXT_LIMIT],
        }
        for m in messages[-AI_HISTORY_LIMIT:]
        if _message_text(m)
    ]
    if not dialogue:
        return {}
    prompt = [
        {
            "role": "system",
            "content": (
                "Извлеки из переписки данные для заявки на топливо. Ответ — СТРОГО "
                "JSON: {\"fuel_type\":\"\",\"monthly_volume\":\"\",\"region\":\"\","
                "\"phone\":\"\"}. Пустая строка — данных нет. fuel_type → «АИ» или "
                "«ДТ». monthly_volume — дословно как написал клиент. phone — номер "
                "телефона цифрами."
            ),
        },
        *dialogue,
    ]
    # Лимит не занижаем: reasoning-модели тратят часть бюджета на размышление
    # в отдельном канале, и при 120 токенах ответ приходил пустым
    reply = await ai_client.chat_completion(
        ctx.ai, ctx.settings, prompt, temperature=0.0
    )
    return _parse_extraction(reply)


def _apply_extracted(application: Application, data: dict[str, str]) -> None:
    """Заполняем только пустые поля — слово клиента важнее домыслов модели."""
    for field, value in data.items():
        if value and not getattr(application, field):
            setattr(application, field, value)


async def _notify_managers(
    bot: Bot, settings: Settings, text: str, keyboard=None
) -> None:
    for manager_id in settings.admin_ids:
        try:
            await bot.send_message(manager_id, text, reply_markup=keyboard)
        except TelegramAPIError:
            logger.exception(
                "Уведомление по Авито не доставлено менеджеру %s", manager_id
            )
