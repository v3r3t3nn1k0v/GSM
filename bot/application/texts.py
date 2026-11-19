import html
from datetime import datetime

Q_FUEL_TYPE = "Какой вид топлива Вас интересует?"
Q_GAS_NETWORKS = "Какими сетями АЗС Вы предпочитаете пользоваться?"
Q_MONTHLY_VOLUME = "Какой ориентировочный объём топлива необходим в месяц?"
Q_REGION = "В каком регионе планируете заправляться?"
Q_DELIVERY = "🚛 Нужна ли доставка топлива на Ваши объекты?"
Q_FULL_NAME = "👤 Напишите Ваше ФИО — чтобы менеджер знал, к кому обращаться."
Q_PHONE = (
    "📱 Последний вопрос: укажите номер телефона для связи.\n\n"
    "Можно написать текстом или нажать кнопку «Поделиться контактом»."
)
PHONE_INVALID = (
    "Похоже, это не номер телефона. Пример: +7 921 123-45-67. Попробуйте ещё раз."
)

RESUME_TEXT = "Продолжим заполнять заявку — осталось ответить ещё на несколько вопросов 🙂"
FUEL_CHOSEN_HINT = "Пожалуйста, выберите вид топлива кнопкой ниже 👇"
NOT_A_TEXT = "Пожалуйста, отправьте ответ обычным текстовым сообщением."
ANSWER_TOO_LONG = "Ответ слишком длинный — до 500 символов. Попробуйте короче."
COMMAND_DURING_FORM = (
    "Вы в процессе заполнения анкеты. Отправьте ответ текстом "
    "или нажмите /start, чтобы начать заново."
)
STALE_APPLICATION = "Эта заявка уже неактуальна. Нажмите /start, чтобы начать новую."
APPLICATION_DONE = "✅ Спасибо! Заявка отправлена, менеджер свяжется с Вами в ближайшее время."


def manager_application_text(
    *,
    application_id: int,
    nickname: str,
    username: str | None,
    telegram_id: int,
    fuel_type: str | None,
    gas_networks: str | None,
    monthly_volume: str | None,
    region: str | None,
    delivery_needed: str | None,
    full_name: str | None,
    phone: str | None,
    created_at: datetime,
) -> str:
    """Формат заявки для менеджеров."""
    who = html.escape(full_name or nickname) or "—"
    if username:
        who += f" (@{html.escape(username)})"
    return (
        f"🆕 <b>Новая заявка №{application_id}</b>\n"
        "\n"
        f"👤 Клиент: {who}\n"
        f"🔗 <a href='tg://user?id={telegram_id}'>Написать клиенту</a>\n"
        f"📱 Телефон: {html.escape(phone or '—')}\n"
        "\n"
        f"⛽ Топливо: {html.escape(fuel_type or '—')}\n"
        f"🏪 Сети АЗС: {html.escape(gas_networks or '—')}\n"
        f"📦 Объём в месяц: {html.escape(monthly_volume or '—')}\n"
        f"📍 Регион: {html.escape(region or '—')}\n"
        f"🚛 Доставка: {html.escape(delivery_needed or '—')}\n"
        "\n"
        f"🕒 {created_at:%d.%m.%Y %H:%M} UTC"
    )
