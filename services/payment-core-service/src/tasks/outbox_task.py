import json
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from kafka import KafkaProducer
from ..celery_app import celery
from ..config import settings

logger = logging.getLogger(__name__)


@celery.task(name="src.tasks.outbox_task.publish_pending_events", bind=True, max_retries=3)
def publish_pending_events(self):
    """Celery beat task: poll domain_events → publish to Kafka."""
    conn = None
    producer = None
    try:
        conn = psycopg2.connect(settings.core_db_url, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = False
        cur = conn.cursor()

        # Fetch pending events with row locking
        cur.execute("""
            SELECT event_id, merchant_id, schema_name, event_type,
                   entity_type, entity_id, payload, status, created_at
            FROM public.domain_events
            WHERE status = 'pending'
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 50
        """)
        events = cur.fetchall()

        if not events:
            conn.commit()
            return {"published": 0}

        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BROKERS,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: str(k).encode("utf-8"),
        )

        published_count = 0
        for event in events:
            try:
                message = {
                    "event_id": str(event["event_id"]),
                    "merchant_id": event["merchant_id"],
                    "schema_name": event["schema_name"],
                    "event_type": event["event_type"],
                    "entity_type": event["entity_type"],
                    "entity_id": event["entity_id"],
                    "payload": event["payload"] if isinstance(event["payload"], dict) else json.loads(event["payload"]),
                    "created_at": str(event["created_at"]),
                }

                producer.send(
                    topic=settings.KAFKA_TOPIC,
                    key=event["merchant_id"],
                    value=message,
                )
            except Exception as e:
                logger.error(f"Failed to submit event {event['event_id']} to producer: {e}")
        
        # Flush all messages together
        producer.flush()

        # Update all statuses and timestamps in one go (using explicit UTC from app)
        ids = [str(e["event_id"]) for e in events]
        now = datetime.now(timezone.utc)
        cur.execute(
            "UPDATE public.domain_events SET status = 'published', updated_at = %s WHERE event_id = ANY(%s::uuid[])",
            (now, ids)
        )
        conn.commit()
        published_count = len(ids)
        logger.info(f"Published {published_count} events")

        return {"published": published_count}

    except Exception as e:
        logger.error(f"Outbox worker error: {e}")
        if conn:
            conn.rollback()
        raise self.retry(exc=e, countdown=5)

    finally:
        if producer:
            producer.close()
        if conn:
            conn.close()
