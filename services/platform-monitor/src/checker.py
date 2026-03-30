"""
checker.py — All health & pipeline check logic for the Platform Monitor.
Runs inside the Docker network, so uses internal hostnames.
"""

import asyncio
import time
from datetime import datetime, timezone

import asyncpg
import httpx
import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer

# ── Internal Docker hostnames ─────────────────────────────────────────────────
CORE_DB_DSN   = "postgresql://payment_admin:payment_secret@core-db:5432/payment_core"
READ_DB_DSN   = "postgresql://payment_admin:payment_secret@read-db:5432/payment_read"
REDIS_URL     = "redis://redis:6379/0"
KAFKA_BROKERS = "redpanda:9092"
KAFKA_TOPIC   = "payments.events"
CORE_URL      = "http://payment-core-service:8001"
CONNECT_URL   = "http://connect-service:8002"
DASHBOARD_URL = "http://merchant-dashboard-service:8003"

DB_TIMEOUT    = 5.0
HTTP_TIMEOUT  = 10.0


def _ms(start: float) -> int:
    return round((time.time() - start) * 1000)


def _ok(**kw) -> dict:
    return {"status": "ok", **kw}


def _err(exc) -> dict:
    return {"status": "error", "error": str(exc)[:250]}


# ── Layer 1: Infrastructure ───────────────────────────────────────────────────

async def _chk_postgres(dsn: str) -> dict:
    start = time.time()
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=DB_TIMEOUT)
        await conn.execute("SELECT 1")
        await conn.close()
        return _ok(latency_ms=_ms(start))
    except Exception as e:
        return _err(e)


async def _chk_redis() -> dict:
    start = time.time()
    try:
        r = aioredis.from_url(REDIS_URL, socket_connect_timeout=5)
        pong = await asyncio.wait_for(r.ping(), timeout=5.0)
        await r.aclose()
        return _ok(latency_ms=_ms(start), pong=bool(pong))
    except Exception as e:
        return _err(e)


async def _chk_kafka() -> dict:
    start = time.time()
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BROKERS)
    try:
        await asyncio.wait_for(producer.start(), timeout=8.0)
        try:
            await asyncio.wait_for(producer.partitions_for(KAFKA_TOPIC), timeout=5.0)
            topic_exists = True
        except Exception:
            topic_exists = False
        return _ok(latency_ms=_ms(start), topic_exists=topic_exists, topic=KAFKA_TOPIC)
    except Exception as e:
        return _err(e)
    finally:
        try:
            await asyncio.wait_for(producer.stop(), timeout=5.0)
        except Exception:
            pass


async def check_infrastructure() -> dict:
    results = await asyncio.gather(
        _chk_postgres(CORE_DB_DSN),
        _chk_postgres(READ_DB_DSN),
        _chk_redis(),
        _chk_kafka(),
        return_exceptions=True,
    )
    keys = ["core_db", "read_db", "redis", "kafka"]
    checks = {k: (_err(r) if isinstance(r, Exception) else r) for k, r in zip(keys, results)}
    all_ok = all(c["status"] == "ok" for c in checks.values())
    return {"status": "healthy" if all_ok else "unhealthy", "checks": checks}


# ── Layer 2: Service Health ───────────────────────────────────────────────────

async def _chk_service(url: str, client: httpx.AsyncClient) -> dict:
    start = time.time()
    try:
        resp = await client.get(f"{url}/health", timeout=HTTP_TIMEOUT)
        data = resp.json()
        ok = resp.status_code == 200 and data.get("status") == "healthy"
        return {
            "status": "ok" if ok else "error",
            "latency_ms": _ms(start),
            "http_status": resp.status_code,
            "components": data.get("components", {}),
        }
    except Exception as e:
        return {**_err(e), "latency_ms": _ms(start)}


async def check_services() -> dict:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            _chk_service(CORE_URL, client),
            _chk_service(CONNECT_URL, client),
            _chk_service(DASHBOARD_URL, client),
            return_exceptions=True,
        )
    keys = ["payment_core", "connect_service", "merchant_dashboard"]
    checks = {k: (_err(r) if isinstance(r, Exception) else r) for k, r in zip(keys, results)}
    all_ok = all(c["status"] == "ok" for c in checks.values())
    return {"status": "healthy" if all_ok else "unhealthy", "checks": checks}


# ── Layer 3: Pipeline Health ──────────────────────────────────────────────────

async def check_pipeline() -> dict:
    checks = {}

    try:
        conn = await asyncio.wait_for(asyncpg.connect(CORE_DB_DSN), timeout=DB_TIMEOUT)
        try:
            pending = int(await conn.fetchval(
                "SELECT COUNT(*) FROM public.domain_events WHERE status = 'pending'"
            ))
            checks["pending_events"] = {
                "status": "warning" if pending > 20 else "ok",
                "count": pending,
            }
            oldest = await conn.fetchval(
                "SELECT EXTRACT(EPOCH FROM (NOW() - created_at))::int "
                "FROM public.domain_events WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
            )
            age = int(oldest) if oldest is not None else None
            checks["event_lag"] = {
                "status": "warning" if age and age > 300 else "ok",
                "oldest_pending_age_seconds": age,
            }
        finally:
            await conn.close()
    except Exception as e:
        checks["pending_events"] = _err(e)
        checks["event_lag"] = _err(e)

    try:
        conn = await asyncio.wait_for(asyncpg.connect(READ_DB_DSN), timeout=DB_TIMEOUT)
        try:
            count = int(await conn.fetchval("SELECT COUNT(*) FROM public.merchants"))
            checks["read_db_mirror"] = {"status": "ok", "merchant_count": count}
        finally:
            await conn.close()
    except Exception as e:
        checks["read_db_mirror"] = _err(e)

    statuses = {c["status"] for c in checks.values()}
    if "error" in statuses:
        overall = "unhealthy"
    elif "warning" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return {"status": overall, "checks": checks}


# ── Layer 4: E2E Smoke Test ───────────────────────────────────────────────────

async def run_e2e_smoke() -> dict:
    start = time.time()
    steps: dict = {}
    merchant_id = None
    schema_name = None

    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            # 1. Create merchant
            suffix = int(time.time())
            r = await http.post(f"{CORE_URL}/api/merchants", json={
                "name": f"[Monitor] Smoke {suffix}",
                "email": f"monitor-{suffix}@platform-check.internal",
            })
            if r.status_code != 201:
                steps["create_merchant"] = {"status": "error", "http": r.status_code}
                return _build_e2e(steps, start, merchant_id, schema_name)

            m = r.json()
            merchant_id = m["merchant_id"]
            schema_name = m["schema_name"]
            hdrs = {"X-API-Key": str(m["api_key"])}
            steps["create_merchant"] = _ok(merchant_id=merchant_id)

            # 2. Create customer
            r = await http.post(
                f"{CORE_URL}/api/{merchant_id}/customers",
                json={"name": "Smoke Customer", "email": "s@m.internal"},
                headers=hdrs,
            )
            if r.status_code != 201:
                steps["create_customer"] = {"status": "error", "http": r.status_code}
                return _build_e2e(steps, start, merchant_id, schema_name)
            customer_id = r.json()["customer_id"]
            steps["create_customer"] = _ok()

            # 3. Create payment
            r = await http.post(
                f"{CORE_URL}/api/{merchant_id}/payments",
                json={"customer_id": customer_id, "amount": 1.00,
                      "currency": "INR", "method": "upi",
                      "description": "Smoke Test"},
                headers=hdrs,
            )
            if r.status_code != 201:
                steps["create_payment"] = {"status": "error", "http": r.status_code}
                return _build_e2e(steps, start, merchant_id, schema_name)
            payment_id = r.json()["payment_id"]
            steps["create_payment"] = _ok()

            # 4. Authorize → Capture
            auth = await http.post(
                f"{CORE_URL}/api/{merchant_id}/payments/{payment_id}/authorize", headers=hdrs)
            cap = await http.post(
                f"{CORE_URL}/api/{merchant_id}/payments/{payment_id}/capture", headers=hdrs)
            steps["payment_lifecycle"] = {
                "status": "ok" if auth.status_code == 200 and cap.status_code == 200 else "error"
            }

            # 5. Verify event published (poll 10s)
            steps["event_published"] = await _poll_event(merchant_id)

            # 6. Verify Read-DB synced (poll 10s)
            steps["read_db_synced"] = await _poll_read_db_sync(merchant_id)

    except Exception as e:
        steps["exception"] = _err(e)

    return _build_e2e(steps, start, merchant_id, schema_name)


async def _poll_read_db_sync(merchant_id: int) -> dict:
    try:
        conn = await asyncio.wait_for(asyncpg.connect(READ_DB_DSN), timeout=5.0)
        try:
            for _ in range(15):
                count = int(await conn.fetchval(
                    "SELECT COUNT(*) FROM public.merchants WHERE merchant_id=$1", merchant_id
                ))
                if count > 0:
                    return _ok(synced=True)
                await asyncio.sleep(1)
            return {"status": "warning", "synced": False, "note": "Sync not reached Read-DB within 15s"}
        finally:
            await conn.close()
    except Exception as e:
        return _err(e)


async def _poll_event(merchant_id: int) -> dict:
    try:
        conn = await asyncio.wait_for(asyncpg.connect(CORE_DB_DSN), timeout=5.0)
        try:
            # Poll for 24s (12 * 2s) to match the outbox-poll schedule
            for _ in range(12):
                count = int(await conn.fetchval(
                    "SELECT COUNT(*) FROM public.domain_events "
                    "WHERE merchant_id=$1 AND status='published'", merchant_id
                ))
                if count > 0:
                    return _ok(published=True)
                await asyncio.sleep(2)
            return {"status": "warning", "published": False, "note": "Event not marked 'published' in outbox within 24s"}
        finally:
            await conn.close()
    except Exception as e:
        return _err(e)


async def _cleanup_smoke(merchant_id, schema_name) -> dict:
    if not merchant_id or not schema_name:
        return {"status": "skipped"}
    errors = []
    
    # DB configuration for cleanup
    # Core DB has public.domain_events, Read DB does not.
    configs = [
        {"name": "Core DB", "dsn": CORE_DB_DSN, "tables": ["public.domain_events", "public.merchants"]},
        {"name": "Read DB", "dsn": READ_DB_DSN, "tables": ["public.merchants"]}
    ]

    for cfg in configs:
        try:
            conn = await asyncio.wait_for(asyncpg.connect(cfg["dsn"]), timeout=5.0)
            try:
                # 1. Drop Schema (CASCADE handles most per-merchant data)
                try:
                    await conn.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
                except Exception as e:
                    errors.append(f"[{cfg['name']}] Schema drop: {str(e)}")

                # 2. Drop merchant-related records in public tables
                for table in cfg["tables"]:
                    try:
                        await conn.execute(f"DELETE FROM {table} WHERE merchant_id=$1;", merchant_id)
                    except Exception as e:
                        errors.append(f"[{cfg['name']}] Delete {table}: {str(e)}")

            finally:
                await conn.close()
        except Exception as e:
            errors.append(f"[{cfg['name']}] Connection: {str(e)}")

    return {"status": "ok" if not errors else "warning", "errors": errors}


def _build_e2e(steps: dict, start: float, merchant_id, schema_name) -> dict:
    # Run cleanup as a fire-and-forget coroutine wrapper with a small delay
    # to allow the connect-service to finish and sync before we wipe it.
    async def _do():
        await asyncio.sleep(3)
        steps["cleanup"] = await _cleanup_smoke(merchant_id, schema_name)
    asyncio.create_task(_do())

    has_error = any(v.get("status") == "error" for v in steps.values())
    return {
        "status": "error" if has_error else "ok",
        "duration_ms": _ms(start),
        "last_run": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
    }


# ── Master runner ─────────────────────────────────────────────────────────────

async def run_all_checks() -> dict:
    infra, services, pipeline = await asyncio.gather(
        check_infrastructure(),
        check_services(),
        check_pipeline(),
        return_exceptions=True,
    )

    def _safe(r):
        if isinstance(r, Exception):
            return {"status": "unhealthy", "error": str(r), "checks": {}}
        return r

    infra = _safe(infra)
    services = _safe(services)
    pipeline = _safe(pipeline)

    all_checks = {}
    all_checks.update(infra.get("checks", {}))
    all_checks.update(services.get("checks", {}))
    all_checks.update(pipeline.get("checks", {}))

    passed = sum(1 for c in all_checks.values() if c.get("status") == "ok")
    total = len(all_checks)

    layer_statuses = {infra["status"], services["status"], pipeline["status"]}
    if "unhealthy" in layer_statuses:
        overall = "unhealthy"
    elif "degraded" in layer_statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "checks_passed": passed,
        "checks_total": total,
        "layers": {
            "infrastructure": infra,
            "services": services,
            "pipeline": pipeline,
        },
    }
