import asyncio
import logging

from app.avito.service import poll_once
from app.reminders.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="avito.poll_messages")
def poll_messages() -> dict:
    """Тик поллинга Авито (запускается beat'ом каждые 30 секунд).

    Никогда не бросает исключение: упавший тик не должен ронять воркер —
    следующий тик через 30 секунд попробует снова.
    """
    try:
        return asyncio.run(poll_once())
    except Exception:
        logger.exception("Поллинг Авито: критическая ошибка тика")
        return {"error": "см. логи воркера"}
