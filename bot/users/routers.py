from aiogram import F, Router
from aiogram.filters import CommandStart

from . import handlers
from .keyboards import CHECK_SUBSCRIPTION_CB, ROLE_NO_CB, ROLE_YES_CB

router = Router(name="users")

router.message.register(handlers.cmd_start, CommandStart())
router.callback_query.register(
    handlers.choose_role, F.data.in_({ROLE_YES_CB, ROLE_NO_CB})
)
router.callback_query.register(
    handlers.check_subscription, F.data == CHECK_SUBSCRIPTION_CB
)
