# GSM — бот-воронка для рынка ГСМ

Telegram-бот воронки: приветствие → анкета (5 вопросов) → заявка менеджерам в ЛС.
Брошенные заявки получают напоминание через celery-воркер, все события пишутся в журнал.

## Стек

Python 3.12, aiogram 3, SQLAlchemy 2 (async + asyncpg), Alembic, Celery + Redis, pydantic v2, docker-compose.

## Запуск

```bash
cp .env.example .env   # заполнить BOT_TOKEN, ADMIN_IDS, MANAGER_IDS
docker compose up --build
```

Поднимаются 5 сервисов: `db` (PostgreSQL 16), `redis`, `bot` (long polling, применяет миграции при старте), `worker` (celery), `beat` (расписание напоминаний каждые 10 минут).

## Переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | токен от @BotFather |
| `TG_PROXY_URL` | прокси для доступа к Telegram API (`socks5://user:pass@host:port`, `socks4://`, `http(s)://`); пусто — напрямую. Нужен, если VPS не может обращаться к `api.telegram.org` |
| `DATABASE_URL` | `postgresql+asyncpg://gsm:gsm@db:5432/gsm` (в docker) |
| `REDIS_URL` | `redis://redis:6379/0` (в docker) |
| `ADMIN_IDS` | ID администраторов (= менеджеров) через запятую: доступ к `/admin`, приём заявок, кнопка «Обработана» |
| `REMINDER_DELAY_MINUTES` | через сколько минут простоя слать напоминание (60) |
| `REMINDER_MAX_COUNT` | максимум напоминаний на заявку (1) |
| `CHANNEL_URL` | ссылка на Telegram-канал для кнопки «Подписаться» (пустая — кнопки не будет) |

## VPS не видит Telegram: `TelegramNetworkError: Request timeout error`

Первый запрос бота — `get_me()` к `api.telegram.org`. Таймаут на нём означает,
что сервер не может обратиться к Telegram напрямую (частая ситуация на хостингах
в РФ — они блокируют Telegram API). Приложение при этом не падает, а ждёт связи
и повторяет попытку каждые 15 секунд; чтобы бот заработал, поднимите прокси
и укажите его в `TG_PROXY_URL`.

Вариант без покупки прокси — SOCKS5-туннель по SSH до любой машины,
где Telegram доступен. Чтобы туннель не зависел от открытого окна SSH и
переживал перезагрузки, оформите его systemd-сервисом на VPS.
Сначала вход на зарубежную машину по ключу (без пароля):

```bash
ssh-keygen -t ed25519
ssh-copy-id user@foreign-server
```

Затем `/etc/systemd/system/ssh-tunnel.service`:

```ini
[Unit]
Description=SSH SOCKS-туннель для доступа к Telegram API
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ssh -N -D 172.17.0.1:1080 \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new \
    user@foreign-server
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now ssh-tunnel
ss -tlnp | grep 1080   # должно быть LISTEN на 172.17.0.1:1080
```

и в `.env` (адрес `172.17.0.1` — это сам VPS, каким его видят контейнеры):

```
TG_PROXY_URL=socks5://172.17.0.1:1080
```

Если в логах бота `Couldn't connect to proxy 172.17.0.1:1080 [Errno 111]` —
на VPS ничего не слушает порт 1080: туннель не запущен (`systemctl status
ssh-tunnel`) или ssh запущен без адреса привязки (слушает только 127.0.0.1,
контейнеры его не видят — нужен именно `-D 172.17.0.1:1080`). Бот при этом
не умирает, а повторяет попытку каждые 15 секунд.

Подойдёт и любой внешний/платный прокси в формате
`socks5://user:pass@host:port` или `http://host:port`. После правки `.env`:
`docker compose up -d --force-recreate bot worker`.

## Логика

- **/start** — пользователь записывается в `users`, получает приветствие и развилку: «⛽ Заполнить заявку» / «🤝 Партнёрская программа».
- **Партнёрская ветка** — текст предложения + inline «Да/Нет»: «Да» → PDF с условиями (`assets/partnership.pdf`) и кнопка вернуться к заявке; «Нет» → приглашение подписаться на канал (`CHANNEL_URL`).
- **Анкета** — вид топлива (кнопки АИ/ДТ), сети АЗС, объём/мес, регион, доставка, ФИО (свободный текст), телефон (текстом или кнопкой «Поделиться контактом»). Заявка создаётся при первом шаге со статусом `partly_filled`, при завершении — `filled` и рассылка админам-менеджерам. Повторное нажатие кнопки продолжает открытую заявку с места остановки.
- **Админ = менеджер**: один список `ADMIN_IDS` — им доступна `/admin` и им приходят заявки с inline-кнопкой «✅ Заявка обработана». Нажатие переводит заявку в `processed` (пишется в журнал) и убирает её из списка новых.
- **Напоминания** — beat каждые 10 минут; заявкам `partly_filled` без активности дольше `REMINDER_DELAY_MINUTES` и с `reminders_sent < REMINDER_MAX_COUNT` отправляется сообщение. Отправка фиксируется в `logs` (`reminder_sent`).
- **Админка** `/admin` — статистика, заявки с вкладками «Новые / Обработанные / Все» и пагинацией, рассылка всем пользователям.
- **Статусы заявки**: `partly_filled` → `filled` (ждёт обработки) → `processed`.
- **Журнал `logs`** — события `new_user`, `new_application`, `reminder_sent`, `application_processed`.

Проверить напоминания вручную, не дожидаясь beat:

```bash
docker compose run --rm worker celery -A app.reminders.celery_app.celery_app call reminders.send_pending
```

## Структура

```
bot/            слой Telegram: users / application / admin
                (в каждом handlers, routers, keyboards, texts [+ states])
app/            бизнес-логика: users / applications / logs / reminders
                (models, schemas, repository, service)
alembic/        миграции (URL берётся из .env)
```
