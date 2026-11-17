from aiogram.fsm.state import State, StatesGroup


class ApplicationForm(StatesGroup):
    """Шаги анкеты."""

    fuel_type = State()
    gas_networks = State()
    monthly_volume = State()
    region = State()
    delivery_needed = State()
    full_name = State()
    phone = State()
