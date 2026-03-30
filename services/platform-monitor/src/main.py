"""
main.py — FastAPI app for the Platform Monitor.
- Runs health checks every 60 seconds via APScheduler.
- Serves a live dashboard at GET /
- Exposes JSON at GET /api/status and GET /api/history
- Manual Start/Stop toggle support.
"""

import asyncio
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

import json
import redis.asyncio as aioredis
from .checker import run_all_checks, run_e2e_smoke, REDIS_URL

# ── State (in-memory) ─────────────────────────────────────────────────────────
_lock = asyncio.Lock()
_is_running = True  # Manual start/stop state
_redis = None       # Set on lifespan
_scheduler = None   # Set on lifespan

_latest: dict = {
    "timestamp": None,
    "overall": "pending",
    "is_running": True,
    "checks_passed": 0,
    "checks_total": 0,
    "layers": {
        "infrastructure": {"status": "pending", "checks": {}},
        "services":       {"status": "pending", "checks": {}},
        "pipeline":       {"status": "pending", "checks": {}},
    },
    "e2e_smoke": {"status": "pending", "last_run": None, "steps": {}},
}

_STATIC = Path(__file__).parent / "static"


# ── Scheduler job ─────────────────────────────────────────────────────────────

async def _job_health():
    global _is_running, _redis
    if not _is_running:
        return

    result = await run_all_checks()
    async with _lock:
        _latest.update(result)
        _latest["is_running"] = _is_running

    # Persist in Redis
    if _redis:
        try:
            full_json = json.dumps(_latest)
            await _redis.lpush("monitor:history", full_json)
            await _redis.ltrim("monitor:history", 0, 49) # Keep 50
        except Exception as e:
            print(f"Redis History Error: {e}")


async def _job_e2e():
    global _is_running
    if not _is_running:
        return
    result = await run_e2e_smoke()
    async with _lock:
        _latest["e2e_smoke"] = result


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _scheduler
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    
    # Run first checks immediately on startup
    await _job_health()
    asyncio.create_task(_job_e2e())

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_job_health, "interval", minutes=5, id="health")
    _scheduler.add_job(_job_e2e,   "interval", hours=1,   id="e2e")
    _scheduler.start()

    yield

    _scheduler.shutdown(wait=False)
    await _redis.aclose()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Platform Monitor",
    description="Automated health & pipeline monitor for the Multi-Tenant Payment Gateway",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(_STATIC / "index.html")


@app.get("/api/status")
async def get_status():
    async with _lock:
        _latest["is_running"] = _is_running
        # Compute seconds until next E2E run
        e2e_next_secs = None
        if _scheduler and _is_running:
            job = _scheduler.get_job("e2e")
            if job and job.next_run_time:
                delta = job.next_run_time - datetime.now(timezone.utc)
                e2e_next_secs = max(0, int(delta.total_seconds()))
        _latest["e2e_next_run_seconds"] = e2e_next_secs
        return JSONResponse(_latest)


@app.post("/api/toggle")
async def toggle_monitoring():
    global _is_running
    async with _lock:
        _is_running = not _is_running
        _latest["is_running"] = _is_running
        
        # If we re-start, trigger a check immediately
        if _is_running:
            asyncio.create_task(_job_health())
            asyncio.create_task(_job_e2e())
            
        return {"is_running": _is_running}


@app.post("/api/e2e/run")
async def manual_e2e_run():
    # Allow manual trigger regardless of global _is_running toggle
    # But only one at a time via job_e2e lock (simplified here)
    asyncio.create_task(_job_e2e())
    return {"status": "triggered"}


@app.get("/api/history")
async def get_history():
    if not _redis:
        return JSONResponse([])
    
    try:
        # Get last 50 entries
        raw_list = await _redis.lrange("monitor:history", 0, 49)
        history = [json.loads(item) for item in raw_list]
        return JSONResponse(history)
    except Exception as e:
        print(f"History Fetch Error: {e}")
        return JSONResponse([])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "platform-monitor"}
