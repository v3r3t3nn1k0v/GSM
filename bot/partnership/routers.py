from aiogram import F, Router

from . import handlers
from .keyboards import PARTNERSHIP_OFFER_CB, PartnershipCallback

router = Router(name="partnership")

router.callback_query.register(handlers.show_offer, F.data == PARTNERSHIP_OFFER_CB)
router.callback_query.register(handlers.offer_answer, PartnershipCallback.filter())
