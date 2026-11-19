import logging
import re

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import Application
from app.applications.service import ApplicationService
from app.config import get_settings
from app.users.service import UserService

from .keyboards import (
    FuelTypeCallback,
    START_APPLICATION_CB,
    fuel_type_keyboard,
    processed_keyboard,
    reply_keyboard_done,
    share_contact_keyboard,
)
from .states import ApplicationForm
from .texts import (
    ANSWER_TOO_LONG,
    APPLICATION_DONE,
    COMMAND_DURING_FORM,
    FUEL_CHOSEN_HINT,
    NOT_A_TEXT,
    PHONE_INVALID,
    Q_DELIVERY,
    Q_FUEL_TYPE,
    Q_FULL_NAME,
    Q_GAS_NETWORKS,
    Q_MONTHLY_VOLUME,
    Q_PHONE,
    Q_REGION,
    RESUME_TEXT,
    STALE_APPLICATION,
    manager_application_text,
)

logger = logging.getLogger(__name__)

ANSWER_MAX_LENGTH = 500
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")


async def start_application(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Кнопка «Заполнить анкету»: новая заявка или продолжение открытой."""
    await state.clear()
    user, _ = await UserService(session).get_or_create(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        nickname=callback.from_user.first_name or "",
        premium=bool(callback.from_user.is_premium),
    )
    application, created = await ApplicationService(session).start_for_user(user)
    await state.update_data(application_id=application.id)

    next_state, question, reply_markup = _next_step(application)
    await state.set_state(next_state)
    if created:
        await _edit_or_answer(callback, question, reply_markup)
    else:
        await _edit_or_answer(callback, RESUME_TEXT)
        await callback.message.answer(question, reply_markup=reply_markup)
    await callback.answer()


async def choose_fuel(
    callback: CallbackQuery,
    callback_data: FuelTypeCallback,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Выбор вида топлива кнопкой АИ/ДТ."""
    data = await state.get_data()
    is_current = (
        await state.get_state() == ApplicationForm.fuel_type.state
        and callback_data.application_id == data.get("application_id")
    )
    application = None
    if is_current:
        application = await ApplicationService(session).get_open_application(
            application_id=callback_data.application_id,
            telegram_id=callback.from_user.id,
        )
    if application is None:
        await state.clear()
        await callback.answer(STALE_APPLICATION, show_alert=True)
        return

    await ApplicationService(session).save_answer(
        application, "fuel_type", callback_data.value
    )
    await state.set_state(ApplicationForm.gas_networks)
    await _edit_or_answer(callback, Q_GAS_NETWORKS)
    await callback.answer("Записал ✅")


async def answer_gas_networks(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await _process_text_answer(
        message,
        session,
        state,
        field="gas_networks",
        next_state=ApplicationForm.monthly_volume,
        next_question=Q_MONTHLY_VOLUME,
    )


async def answer_monthly_volume(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await _process_text_answer(
        message,
        session,
        state,
        field="monthly_volume",
        next_state=ApplicationForm.region,
        next_question=Q_REGION,
    )


async def answer_region(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await _process_text_answer(
        message,
        session,
        state,
        field="region",
        next_state=ApplicationForm.delivery_needed,
        next_question=Q_DELIVERY,
    )


async def answer_delivery_needed(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await _process_text_answer(
        message,
        session,
        state,
        field="delivery_needed",
        next_state=ApplicationForm.full_name,
        next_question=Q_FULL_NAME,
    )


async def answer_full_name(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await _process_text_answer(
        message,
        session,
        state,
        field="full_name",
        next_state=ApplicationForm.phone,
        next_question=Q_PHONE,
        next_reply_markup=share_contact_keyboard(),
    )


async def answer_phone(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Телефон текстом — последний вопрос, завершаем заявку."""
    text = (message.text or "").strip()
    if text and not text.startswith("/") and not _is_phone(text):
        await message.answer(PHONE_INVALID)
        return
    await _process_text_answer(
        message,
        session,
        state,
        field="phone",
        next_state=None,
        next_question=None,
        next_reply_markup=reply_keyboard_done(),
    )


async def answer_phone_contact(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Телефон кнопкой «Поделиться контактом»."""
    if message.contact is None or not message.contact.phone_number:
        await message.answer(NOT_A_TEXT)
        return
    data = await state.get_data()
    application_id = data.get("application_id")
    application = None
    if application_id is not None:
        application = await ApplicationService(session).get_open_application(
            application_id=application_id, telegram_id=message.from_user.id
        )
    if application is None:
        await state.clear()
        await message.answer(STALE_APPLICATION, reply_markup=reply_keyboard_done())
        return
    await ApplicationService(session).save_answer(
        application, "phone", message.contact.phone_number
    )
    await message.answer(
        "Спасибо, контакт записал ✅", reply_markup=reply_keyboard_done()
    )
    await _finish_application(message, session, state, application)


async def fuel_type_text(message: Message) -> None:
    """Текст вместо нажатия кнопки на первом шаге."""
    await message.answer(FUEL_CHOSEN_HINT)


async def not_a_text(message: Message) -> None:
    """Фото/стикер/голос вместо текстового ответа."""
    await message.answer(NOT_A_TEXT)


def _next_step(
    application: Application,
) -> tuple[State, str, InlineKeyboardMarkup | ReplyKeyboardMarkup | None]:
    """Первый незаполненный вопрос анкеты (для старта и возобновления)."""
    if application.fuel_type is None:
        return ApplicationForm.fuel_type, Q_FUEL_TYPE, fuel_type_keyboard(application.id)
    if application.gas_networks is None:
        return ApplicationForm.gas_networks, Q_GAS_NETWORKS, None
    if application.monthly_volume is None:
        return ApplicationForm.monthly_volume, Q_MONTHLY_VOLUME, None
    if application.region is None:
        return ApplicationForm.region, Q_REGION, None
    if application.delivery_needed is None:
        return ApplicationForm.delivery_needed, Q_DELIVERY, None
    if application.full_name is None:
        return ApplicationForm.full_name, Q_FULL_NAME, None
    return ApplicationForm.phone, Q_PHONE, share_contact_keyboard()


def _is_phone(text: str) -> bool:
    return bool(PHONE_RE.match(text)) and len(re.sub(r"\D", "", text)) >= 7


async def _process_text_answer(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    *,
    field: str,
    next_state: State | None,
    next_question: str | None,
    next_reply_markup: ReplyKeyboardMarkup | None = None,
) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await message.answer(COMMAND_DURING_FORM)
        return
    if not text or len(text) > ANSWER_MAX_LENGTH:
        await message.answer(ANSWER_TOO_LONG)
        return

    data = await state.get_data()
    application_id = data.get("application_id")
    application = None
    if application_id is not None:
        application = await ApplicationService(session).get_open_application(
            application_id=application_id, telegram_id=message.from_user.id
        )
    if application is None:
        await state.clear()
        await message.answer(STALE_APPLICATION, reply_markup=reply_keyboard_done())
        return

    await ApplicationService(session).save_answer(application, field, text)
    if next_question is None or next_state is None:
        await _finish_application(message, session, state, application)
    else:
        await state.set_state(next_state)
        await message.answer(next_question, reply_markup=next_reply_markup)


async def _finish_application(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    application: Application,
) -> None:
    await ApplicationService(session).complete(application)
    await state.clear()
    await message.answer(APPLICATION_DONE)
    await _notify_managers(message.bot, application)


async def _notify_managers(bot: Bot, application: Application) -> None:
    """Заявка уходит админам (= менеджерам) с кнопкой «Обработана»."""
    settings = get_settings()
    if not settings.admin_ids:
        logger.error(
            "ADMIN_IDS пуст: заявка №%s не отправлена менеджерам", application.id
        )
        return
    text = manager_application_text(
        application_id=application.id,
        nickname=application.user.nickname,
        username=application.user.username,
        telegram_id=application.user.telegram_id,
        fuel_type=application.fuel_type,
        gas_networks=application.gas_networks,
        monthly_volume=application.monthly_volume,
        region=application.region,
        delivery_needed=application.delivery_needed,
        full_name=application.full_name,
        phone=application.phone,
        created_at=application.created_at,
    )
    keyboard = processed_keyboard(application.id)
    for manager_id in settings.admin_ids:
        try:
            await bot.send_message(manager_id, text, reply_markup=keyboard)
        except TelegramAPIError:
            logger.exception(
                "Заявка №%s не доставлена менеджеру %s", application.id, manager_id
            )


async def _edit_or_answer(
    callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Редактируем сообщение, а если оно недоступно — отправляем новое."""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup)
