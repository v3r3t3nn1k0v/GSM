import logging
import re

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.users.service import UserService
from bot.application.keyboards import reply_keyboard_done, share_contact_keyboard

from .keyboards import AgentAnswerCallback, channel_keyboard
from .states import AgentForm
from .texts import (
    AGENT_DONE,
    AGENT_PHONE_INVALID,
    NEWS_ONLY_TEXT,
    Q_AGENT_PHONE,
    agent_manager_text,
)

logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")


async def agent_offer_answer(
    callback: CallbackQuery,
    callback_data: AgentAnswerCallback,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Ответ на предложение стать агентом."""
    if callback_data.accept:
        await state.set_state(AgentForm.phone)
        if callback.message is not None:
            await callback.message.edit_text(
                Q_AGENT_PHONE, reply_markup=share_contact_keyboard()
            )
        await callback.answer()
        return
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            NEWS_ONLY_TEXT, reply_markup=channel_keyboard()
        )
    await callback.answer("Спасибо за ответ!")


async def answer_phone_text(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Телефон агента текстом."""
    text = (message.text or "").strip()
    if text and not text.startswith("/") and not _is_phone(text):
        await message.answer(AGENT_PHONE_INVALID)
        return
    if not text:
        await message.answer(AGENT_PHONE_INVALID)
        return
    await _save_phone(message, session, state, text)


async def answer_phone_contact(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Телефон агента кнопкой «Поделиться контактом»."""
    if message.contact is None or not message.contact.phone_number:
        await message.answer(AGENT_PHONE_INVALID)
        return
    await _save_phone(message, session, state, message.contact.phone_number)


async def _save_phone(
    message: Message, session: AsyncSession, state: FSMContext, phone: str
) -> None:
    """Финал анкеты агента: сохраняем телефон и уведомляем менеджеров."""
    user = await UserService(session).get_by_telegram_id(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer(
            "Что-то пошло не так 🙁 Нажмите /start, чтобы начать заново.",
            reply_markup=reply_keyboard_done(),
        )
        return
    await UserService(session).register_agent(user, phone)
    await state.clear()
    await message.answer(AGENT_DONE, reply_markup=reply_keyboard_done())
    await _notify_managers(message.bot, user.nickname, user.username, user.telegram_id, phone)


async def _notify_managers(
    bot: Bot, nickname: str, username: str | None, telegram_id: int, phone: str
) -> None:
    settings = get_settings()
    text = agent_manager_text(
        nickname=nickname,
        username=username,
        telegram_id=telegram_id,
        phone=phone,
    )
    for manager_id in settings.admin_ids:
        try:
            await bot.send_message(manager_id, text)
        except TelegramAPIError:
            logger.exception("Уведомление об агенте не доставлено менеджеру %s", manager_id)


def _is_phone(text: str) -> bool:
    return bool(PHONE_RE.match(text)) and len(re.sub(r"\D", "", text)) >= 7
