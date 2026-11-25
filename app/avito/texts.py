import html

THANKS_TEXT = (
    "Спасибо! Все данные записал ✅ Наш менеджер свяжется с Вами "
    "в ближайшее время."
)

# Ответ клиенту, который спрашивает про топливо как физическое лицо
INDIVIDUAL_TEXT = (
    "Добрый день 🤝 вам выгоднее заправляться как физлицо через систему лояльности "
    "АЗС ⛽️ у некоторых есть баллы у других кешбэк 💰 вам как физ лицу это будет "
    "выгоднее"
)

# Ответа на вопрос нет в контексте компании
NO_ANSWER_TEXT = (
    "На этот вопрос точнее ответит наш менеджер — свяжитесь с ним, "
    "и он всё расскажет."
)

# Заявка уже у менеджеров: подпись под ответом на новый вопрос
MANAGER_CONTACT_TEXT = "Наш менеджер свяжется с Вами в ближайшее время."

# Приветствие клиенту, который ещё ничего не назвал: предложение заполнить заявку
GREETING_TEXT = (
    "Добрый день🤝\n"
    "1️⃣Какой вид топлива Вас интересует ? 🛢\n"
    "2️⃣Какая сеть АЗС ? ⛽️\n"
    "3️⃣Какой объём в среднем в месяц ? 💸\n"
    "4️⃣Какой у вас Регион ? 🚗\n"
    "\n"
    "Можете написать свой номер и мы с вами свяжемся 🤝⛽️☎️📞\n"
    "Обсудим детали и выгодные цены 🤝"
)

# Что спрашиваем, по каким полям заявки
_FIELD_LABELS = {
    "fuel_type": "вид топлива",
    "monthly_volume": "примерный объём в месяц",
    "region": "регион заправки или доставки",
    "phone": "телефон для связи",
}


def _missing_labels(application) -> list[str]:
    return [
        label
        for field, label in _FIELD_LABELS.items()
        if not getattr(application, field, None)
    ]


def offer_text(application) -> str:
    """Предложение заполнить заявку.

    Клиенту, который ещё ничего не назвал, уходит приветствие с вопросами;
    если часть данных уже есть — перечисляем только недостающее.
    """
    if len(_missing_labels(application)) == len(_FIELD_LABELS):
        return GREETING_TEXT
    return ask_missing_text(application)


def ask_missing_text(application) -> str:
    """Перечисляет ровно те поля, которых ещё не хватает; когда всё собрано — благодарность."""
    missing = _missing_labels(application)
    if not missing:
        return THANKS_TEXT
    fields = ", ".join(missing)
    return (
        "Спасибо за обращение 🙂 Чтобы передать заявку менеджеру, "
        f"укажите, пожалуйста: {fields}."
    )


def compose_answer(answer: str, tail: str) -> str:
    """Ответ на вопрос клиента + подпись (что дозаполнить / «менеджер свяжется»)."""
    return f"{answer}\n\n{tail}"


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
