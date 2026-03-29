import asyncpg
import json
from .config import settings

pool = None

async def init_connection(conn):
    await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
    await conn.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')

async def get_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            dsn=settings.core_db_dsn,
            min_size=10,
            max_size=50,
            command_timeout=60,
            max_inactive_connection_lifetime=300,
            setup=init_connection
        )
    return pool


async def close_pool():
    global pool
    if pool:
        await pool.close()
        pool = None
