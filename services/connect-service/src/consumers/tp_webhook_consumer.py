"""
Third-Party Webhook Kafka Consumer.

Consumes from payments.events topic, matches events against active
webhook endpoints, and dispatches HMAC-signed payloads.

Consumer Group: third-party-webhook-delivery-group
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from kafka import KafkaConsumer

from ..config import settings
from ..services.tp_webhook_service import (
    get_active_endpoints_for_event,
    dispatch_webhook,
)

logger = logging.getLogger(__name__)


async def check_merchant_access_for_endpoint(endpoint: dict, merchant_id: int) -> bool:
    """Check if the endpoint's consumer has access to this merchant."""
    from ..services.oauth_service import check_merchant_access
    return await check_merchant_access(str(endpoint["consumer_id"]), merchant_id)


async def _process_event(event_data: dict):
    """Process a single event and dispatch to matching endpoints."""
    event_type = event_data.get("event_type")
    merchant_id = event_data.get("merchant_id")

    if not event_type or not merchant_id:
        logger.warning(f"Skipping event with missing type or merchant_id: {event_data}")
        return

    # Find matching active endpoints
    endpoints = await get_active_endpoints_for_event(event_type, merchant_id)

    for endpoint in endpoints:
        # Verify consumer has access to this merchant
        if endpoint.get("merchant_id") is None:
            has_access = await check_merchant_access_for_endpoint(endpoint, merchant_id)
            if not has_access:
                continue

        try:
            result = await dispatch_webhook(endpoint, event_data)
            logger.info(
                f"Webhook dispatched: endpoint={endpoint['endpoint_id']}, "
                f"event={event_type}, status={result['status']}"
            )
        except Exception as e:
            logger.error(f"Failed to dispatch webhook to {endpoint['url']}: {e}")


def start_tp_webhook_consumer():
    """Start the third-party webhook delivery consumer (blocking)."""
    logger.info("Starting third-party webhook consumer...")

    consumer = KafkaConsumer(
        settings.KAFKA_TOPIC,
        bootstrap_servers=settings.KAFKA_BROKERS,
        group_id="third-party-webhook-delivery-group",
        auto_offset_reset="latest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        enable_auto_commit=True,
        auto_commit_interval_ms=5000,
    )

    logger.info(f"Third-party webhook consumer connected, listening on: {settings.KAFKA_TOPIC}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        for message in consumer:
            try:
                event_data = message.value
                logger.debug(f"TP webhook consumer received: {event_data.get('event_type')}")
                loop.run_until_complete(_process_event(event_data))
            except Exception as e:
                logger.error(f"Error processing event for TP webhook delivery: {e}")
    except KeyboardInterrupt:
        logger.info("Third-party webhook consumer shutting down")
    finally:
        consumer.close()
        loop.close()
