"""
Analytics Service — Reads from Core DB Replica.

All aggregation/time-series queries run on the replica — zero load on primary.
"""
import logging
from datetime import datetime, timezone, timedelta

from ..database import get_core_replica_pool

logger = logging.getLogger(__name__)


async def get_system_overview() -> dict:
    """System-wide analytics overview. Reads from Replica."""
    pool = await get_core_replica_pool()
    async with pool.acquire() as conn:
        # Active consumers
        active_consumers = await conn.fetchval(
            "SELECT COUNT(*) FROM public.third_party_consumers WHERE status = 'active'"
        )

        # API calls
        now = datetime.now(timezone.utc)
        api_calls_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM public.api_call_audit_log WHERE called_at > $1",
            now - timedelta(hours=24),
        )
        api_calls_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM public.api_call_audit_log WHERE called_at > $1",
            now - timedelta(days=7),
        )

        # Webhook stats
        wh_delivered_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM public.tp_webhook_events WHERE status = 'delivered' AND created_at > $1",
            now - timedelta(hours=24),
        )
        wh_failed_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM public.tp_webhook_events WHERE status IN ('failed', 'dlq') AND created_at > $1",
            now - timedelta(hours=24),
        )
        wh_total_24h = wh_delivered_24h + wh_failed_24h
        wh_success_rate = round((wh_delivered_24h / wh_total_24h * 100), 2) if wh_total_24h > 0 else 100.0

        # DLQ backlog
        dlq_count = await conn.fetchval("SELECT COUNT(*) FROM public.tp_dead_letter_queue")

        # Top consumers by API calls (24h)
        top_consumers_rows = await conn.fetch(
            """
            SELECT a.consumer_id, c.name, COUNT(*) AS call_count
            FROM public.api_call_audit_log a
            JOIN public.third_party_consumers c ON c.consumer_id = a.consumer_id
            WHERE a.called_at > $1
            GROUP BY a.consumer_id, c.name
            ORDER BY call_count DESC
            LIMIT 5
            """,
            now - timedelta(hours=24),
        )

    return {
        "active_consumers": active_consumers,
        "api_calls": {"last_24h": api_calls_24h, "last_7d": api_calls_7d},
        "webhooks": {
            "delivered_24h": wh_delivered_24h,
            "failed_24h": wh_failed_24h,
            "success_rate": wh_success_rate,
        },
        "dlq_backlog": dlq_count,
        "top_consumers": [
            {"consumer_id": str(r["consumer_id"]), "name": r["name"], "call_count": r["call_count"]}
            for r in top_consumers_rows
        ],
    }


async def get_consumer_stats(consumer_id: str) -> dict:
    """Detailed analytics for a specific consumer. Reads from Replica."""
    pool = await get_core_replica_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        # API calls
        api_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM public.api_call_audit_log WHERE consumer_id = $1 AND called_at > $2",
            consumer_id, now - timedelta(hours=24),
        )
        api_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM public.api_call_audit_log WHERE consumer_id = $1 AND called_at > $2",
            consumer_id, now - timedelta(days=7),
        )

        # Response time percentiles
        response_times = await conn.fetchrow(
            """
            SELECT
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY response_time_ms) AS p50,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) AS p95,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY response_time_ms) AS p99,
                AVG(response_time_ms) AS avg_ms
            FROM public.api_call_audit_log
            WHERE consumer_id = $1 AND called_at > $2
            """,
            consumer_id, now - timedelta(days=7),
        )

        # Webhook stats
        wh_delivered = await conn.fetchval(
            "SELECT COUNT(*) FROM public.tp_webhook_events WHERE consumer_id = $1 AND status = 'delivered' AND created_at > $2",
            consumer_id, now - timedelta(days=7),
        )
        wh_failed = await conn.fetchval(
            "SELECT COUNT(*) FROM public.tp_webhook_events WHERE consumer_id = $1 AND status IN ('failed', 'dlq') AND created_at > $2",
            consumer_id, now - timedelta(days=7),
        )

        # Top endpoints
        top_endpoints = await conn.fetch(
            """
            SELECT endpoint, COUNT(*) AS call_count
            FROM public.api_call_audit_log
            WHERE consumer_id = $1 AND called_at > $2
            GROUP BY endpoint
            ORDER BY call_count DESC
            LIMIT 5
            """,
            consumer_id, now - timedelta(days=7),
        )

        # DLQ count
        dlq_count = await conn.fetchval(
            "SELECT COUNT(*) FROM public.tp_dead_letter_queue WHERE consumer_id = $1",
            consumer_id,
        )

    wh_total = wh_delivered + wh_failed
    return {
        "api_calls": {"last_24h": api_24h, "last_7d": api_7d},
        "response_time_ms": {
            "p50": round(response_times["p50"] or 0, 1),
            "p95": round(response_times["p95"] or 0, 1),
            "p99": round(response_times["p99"] or 0, 1),
            "avg": round(response_times["avg_ms"] or 0, 1),
        },
        "webhooks": {
            "delivered_7d": wh_delivered,
            "failed_7d": wh_failed,
            "success_rate": round((wh_delivered / wh_total * 100), 2) if wh_total > 0 else 100.0,
        },
        "dlq_count": dlq_count,
        "top_endpoints": [{"endpoint": r["endpoint"], "call_count": r["call_count"]} for r in top_endpoints],
    }


async def get_time_series_api_calls(
    consumer_id: str,
    from_dt: datetime,
    to_dt: datetime,
    granularity: str = "hour",
) -> list[dict]:
    """Time-series API call data. Reads from Replica."""
    pool = await get_core_replica_pool()

    valid_granularities = {"hour", "day", "week"}
    if granularity not in valid_granularities:
        granularity = "hour"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT date_trunc($1, called_at) AS bucket,
                   COUNT(*) AS call_count,
                   AVG(response_time_ms) AS avg_response_ms,
                   COUNT(*) FILTER (WHERE status_code >= 400) AS error_count
            FROM public.api_call_audit_log
            WHERE consumer_id = $2 AND called_at BETWEEN $3 AND $4
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            granularity, consumer_id, from_dt, to_dt,
        )

    return [
        {
            "timestamp": r["bucket"].isoformat(),
            "call_count": r["call_count"],
            "avg_response_ms": round(r["avg_response_ms"] or 0, 1),
            "error_count": r["error_count"],
        }
        for r in rows
    ]


async def get_time_series_webhooks(
    consumer_id: str,
    from_dt: datetime,
    to_dt: datetime,
    granularity: str = "hour",
) -> list[dict]:
    """Time-series webhook delivery data. Reads from Replica."""
    pool = await get_core_replica_pool()

    valid_granularities = {"hour", "day", "week"}
    if granularity not in valid_granularities:
        granularity = "hour"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT date_trunc($1, created_at) AS bucket,
                   COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                   COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                   COUNT(*) FILTER (WHERE status = 'dlq') AS dlq
            FROM public.tp_webhook_events
            WHERE consumer_id = $2 AND created_at BETWEEN $3 AND $4
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            granularity, consumer_id, from_dt, to_dt,
        )

    return [
        {
            "timestamp": r["bucket"].isoformat(),
            "delivered": r["delivered"],
            "failed": r["failed"],
            "dlq": r["dlq"],
        }
        for r in rows
    ]
