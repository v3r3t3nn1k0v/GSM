from aiogram import F, Router
from aiogram.filters import StateFilter

from . import handlers
from .keyboards import FuelTypeCallback, START_APPLICATION_CB
from .states import ApplicationForm

router = Router(name="application")

# Вход в воронку и выбор топлива
router.callback_query.register(
    handlers.start_application, F.data == START_APPLICATION_CB
)
router.callback_query.register(handlers.choose_fuel, FuelTypeCallback.filter())

# Текстовые подсказки вместо кнопки на первом шаге
router.message.register(
    handlers.fuel_type_text,
    StateFilter(ApplicationForm.fuel_type),
    F.text,
)

# Ответы на вопросы со свободным вводом
router.message.register(
    handlers.answer_gas_networks,
    StateFilter(ApplicationForm.gas_networks),
    F.text,
)
router.message.register(
    handlers.answer_monthly_volume,
    StateFilter(ApplicationForm.monthly_volume),
    F.text,
)
router.message.register(
    handlers.answer_region,
    StateFilter(ApplicationForm.region),
    F.text,
)
router.message.register(
    handlers.answer_delivery_needed,
    StateFilter(ApplicationForm.delivery_needed),
    F.text,
)
router.message.register(
    handlers.answer_full_name,
    StateFilter(ApplicationForm.full_name),
    F.text,
)

# Телефон: текстом или кнопкой «Поделиться контактом»
router.message.register(
    handlers.answer_phone,
    StateFilter(ApplicationForm.phone),
    F.text,
)
router.message.register(
    handlers.answer_phone_contact,
    StateFilter(ApplicationForm.phone),
    F.contact,
)

# Не-текстовые сообщения (фото, стикеры и т.п.) в любом шаге анкеты
router.message.register(
    handlers.not_a_text,
    StateFilter(
        ApplicationForm.fuel_type,
        ApplicationForm.gas_networks,
        ApplicationForm.monthly_volume,
        ApplicationForm.region,
        ApplicationForm.delivery_needed,
        ApplicationForm.full_name,
        ApplicationForm.phone,
    ),
)
