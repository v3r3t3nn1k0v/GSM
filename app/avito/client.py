"""Клиент официального Avito Messenger API.

Авторизация — OAuth2 client_credentials: токен живёт ~24 часа, обновляем
заранее и кэшируем в памяти воркера. Все URL собраны в одном месте:
при подключении боевых ключей сверить версии путей с developers.avito.ru
(меняться должны только константы ниже, не логика).
"""
import logging
import time
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "https://api.avito.ru"
TOKEN_URL = f"{BASE_URL}/token"
CHATS_URL = f"{BASE_URL}/messenger/v2/accounts/{{user_id}}/chats"
CHAT_MESSAGES_URL = f"{BASE_URL}/messenger/v3/accounts/{{user_id}}/chats/{{chat_id}}/messages/"
SEND_MESSAGE_URL = f"{BASE_URL}/messenger/v1/accounts/{{user_id}}/chats/{{chat_id}}/messages/send"

# Токен обновляем за 5 минут до истечения
_TOKEN_REFRESH_MARGIN = 300


class AvitoApiError(RuntimeError):
    """Ошибка обращения к Avito API."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AvitoSubscriptionError(AvitoApiError):
    """HTTP 402: на аккаунте нет подписки с API мессенджера."""


class AvitoClient:
    """Тонкий клиент: токен + GET/POST, без бизнес-логики."""

    def __init__(self, client_id: str, client_secret: str, user_id: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._user_id = user_id
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def user_id(self) -> str:
        return self._user_id

    async def _get_token(self, session: aiohttp.ClientSession) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        async with session.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        ) as response:
            if response.status != 200:
                raise AvitoApiError(
                    f"Не получен токен Авито (HTTP {response.status}): {await response.text()}"
                )
            payload = await response.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.monotonic() + int(
            payload.get("expires_in", 86400)
        ) - _TOKEN_REFRESH_MARGIN
        return self._token

    async def _get(
        self,
        session: aiohttp.ClientSession,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        token = await self._get_token(session)
        async with session.get(
            url, params=params, headers={"Authorization": f"Bearer {token}"}
        ) as response:
            if response.status != 200:
                body = await response.text()
                if response.status == 402:
                    raise AvitoSubscriptionError(
                        f"GET {url} -> HTTP 402: {body}", status=402
                    )
                raise AvitoApiError(
                    f"GET {url} -> HTTP {response.status}: {body}",
                    status=response.status,
                )
            return await response.json()

    async def fetch_updated_chats(
        self, session: aiohttp.ClientSession, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Чаты с обновлениями (непрочитанные в первую очередь)."""
        payload = await self._get(
            session,
            CHATS_URL.format(user_id=self._user_id),
            params={"unread_only": "false", "limit": limit, "offset": 0},
        )
        # Формат ответа может быть {"chats": [...]} или список — берём как есть
        if isinstance(payload, dict):
            return list(payload.get("chats") or [])
        return list(payload or [])

    async def fetch_chat_messages(
        self, session: aiohttp.ClientSession, chat_id: str
    ) -> list[dict[str, Any]]:
        """Все сообщения чата (свежие фильтрует сервис по курсору)."""
        payload = await self._get(
            session, CHAT_MESSAGES_URL.format(user_id=self._user_id, chat_id=chat_id)
        )
        if isinstance(payload, dict):
            return list(payload.get("messages") or [])
        return list(payload or [])

    async def send_message(
        self, session: aiohttp.ClientSession, chat_id: str, text: str
    ) -> None:
        """Отправить сообщение от имени аккаунта (автоответ)."""
        token = await self._get_token(session)
        async with session.post(
            SEND_MESSAGE_URL.format(user_id=self._user_id, chat_id=chat_id),
            json={"message": {"text": text}, "type": "text"},
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            if response.status != 200:
                raise AvitoApiError(
                    f"POST send_message -> HTTP {response.status}: {await response.text()}"
                )
