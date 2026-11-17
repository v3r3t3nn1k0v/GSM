from aiogram import Router
from aiogram.filters import CommandStart

from . import handlers

router = Router(name="users")

router.message.register(handlers.cmd_start, CommandStart())
