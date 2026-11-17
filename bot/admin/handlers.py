import asyncio
import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.models import ApplicationStatus
from app.applications.service import ApplicationService
from app.users.service import UserService
from bot.application.keyboards import ProcessedCallback

from .keyboards import (
    PAGE_SIZE,
    APPS_ACTIVE,
    APPS_ALL,
    APPS_PROCESSED,
    AdminAction,
    ACTION_APPS,
    ACTION_BROADCAST,
    ACTION_BROADCAST_CANCEL,
    ACTION_BROADCAST_CONFIRM,
    ACTION_MENU,
    ACTION_STATS,
    admin_menu_keyboard,
    applications_keyboard,
    back_to_menu_keyboard,
    broadcast_confirm_keyboard,
)
from .states import BroadcastStates
from .texts import (
    ADMIN_MENU_TEXT,
    BROADCAST_ASK,
    BROADCAST_CANCELLED,
    BROADCAST_DONE,
    BROADCAST_EMPTY,
    BROADCAST_PREVIEW,
    applications_page_text,
    stats_text,
)

logger = logging.getLogger(__name__)

# Фильтр списка заявок → статус в БД
_APPS_FILTER_STATUS: dict[str, ApplicationStatus | None] = {
    APPS_ACTIVE: ApplicationStatus.filled,
    APPS_PROCESSED: ApplicationStatus.processed,
    APPS_ALL: None,
}


async def cmd_admin(message: Message, state: FSMContext) -> None:
    """Вход в админ-панель (доступ закрыт фильтром IsAdmin на роутере)."""
    await state.clear()
    await message.answer(ADMIN_MENU_TEXT, reply_markup=admin_menu_keyboard())


async def open_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(callback, ADMIN_MENU_TEXT, admin_menu_keyboard())
    await callback.answer()


async def show_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    user_stats = await UserService(session).stats()
    app_stats = await ApplicationService(session).stats()
    await _edit(callback, stats_text(user_stats, app_stats), admin_menu_keyboard())
    await callback.answer()


async def show_applications(
    callback: CallbackQuery, callback_data: AdminAction, session: AsyncSession
) -> None:
    apps_filter = callback_data.tab or APPS_ACTIVE
    status = _APPS_FILTER_STATUS.get(apps_filter)
    offset = max(callback_data.offset or 0, 0)
    applications, total = await ApplicationService(session).list_page(
        limit=PAGE_SIZE, offset=offset, status=status
    )
    await _edit(
        callback,
        applications_page_text(applications, offset, total, apps_filter),
        applications_keyboard(offset, total, apps_filter),
    )
    await callback.answer()


async def process_application(
    callback: CallbackQuery,
    callback_data: ProcessedCallback,
    session: AsyncSession,
) -> None:
    """Кнопка «Заявка обработана» в сообщении с заявкой."""
    application = await ApplicationService(session).get_application(
        callback_data.application_id
    )
    if application is None:
        await callback.answer("Заявка не найдена 🤷", show_alert=True)
        return
    marked = await ApplicationService(session).mark_processed(application)
    if not marked:
        await callback.answer("Уже отмечена обработанной ✅")
        return
    # Дополняем исходное сообщение и убираем кнопку
    text = (callback.message.html_text or "") + "\n\n✅ <b>Заявка обработана</b>"
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer("Отмечена обработанной ✅")


async def start_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastStates.waiting_message)
    await _edit(callback, BROADCAST_ASK, back_to_menu_keyboard())
    await callback.answer()


async def receive_broadcast_message(message: Message, state: FSMContext) -> None:
    text = (message.text or message.caption or "").strip()
    if not text:
        await message.answer(BROADCAST_EMPTY)
        return
    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastStates.waiting_confirm)
    # Предпросмотр без разметки, чтобы админ видел ровно то, что получат пользователи
    await message.answer(text, parse_mode=None)
    await message.answer(BROADCAST_PREVIEW, reply_markup=broadcast_confirm_keyboard())


async def confirm_broadcast(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    data = await state.get_data()
    text = data.get("broadcast_text")
    await state.clear()
    if not text:
        await _edit(callback, ADMIN_MENU_TEXT, admin_menu_keyboard())
        await callback.answer()
        return

    telegram_ids = await UserService(session).all_telegram_ids()
    sent = failed = 0
    for telegram_id in telegram_ids:
        try:
            await callback.bot.send_message(telegram_id, text, parse_mode=None)
            sent += 1
        except TelegramAPIError:
            failed += 1
        await asyncio.sleep(0.05)  # мягкий лимит Telegram

    await callback.message.answer(
        BROADCAST_DONE.format(sent=sent, failed=failed, total=len(telegram_ids))
    )
    await _edit(callback, ADMIN_MENU_TEXT, admin_menu_keyboard())
    await callback.answer("Готово")


async def cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(callback, BROADCAST_CANCELLED, admin_menu_keyboard())
    await callback.answer()


async def _edit(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Редактируем сообщение, игнорируя «message is not modified»."""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass
