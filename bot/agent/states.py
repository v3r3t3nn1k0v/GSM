from aiogram.fsm.state import State, StatesGroup


class AgentForm(StatesGroup):
    """Анкета агента: только телефон."""

    phone = State()
