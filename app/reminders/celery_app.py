from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery("gsm", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    imports=("app.reminders.tasks", "app.avito.tasks"),
    beat_schedule={
        # Каждые 10 минут ищем брошенные заявки и отправляем напоминания
        "send-pending-reminders": {
            "task": "reminders.send_pending",
            "schedule": crontab(minute="*/10"),
        },
        # Раз в 30 секунд забираем новые сообщения из чатов Авито
        # (без ключей AVITO_* задача тихо завершается)
        "avito-poll-messages": {
            "task": "avito.poll_messages",
            "schedule": 30.0,
        },
    },
)
