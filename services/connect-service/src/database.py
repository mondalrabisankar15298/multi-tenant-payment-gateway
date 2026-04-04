import asyncpg
from .config import settings
import json

# ─── Connection Pools ─────────────────────────────────────
# System 2 connects to THREE databases:
#   1. Read DB       — for DB sync consumer (existing, unchanged)
#   2. Core Primary  — for writes (consumer CRUD, webhooks, audit, OAuth)
#   3. Core Replica  — for read-only queries (Bulk API, Analytics)

_read_db_pool = None
_core_primary_pool = None
_core_replica_pool = None


async def init_connection(conn):
    await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
    await conn.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')


# ─── Read DB Pool (System 3 internal — DB sync consumer) ──

async def get_pool() -> asyncpg.Pool:
    """Read DB pool — used by existing DB sync consumer (unchanged)."""
    global _read_db_pool
    if _read_db_pool is None:
        _read_db_pool = await asyncpg.create_pool(
            dsn=settings.read_db_dsn,
            min_size=5,
            max_size=20,
            command_timeout=60,
            max_inactive_connection_lifetime=300,
            setup=init_connection
        )
    return _read_db_pool


# ─── Core DB Primary Pool (writes) ────────────────────────

async def get_core_primary_pool() -> asyncpg.Pool:
    """Core DB Primary — for writes (consumer management, webhooks, audit logs, OAuth)."""
    global _core_primary_pool
    if _core_primary_pool is None:
        _core_primary_pool = await asyncpg.create_pool(
            dsn=settings.core_db_dsn,
            min_size=3,
            max_size=10,
            command_timeout=30,
            max_inactive_connection_lifetime=300,
            setup=init_connection
        )
    return _core_primary_pool


# ─── Core DB Replica Pool (read-only) ─────────────────────

async def get_core_replica_pool() -> asyncpg.Pool:
    """Core DB Replica — read-only queries (Bulk API, Analytics). Zero load on primary."""
    global _core_replica_pool
    if _core_replica_pool is None:
        _core_replica_pool = await asyncpg.create_pool(
            dsn=settings.core_replica_dsn,
            min_size=5,
            max_size=20,
            command_timeout=60,
            max_inactive_connection_lifetime=300,
            setup=init_connection
        )
    return _core_replica_pool


# ─── Cleanup ──────────────────────────────────────────────

async def close_pool():
    """Close the Read DB pool (backward compatible name)."""
    global _read_db_pool
    if _read_db_pool:
        await _read_db_pool.close()
        _read_db_pool = None


async def close_all_pools():
    """Close all database connection pools on shutdown."""
    global _read_db_pool, _core_primary_pool, _core_replica_pool

    for pool_name, pool in [
        ("Read DB", _read_db_pool),
        ("Core Primary", _core_primary_pool),
        ("Core Replica", _core_replica_pool),
    ]:
        if pool:
            try:
                await pool.close()
            except Exception:
                pass

    _read_db_pool = None
    _core_primary_pool = None
    _core_replica_pool = None
