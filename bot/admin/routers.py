from aiogram import F, Router
from aiogram.filters import Command, StateFilter

from bot.filters.admin import IsAdmin
from bot.application.keyboards import ProcessedCallback

from . import handlers
from .keyboards import (
    ACTION_APPS,
    ACTION_BROADCAST,
    ACTION_BROADCAST_CANCEL,
    ACTION_BROADCAST_CONFIRM,
    ACTION_MENU,
    ACTION_STATS,
    AdminAction,
    BroadcastAudience,
)
from .states import BroadcastStates

# Весь роутер доступен только администраторам из ADMIN_IDS
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

router.message.register(handlers.cmd_admin, Command("admin"))

router.callback_query.register(
    handlers.open_menu, AdminAction.filter(F.action == ACTION_MENU)
)
router.callback_query.register(
    handlers.show_stats, AdminAction.filter(F.action == ACTION_STATS)
)
router.callback_query.register(
    handlers.show_applications, AdminAction.filter(F.action == ACTION_APPS)
)
router.callback_query.register(
    handlers.start_broadcast, AdminAction.filter(F.action == ACTION_BROADCAST)
)
router.callback_query.register(
    handlers.choose_broadcast_audience,
    BroadcastAudience.filter(),
    StateFilter(BroadcastStates.waiting_audience),
)
router.callback_query.register(
    handlers.confirm_broadcast,
    AdminAction.filter(F.action == ACTION_BROADCAST_CONFIRM),
    StateFilter(BroadcastStates.waiting_confirm),
)
router.callback_query.register(
    handlers.cancel_broadcast, AdminAction.filter(F.action == ACTION_BROADCAST_CANCEL)
)

# Кнопка «Заявка обработана» под заявкой, пришедшей менеджеру
router.callback_query.register(
    handlers.process_application, ProcessedCallback.filter()
)

router.message.register(
    handlers.receive_broadcast_message,
    StateFilter(BroadcastStates.waiting_message),
)
