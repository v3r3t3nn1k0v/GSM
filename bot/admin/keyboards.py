from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

PAGE_SIZE = 5

ACTION_MENU = "menu"
ACTION_STATS = "stats"
ACTION_APPS = "apps"
ACTION_BROADCAST = "broadcast"
ACTION_BROADCAST_CONFIRM = "broadcast_confirm"
ACTION_BROADCAST_CANCEL = "broadcast_cancel"

# Аудитории рассылки
AUD_ALL = "all"
AUD_CONSUMERS = "consumers"
AUD_AGENTS = "agents"


class BroadcastAudience(CallbackData, prefix="broadcast"):
    """Выбор аудитории рассылки."""

    audience: str

# Фильтры списка заявок
APPS_ACTIVE = "active"      # заполнены, ждут обработки
APPS_PROCESSED = "processed"
APPS_ALL = "all"


class AdminAction(CallbackData, prefix="admin"):
    action: str
    offset: int | None = None
    tab: str | None = None  # фильтр списка заявок (active/processed/all)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data=AdminAction(action=ACTION_STATS))
    builder.button(
        text="📋 Последние заявки", callback_data=AdminAction(action=ACTION_APPS)
    )
    builder.button(text="📢 Рассылка", callback_data=AdminAction(action=ACTION_BROADCAST))
    builder.adjust(1)
    return builder.as_markup()


def applications_keyboard(offset: int, total: int, apps_filter: str) -> InlineKeyboardMarkup:
    """Список заявок: вкладки-фильтры + постраничная навигация."""
    builder = InlineKeyboardBuilder()
    tabs = (
        ("● Новые", APPS_ACTIVE),
        ("Обработанные", APPS_PROCESSED),
        ("Все", APPS_ALL),
    )
    builder.row(
        *(
            InlineKeyboardButton(
                text=(f"● {label}" if f == apps_filter else label),
                callback_data=AdminAction(action=ACTION_APPS, tab=f).pack(),
            )
            for label, f in tabs
        )
    )
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=AdminAction(
                    action=ACTION_APPS,
                    offset=max(offset - PAGE_SIZE, 0),
                    tab=apps_filter,
                ).pack(),
            )
        )
    if offset + PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=AdminAction(
                    action=ACTION_APPS, offset=offset + PAGE_SIZE, tab=apps_filter
                ).pack(),
            )
        )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="🔙 В меню", callback_data=AdminAction(action=ACTION_MENU).pack()
        )
    )
    return builder.as_markup()


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Отправить", callback_data=AdminAction(action=ACTION_BROADCAST_CONFIRM)
    )
    builder.button(
        text="❌ Отмена", callback_data=AdminAction(action=ACTION_BROADCAST_CANCEL)
    )
    builder.adjust(2)
    return builder.as_markup()


def broadcast_audience_keyboard() -> InlineKeyboardMarkup:
    """Кому разослать сообщение."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⛽ Потребителям", callback_data=BroadcastAudience(audience=AUD_CONSUMERS)
    )
    builder.button(
        text="🤝 Агентам", callback_data=BroadcastAudience(audience=AUD_AGENTS)
    )
    builder.button(text="👥 Всем", callback_data=BroadcastAudience(audience=AUD_ALL))
    builder.adjust(2)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В меню", callback_data=AdminAction(action=ACTION_MENU))
    return builder.as_markup()
