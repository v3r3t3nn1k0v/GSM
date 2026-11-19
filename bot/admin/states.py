from aiogram.fsm.state import State, StatesGroup


class BroadcastStates(StatesGroup):
    """Массовая рассылка: ввод текста → выбор аудитории → подтверждение."""

    waiting_message = State()
    waiting_audience = State()
    waiting_confirm = State()
