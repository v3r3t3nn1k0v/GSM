from aiogram import F, Router
from aiogram.filters import StateFilter

from . import handlers
from .keyboards import AgentAnswerCallback
from .states import AgentForm

router = Router(name="agent")

# Ответ на предложение стать агентом
router.callback_query.register(handlers.agent_offer_answer, AgentAnswerCallback.filter())

# Телефон агента: текстом или кнопкой «Поделиться контактом»
router.message.register(
    handlers.answer_phone_text, StateFilter(AgentForm.phone), F.text
)
router.message.register(
    handlers.answer_phone_contact, StateFilter(AgentForm.phone), F.contact
)
