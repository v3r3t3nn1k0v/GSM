import html

AUTO_REPLY_TEXT = (
    "Здравствуйте! Спасибо за обращение 🙂\n\n"
    "Подскажите, пожалуйста, какой вид топлива Вам нужен и примерный объём "
    "в месяц — подберём лучшие условия. Наш менеджер уже смотрит Ваше сообщение."
)

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

# Системная инструкция AI-ассистента (Groq): продаём топливо, квалифицируем лид,
# ничего не выдумываем. Используется для живых автоответов в чатах Авито.
AI_SYSTEM_PROMPT = (
    "Ты — вежливый консультант компании «ГСМ»: оптовые продажи топлива "
    "(АИ-92, АИ-95, дизельное топливо ДТ), доставка и заправка на сетях АЗС "
    "в Ленинградской области и Северо-Западе.\n"
    "Правила общения:\n"
    "- Отвечай по-русски, коротко (2–4 предложения), дружелюбно, без канцелярита.\n"
    "- Твоя цель — понять потребность: вид топлива, примерный объём в месяц, "
    "регион заправки/доставки и телефон для связи.\n"
    "- Задавай только ОДИН вопрос за сообщение.\n"
    "- ЦЕНЫ И СКИДКИ НЕ НАЗЫВАЙ никогда: «актуальный прайс и условия пришлёт "
    "менеджер».\n"
    "- Не выдумывай факты, не обещай сроки и объёмы, не обсуждай темы кроме "
    "топлива. Непонятный вопрос — честно скажи, что уточнишь у менеджера.\n"
    "- Если клиент назвал телефон или все данные — поблагодари и скажи, что "
    "менеджер свяжется в ближайшее время."
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


def escalation_text(
    *,
    application_id: int,
    listing_title: str | None,
    name: str | None,
    phone: str | None,
    fuel_type: str | None,
    monthly_volume: str | None,
    region: str | None,
    message: str,
) -> str:
    """Клиент общительный, а данных всё не хватает — зовём человека."""
    lines = [
        f"⚠️ <b>Клиент с Авито общается, но данных не хватает — заявка №{application_id}</b>",
        "",
        f"📦 Объявление: {html.escape(listing_title or '—')}",
        f"👤 Клиент: {html.escape(name or '—')}",
    ]
    known = " · ".join(
        html.escape(part)
        for part in (fuel_type, monthly_volume, region, phone)
        if part
    )
    if known:
        lines.append(f"🧩 Собрано: {known}")
    lines += [
        "",
        "🤖 AI-ассистент дальше сам — подключитесь к чату, если нужна рука человека.",
        "",
        f"💬 Последнее: «{html.escape(message[:500])}»",
    ]
    return "\n".join(lines)


def followup_text(
    *, application_id: int, messages: list[str], returned: bool, ai_reply: str | None = None
) -> str:
    """Новые сообщения клиента по уже существующей заявке."""
    header = (
        f"↩️ <b>Клиент вернулся по обработанной заявке №{application_id}</b>"
        if returned
        else f"💬 <b>Новое сообщение по заявке №{application_id}</b>"
    )
    quoted = "\n".join(f"«{html.escape(text[:1000])}»" for text in messages)
    footer = ""
    if ai_reply:
        footer = f"\n\n🤖 AI-ассистент ответил: «{html.escape(ai_reply[:500])}»"
    return f"{header}\n\n{quoted}{footer}"
