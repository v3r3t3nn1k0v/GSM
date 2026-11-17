from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.service import UserService

from .keyboards import start_keyboard
from .texts import CHOICE_QUESTION, WELCOME_TEXT


async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """Регистрируем (или обновляем) пользователя и показываем приветствие."""
    await state.clear()
    tg_user = message.from_user
    if tg_user is None:
        return
    await UserService(session).get_or_create(
        telegram_id=tg_user.id,
        username=tg_user.username,
        nickname=tg_user.first_name or "",
        premium=bool(tg_user.is_premium),
    )
    await message.answer(
        f"{WELCOME_TEXT}\n\n{CHOICE_QUESTION}", reply_markup=start_keyboard()
    )
