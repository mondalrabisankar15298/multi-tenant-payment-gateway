import json
import logging
import asyncio
from aiokafka import AIOKafkaConsumer
from ..database import get_pool
from ..services.webhook_service import dispatch_webhook
from ..config import settings

logger = logging.getLogger(__name__)


async def start_webhook_consumer(shutdown_event: asyncio.Event):
    """Consumer Group 2: Webhook Delivery — Dispatch HMAC-signed webhooks."""
    consumer = AIOKafkaConsumer(
        settings.KAFKA_TOPIC,
        bootstrap_servers=settings.KAFKA_BROKERS,
        group_id="webhook-delivery-group",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    while not shutdown_event.is_set():
        try:
            await consumer.start()
            pool = await get_pool()
            logger.info("Webhook consumer started")

            while not shutdown_event.is_set():
                try:
                    msg = await asyncio.wait_for(consumer.getone(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                event = msg.value
                logger.info(f"Webhook consumer received: {event.get('event_type')}")

                try:
                    await dispatch_webhook(pool, event)
                except Exception as e:
                    logger.error(f"Webhook dispatch error: {e}")

                await consumer.commit()

        except Exception as e:
            logger.error(f"Webhook consumer error: {e}")
            await asyncio.sleep(5)
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass
