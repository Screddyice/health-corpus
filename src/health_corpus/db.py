"""psycopg3 connection pool for the health corpus store."""
from __future__ import annotations

import psycopg
from psycopg_pool import ConnectionPool


def init_pool(
    dsn: str,
    *,
    min_size: int = 1,
    max_size: int = 8,
) -> ConnectionPool:
    """Open a pool against ``dsn``. Callers own and must close it."""

    def _configure(conn: psycopg.Connection) -> None:
        conn.autocommit = True
        try:
            conn.execute("SET search_path TO public")
        finally:
            conn.autocommit = False

    return ConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        configure=_configure,
        kwargs={"autocommit": False, "prepare_threshold": None},
        open=True,
    )


def close_pool(pool: ConnectionPool) -> None:
    """Close the connection pool. Idempotent."""
    if not pool.closed:
        pool.close()
