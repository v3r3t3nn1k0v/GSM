"""Поллинг чатов Авито: новые лиды и сообщения по существующим заявкам.

Ключевая идея: один chat_id Авито = одна заявка. Первое сообщение в чате
создаёт «тихую» заявку; менеджерам она уходит РОВНО ОДИН РАЗ — когда
собраны телефон, топливо, объём и регион.

Каждое новое сообщение клиента разбирается через tool calling (Groq):
модель сама выбирает функции — сохранить данные заявки, ответить на вопрос
по контексту компании, ответить физлицу или предложить заполнить заявку.
Любой сбой Groq — откат на шаблон, лид не теряется.
"""
import asyncio
import logging
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai import client as ai_client
from app.applications.models import Application, ApplicationStatus
from app.applications.service import ApplicationService
from app.avito import texts, tools
from app.avito.client import AvitoApiError, AvitoClient, AvitoSubscriptionError
from app.config import Settings
from app.telegram import create_bot
from bot.application.keyboards import processed_keyboard

logger = logging.getLogger(__name__)

# Телефон, оставленный прямо в тексте сообщения (7+ цифр)
PHONE_IN_TEXT_RE = re.compile(r"\+?\d[\d\s\-()]{6,19}\d")

# Экономия лимитов Groq (free-тариф, 8000 токенов/мин): модель дёргаем
# только при новых сообщениях клиента
AI_REPLY_MAX_PER_CHAT = 15        # максимум наших ответов в одном чате
AI_HISTORY_LIMIT = 8              # сколько последних сообщений уходит модели
AI_MESSAGE_TEXT_LIMIT = 300       # обрезаем реплики для экономии токенов

# Квалификация лида: менеджерам заявка падает РОВНО ОДИН РАЗ — когда
# собраны телефон + вид топлива + объём + регион. До и после — только
# ответы клиенту, переписка в TG не дублируется
LEAD_REQUIRED_FIELDS = ("fuel_type", "monthly_volume", "region", "phone")

# Контекст компании: по нему модель отвечает на вопросы клиентов
CONTEXT_PATH = Path(__file__).resolve().parents[2] / "assets" / "avito_context.txt"


@lru_cache
def company_context() -> str:
    """Текст контекста компании (читается один раз на процесс)."""
    try:
        return CONTEXT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        logger.error(
            "Не прочитан контекст компании %s — вопросы клиентов будут уходить менеджеру",
            CONTEXT_PATH,
        )
        return ""


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
    """Время сообщения. У Авито это поле «created» (epoch-секунды) —
    проверено живым ответом API; оставляем «created_at» как запасной вариант."""
    raw = message.get("created", message.get("created_at"))
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
            return await _create_lead(ctx, session, service, chat, messages, incoming)

        return await _process_followup(ctx, session, application, chat, messages)


async def _create_lead(
    ctx: _PollContext,
    session,
    service: ApplicationService,
    chat: dict[str, Any],
    messages: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> str:
    """Первый контакт: тихий лид (partly_filled) + просьба данных + извлечение.

    Менеджерам заявка упадёт РОВНО ОДИН РАЗ — когда собраны все обязательные
    поля (телефон, топливо, объём, регион). Курсор ставим на последнее
    сообщение чата: предыстория (старые чаты при онбординге) не считается
    новой и не пересылается.
    """
    chat_id = str(chat.get("id"))
    last_text = _message_text(incoming[-1])
    application = await service.create_avito_lead(
        chat_id=chat_id,
        last_message_id=_message_id(messages[-1]),
        listing_title=_chat_title(chat),
        full_name=_buyer_name(chat, ctx.client.user_id),
        phone=_find_phone(incoming),
    )
    # Старые чаты при онбординге, где последним ответил менеджер, модель не дёргаем
    await _qualify_step(
        ctx, session, application, chat, messages,
        analyze=_needs_answer(messages, ctx.client.user_id),
    )
    if _lead_is_ready(application):
        await _complete_lead(ctx, session, application, last_text)
        return "new_leads"
    logger.info(
        "Квалификация лида с Авито: заявка №%s ждёт данные (чат %s)",
        application.id,
        chat_id,
    )
    return "qualifying"


async def _process_followup(
    ctx: _PollContext,
    session,
    application: Application,
    chat: dict[str, Any],
    messages: list[dict[str, Any]],
) -> str:
    """Переписка по заявке: до пересылки менеджерам — квалификация, после — ответы на вопросы."""
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
    # Нового нет, и последнее сообщение в чате — наше: нечего делать
    needs_answer = _needs_answer(messages, ctx.client.user_id)
    if not fresh and not needs_answer:
        return ""
    if fresh:
        application.avito_last_message_id = _message_id(fresh[-1])
        # Клиент мог оставить телефон прямо в тексте сообщения
        if not application.phone:
            application.phone = _find_phone(fresh)

    qualifying = application.status == ApplicationStatus.partly_filled
    # Модель дёргаем, только когда новое сообщение осталось без ответа менеджера
    # (на каждом тике по всем чатам выбивался лимит токенов Groq)
    answered = await _qualify_step(
        ctx, session, application, chat, messages,
        analyze=bool(fresh) and needs_answer, completed=not qualifying,
    )
    if qualifying and _lead_is_ready(application):
        await _complete_lead(
            ctx, session, application, _message_text(fresh[-1]) if fresh else ""
        )
        return "new_leads"
    return "qualifying" if qualifying and (fresh or answered) else ""


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
    analyze: bool,
    completed: bool = False,
) -> bool:
    """Шаг обработки новых сообщений. True — отправили клиенту сообщение.

    Function calling (только при новых сообщениях без ответа менеджера):
    классификация с данными заявки, а если клиент задал вопрос — ответ по
    контексту компании. Ответ уходит, только если последнее сообщение чата —
    от клиента (наши ответы и реплики менеджеров его закрывают). Без новых
    сообщений остаётся только повтор шаблона, если прошлый ответ не дошёл.
    """
    chat_id = str(chat.get("id"))
    result = await _analyze(ctx, messages) if analyze and ctx.ai else None
    if result is not None:
        _apply_extracted(application, result.fields)

    if not _needs_answer(messages, ctx.client.user_id):
        await session.commit()
        return False
    if len(_outgoing(messages, ctx.client.user_id)) >= AI_REPLY_MAX_PER_CHAT:
        await session.commit()
        return False  # лимит исчерпан — дальше работает менеджер

    try:
        await ctx.client.send_message(
            ctx.http, chat_id, _reply_text(result, application, completed=completed)
        )
        return True
    except AvitoApiError as exc:
        logger.warning(
            "Заявка №%s: ответ в чат %s не отправлен (%s), повторим в следующий тик",
            application.id,
            chat_id,
            exc,
        )
        return False
    finally:
        await session.commit()


async def _complete_lead(
    ctx: _PollContext, session, application: Application, last_message: str
) -> None:
    """Данные собраны: заявка ждёт обработки, менеджерам летит карточка.

    ВАЖНО: фиксируем статус в БД сразу — без commit заявка оставалась
    partly_filled и карточка менеджерам улетала на каждом тике.
    """
    application.status = ApplicationStatus.filled
    await session.commit()
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


@dataclass
class _Analysis:
    """Итог разбора нового сообщения клиента (function calling)."""

    fields: dict[str, str]          # данные заявки из утверждений клиента
    has_question: bool = False      # клиент задал вопрос
    individual: bool = False        # клиент спрашивает про физлицо
    answer: str | None = None       # ответ на вопрос (None — вопроса не было)


async def _analyze(ctx: _PollContext, messages: list[dict[str, Any]]) -> _Analysis | None:
    """Разбор новых сообщений в два шага. None — сбой Groq (откат на шаблон).

    1) classify_client_message — данные заявки + вопрос/физлицо (без контекста
    компании, дёшево); 2) answer_from_context — только если клиент задал вопрос.
    """
    window = [m for m in messages[-AI_HISTORY_LIMIT:] if _message_text(m)]
    dialogue = [
        {
            "role": "user" if _is_incoming(m, ctx.client.user_id) else "assistant",
            "content": _message_text(m)[:AI_MESSAGE_TEXT_LIMIT],
        }
        for m in window
    ]
    if not dialogue:
        return None
    statements = [
        piece
        for piece in (
            statements_only(_message_text(m))
            for m in window
            if _is_incoming(m, ctx.client.user_id)
        )
        if piece
    ]
    system = tools.CLASSIFY_SYSTEM.format(statements=" | ".join(statements) or "—")
    calls = await ai_client.chat_tool_calls(
        ctx.ai,
        ctx.settings,
        [{"role": "system", "content": system}, *dialogue],
        tools.CLASSIFY_TOOLS,
    )
    if not calls:
        return None
    args = calls[0][1]
    result = _Analysis(
        fields=_normalize_fields(args, " ".join(statements)),
        has_question=args.get("has_question") is True,
        individual=args.get("is_individual") is True,
    )
    if result.has_question and not result.individual:
        result.answer = await _answer_from_context(ctx, dialogue)
    return result


async def _answer_from_context(
    ctx: _PollContext, dialogue: list[dict[str, str]]
) -> str:
    """Ответ на вопрос по контексту компании; не нашли — к менеджеру."""
    system = tools.ANSWER_SYSTEM.format(context=company_context())
    calls = await ai_client.chat_tool_calls(
        ctx.ai,
        ctx.settings,
        [{"role": "system", "content": system}, *dialogue],
        tools.ANSWER_TOOLS,
    )
    if not calls:
        return texts.NO_ANSWER_TEXT
    args = calls[0][1]
    answer = str(args.get("answer") or "").strip()[:1000] if args.get("found") is True else ""
    # Модель может отправить клиента «позвонить» на его же собственный номер —
    # фразы с телефонами из ответа убираем, менеджер свяжется сам
    answer = " ".join(
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", answer)
        if sentence and not extract_phone(sentence)
    )
    return answer or texts.NO_ANSWER_TEXT


# Границы фраз внутри предложения и вопросительные слова в начале фразы
_CLAUSE_DELIMITERS_RE = re.compile(r"[,;]| {2,}|\s+-\s+|\s+(?:а|но|и)\s+", re.IGNORECASE)
_QUESTION_START_RE = re.compile(
    r"^(?:сколько|как\w*|где|куда|когда|почему|зачем|что|кто|чь[иёя]|\S+\s+ли\b)",
    re.IGNORECASE,
)


def statements_only(text: str) -> str:
    """Сообщение клиента без вопросов — данные заявки берём только из утверждений.

    Маленькая модель принимает упоминание в вопросе («доставляете в Новгород?»)
    за регион клиента, поэтому вопросительные фразы отрезаем заранее.
    """
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", text):
        clauses = [c.strip(" ?!.") for c in _CLAUSE_DELIMITERS_RE.split(sentence)]
        if sentence.rstrip().endswith("?"):
            clauses = clauses[:-1]  # вопросительная фраза — последняя перед «?»
        kept.extend(c for c in clauses if c and not _QUESTION_START_RE.match(c))
    return ", ".join(kept)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _stem(value: str) -> str:
    """Начало слова без окончания: «Тверь» и «из Твери» должны совпасть."""
    return value.lower()[: max(3, min(5, len(value) - 1))]


def _normalize_fields(args: dict[str, Any], statements: str) -> dict[str, str]:
    """Аргументы модели → поля заявки.

    Значение оставляем, только если оно действительно встречается в словах
    клиента: модель небольшая и может взять регион или объём из вопроса.
    """
    volume = str(args.get("monthly_volume") or "").strip()[:200]
    region = str(args.get("region") or "").strip()[:200]
    phone = extract_phone(str(args.get("phone") or "")) or ""
    digits = _digits(statements)
    if not _digits(volume) or _digits(volume) not in digits:
        volume = ""
    if len(region) < 3 or _stem(region) not in statements.lower():
        region = ""
    if phone:
        # Клиент пишет «8 921…», нормализованный номер начинается с «+7» —
        # сверяем по значимой части без кода страны
        phone_digits = _digits(phone)
        if len(phone_digits) == 11 and phone_digits[0] == "7":
            phone_digits = phone_digits[1:]
        if phone_digits not in digits:
            phone = ""
    return {
        "fuel_type": _normalize_fuel(str(args.get("fuel_type") or "")),
        "monthly_volume": volume,
        "region": region,
        "phone": phone,
    }


def _find_phone(messages: list[dict[str, Any]]) -> str | None:
    """Первый телефон, встретившийся в тексте сообщений."""
    for message in messages:
        phone = extract_phone(_message_text(message))
        if phone:
            return phone
    return None


def _reply_text(
    result: _Analysis | None, application: Application, *, completed: bool
) -> str:
    """Что отправить клиенту по итогам function calling."""
    if result is not None and result.individual:
        return texts.INDIVIDUAL_TEXT
    if completed:
        # Заявка уже у менеджеров: на вопрос отвечаем, остальное — «менеджер свяжется»
        tail = texts.MANAGER_CONTACT_TEXT if result and result.answer else texts.THANKS_TEXT
    else:
        # Приветствие или сообщение без вопроса — предлагаем заполнить заявку
        tail = texts.ask_missing_text(application)
    if result is None or not result.answer:
        return tail
    return texts.compose_answer(result.answer, tail)


def _apply_extracted(application: Application, data: dict[str, str]) -> None:
    """Заполняем только пустые поля заявки — слово клиента важнее домыслов."""
    for field in LEAD_REQUIRED_FIELDS:
        value = data.get(field)
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
