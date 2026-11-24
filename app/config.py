from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, читаются из .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    # Прокси для доступа к api.telegram.org (socks5://, socks4://, http(s)://).
    # Нужен, если VPS не может обращаться к Telegram напрямую.
    tg_proxy_url: str = ""
    # Ссылка на Telegram-канал для кнопки «Подписаться» (пустая — кнопки не будет)
    channel_url: str = ""
    # ID канала (вида -1001234567890) для проверки подписки: без неё бот не пускает
    # пользователя. Бот должен быть админом канала. Пусто — проверка выключена.
    telegram_channel_id: str = ""

    # NoDecode: строка "1,2,3" из .env парсится нашим валидатором, а не как JSON
    # Админы и менеджеры — один и тот же список прав: и панель, и приём заявок
    admin_ids: Annotated[list[int], NoDecode] = []

    reminder_delay_minutes: int = 60
    reminder_max_count: int = 1

    # Авито: официальное Messenger API (пустые значения — интеграция выключена).
    # Ключи выдаются на developers.avito.ru, user_id — номер профиля Авито.
    avito_client_id: str = ""
    avito_client_secret: str = ""
    avito_user_id: str = ""

    # Groq: AI-ассистент для автоответов клиентам Авито (пусто — шаблонные ответы).
    # Ключ: console.groq.com → API Keys. Если api.groq.com недоступен с VPS —
    # укажите прокси в GROQ_PROXY_URL (тот же формат, что TG_PROXY_URL).
    groq_api_key: str = ""
    # Список актуальных моделей: GET https://api.groq.com/openai/v1/models
    # (llama-3.3-70b-versatile снята с производства — даёт model_not_found)
    groq_model: str = "openai/gpt-oss-120b"
    groq_proxy_url: str = ""

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_id_list(cls, value: object) -> object:
        """Поддержка формата ADMIN_IDS=1,2,3 из .env."""
        if isinstance(value, str):
            return [int(item) for item in value.replace(" ", "").split(",") if item]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
