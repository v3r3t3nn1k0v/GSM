import html

from app.applications.models import Application, ApplicationStatus
from app.applications.schemas import ApplicationStats
from app.users.schemas import UserStats

ADMIN_MENU_TEXT = "🛠 <b>Админ-панель</b>\n\nВыберите раздел:"

BROADCAST_ASK = (
    "📢 Отправьте сообщение, которое нужно разослать пользователям бота."
)
BROADCAST_EMPTY = "Сообщение пустое. Отправьте текст или вернитесь в меню."
BROADCAST_AUDIENCE = "☝️ Предпросмотр сообщения выше. Кому его разослать?"
BROADCAST_PREVIEW = "Аудитория: {audience}.\n\n☝️ Разослать это сообщение?"
BROADCAST_CANCELLED = "Рассылка отменена."
BROADCAST_DONE = (
    "📢 Рассылка завершена ({audience}): доставлено {sent}, не доставлено {failed} "
    "из {total} получателей."
)


def stats_text(user_stats: UserStats, app_stats: ApplicationStats) -> str:
    return (
        "📊 <b>Статистика</b>\n"
        "\n"
        f"👥 Пользователей: {user_stats.total} (+{user_stats.new_today} сегодня)\n"
        "\n"
        f"📋 Заявок всего: {app_stats.total}\n"
        f"  • новые (ждут обработки): {app_stats.filled}\n"
        f"  • обработаны: {app_stats.processed}\n"
        f"  • в заполнении: {app_stats.partly_filled}"
    )


_APPS_FILTER_LABELS = {
    "active": "новые",
    "processed": "обработанные",
    "all": "все",
}

_APPS_EMPTY_TEXT = {
    "active": "🆕 Новых заявок нет — всё обработано 👍",
    "processed": "✅ Обработанных заявок пока нет.",
    "all": "📋 Заявок пока нет.",
}

_STATUS_ICONS = {
    ApplicationStatus.filled: "🆕",
    ApplicationStatus.processed: "✅",
    ApplicationStatus.partly_filled: "⏳",
}


def applications_page_text(
    applications: list[Application], offset: int, total: int, apps_filter: str
) -> str:
    if not applications:
        return _APPS_EMPTY_TEXT.get(apps_filter, _APPS_EMPTY_TEXT["all"])
    start = offset + 1
    end = offset + len(applications)
    label = _APPS_FILTER_LABELS.get(apps_filter, "все")
    lines = [f"📋 <b>Заявки {start}–{end} из {total}</b> ({label})", ""]
    for application in applications:
        status = _STATUS_ICONS.get(application.status, "•")
        name = html.escape(application.full_name or application.user.nickname or "—")
        if application.user.username:
            name += f" (@{application.user.username})"
        who = name
        details = " · ".join(
            html.escape(part)
            for part in (
                application.fuel_type,
                application.region,
                application.monthly_volume,
                application.phone,
            )
            if part
        )
        lines.append(
            f"{status} №{application.id} · {application.created_at:%d.%m.%Y} · {who}\n"
            f"     {details or '—'}"
        )
    return "\n".join(lines)
