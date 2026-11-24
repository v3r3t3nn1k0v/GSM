import html

THANKS_TEXT = (
    "Спасибо! Все данные записал ✅ Наш менеджер свяжется с Вами "
    "в ближайшее время."
)

# Что спрашиваем, по каким полям заявки
_FIELD_LABELS = {
    "fuel_type": "вид топлива",
    "monthly_volume": "примерный объём в месяц",
    "region": "регион заправки или доставки",
    "phone": "телефон для связи",
}


def ask_missing_text(application) -> str:
    """Просьба недостающих данных — фолбэк, если AI недоступен.

    Работает и как первый автоответ: перечисляет ровно те поля,
    которых ещё не хватает для заявки.
    """
    missing = [
        label
        for field, label in _FIELD_LABELS.items()
        if not getattr(application, field, None)
    ]
    if not missing:
        return THANKS_TEXT
    fields = ", ".join(missing)
    return (
        "Спасибо за обращение 🙂 Чтобы передать заявку менеджеру, "
        f"укажите, пожалуйста: {fields}."
    )


_LEAD_HEADER = "🆕 <b>Лид с Авито — заявка №{application_id}</b>"


def new_lead_text(
    *,
    application_id: int,
    listing_title: str | None,
    name: str | None,
    phone: str | None,
    fuel_type: str | None = None,
    monthly_volume: str | None = None,
    region: str | None = None,
    message: str,
) -> str:
    """Уведомление менеджерам: заявка с Авито собрана и ждёт обработки."""
    lines = [
        _LEAD_HEADER.format(application_id=application_id),
        "",
        f"📦 Объявление: {html.escape(listing_title or '—')}",
        f"👤 Клиент: {html.escape(name or '—')}",
    ]
    if fuel_type:
        lines.append(f"⛽ Топливо: {html.escape(fuel_type)}")
    if monthly_volume:
        lines.append(f"📦 Объём: {html.escape(monthly_volume)}")
    if region:
        lines.append(f"📍 Регион: {html.escape(region)}")
    if phone:
        lines.append(f"📱 Телефон: {html.escape(phone)}")
    lines += ["", f"💬 «{html.escape(message[:1000])}»"]
    return "\n".join(lines)
