from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.users.service import UserService
from bot.middlewares.subscription import is_subscriber

from .keyboards import start_keyboard
from .texts import CHOICE_QUESTION, SUBSCRIBE_OK_TEXT, WELCOME_TEXT


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


async def check_subscription(callback: CallbackQuery, bot: Bot) -> None:
    """Кнопка «Я подписался»: перепроверяем подписку и открываем доступ."""
    channel_id = get_settings().telegram_channel_id
    subscribed = await is_subscriber(bot, channel_id, callback.from_user.id)
    if subscribed:
        if callback.message is not None:
            await callback.message.edit_text(SUBSCRIBE_OK_TEXT)
        await callback.answer("Доступ открыт ✅")
    elif subscribed is None:
        await callback.answer(
            "Не удалось проверить подписку, попробуйте ещё раз", show_alert=True
        )
    else:
        await callback.answer(
            "Пока не вижу подписки — проверьте и нажмите ещё раз", show_alert=True
        )
