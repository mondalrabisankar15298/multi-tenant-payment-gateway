import json
import logging
import asyncio
import uuid
from aiokafka import AIOKafkaConsumer
from ..database import get_pool
from ..utils.idempotency import try_claim_event
from ..services.schema_manager import ensure_merchant_schema
from ..services.sync_service import sync_event
from ..config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


async def start_db_sync_consumer(shutdown_event: asyncio.Event):
    """Consumer Group 1: DB Sync — Transform and sync data to read DB."""
    consumer = AIOKafkaConsumer(
        settings.KAFKA_TOPIC,
        bootstrap_servers=settings.KAFKA_BROKERS,
        group_id="db-sync-group",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    while not shutdown_event.is_set():
        try:
            await consumer.start()
            pool = await get_pool()
            logger.info("DB Sync consumer started")

            while not shutdown_event.is_set():
                # Await msg with timeout to allow checking shutdown_event
                try:
                    msg = await asyncio.wait_for(consumer.getone(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                event = msg.value
                event_id_str = event.get("event_id")
                try:
                    event_id = uuid.UUID(event_id_str)
                except (ValueError, TypeError):
                    logger.error(f"Invalid event_id: {event_id_str}")
                    await consumer.commit()
                    continue

                logger.info(f"DB Sync received: {event.get('event_type')} for merchant {event.get('merchant_id')}")

                # Idempotency check
                if not await try_claim_event(pool, event_id):
                    await consumer.commit()
                    continue

                try:
                    # If merchant.created, ensure schema exists
                    if event.get("event_type") == "merchant.created.v1":
                        await ensure_merchant_schema(pool, event["schema_name"])

                    # Transform and sync
                    await sync_event(pool, event)

                    # Commit offset
                    await consumer.commit()
                    logger.info(f"DB Sync processed: {event.get('event_type')}")
                except Exception as e:
                    logger.error(f"Failed to sync event {event_id}: {e}", exc_info=True)
                    # Store failed event for manual inspection
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO public.consumer_dead_letter (event_id, event_data, error, created_at) "
                            "VALUES ($1, $2::jsonb, $3, NOW()) ON CONFLICT DO NOTHING",
                            event_id, json.dumps(event, default=str), str(e)[:1000],
                        )
                    await consumer.commit()

        except Exception as e:
            logger.error(f"DB Sync consumer error: {e}")
            await asyncio.sleep(5)
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass
