from aiogram.fsm.state import State, StatesGroup


class BroadcastStates(StatesGroup):
    """Массовая рассылка: ввод текста → подтверждение."""

    waiting_message = State()
    waiting_confirm = State()
