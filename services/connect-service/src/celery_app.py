from celery import Celery
from .config import settings

celery_app = Celery(
    "connect_service",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.imports = (
    "src.tasks.tp_webhook_retry_task",
)
