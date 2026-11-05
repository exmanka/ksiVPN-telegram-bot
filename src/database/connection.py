"""asyncpg connection pool and the dedicated LISTEN connection.

Domain modules (``*_db.py``) reach the pool only through :func:`acquire`.
Never ``from src.database.connection import _pool``: that would bind the name
at import time, before :func:`asyncpg_run` has created the pool.
"""
import logging

import asyncpg

from src.config import settings


logger = logging.getLogger(__name__)
_pool: asyncpg.Pool | None = None


async def asyncpg_run() -> None:
    """Initialize asyncpg connection."""
    global _pool
    _pool = await asyncpg.create_pool(
        host=settings.connections.postgres.host,
        database=settings.connections.postgres.db,
        user=settings.connections.postgres.user,
        password=settings.connections.postgres.password.get_secret_value(),
        min_size=1,
        max_size=10,
    )

    if _pool:
        logger.info('Database has been successfully connected!')


async def asyncpg_close() -> None:
    """Close asyncpg connection."""
    if _pool is not None:
        await _pool.close()
    logger.info('Database has been successfully disconnected!')


def acquire():
    """Return the pool's acquire context: ``async with acquire() as conn: ...``."""
    if _pool is None:
        raise RuntimeError('Database pool is not initialized: call asyncpg_run() first')
    return _pool.acquire()


async def create_listener_connection() -> asyncpg.Connection:
    """Open a dedicated connection outside the pool for LISTEN/NOTIFY.

    A listening connection stays checked out for its whole life, so it must not
    come from the pool (it would permanently shrink it).
    """
    return await asyncpg.connect(
        host=settings.connections.postgres.host,
        database=settings.connections.postgres.db,
        user=settings.connections.postgres.user,
        password=settings.connections.postgres.password.get_secret_value(),
    )
