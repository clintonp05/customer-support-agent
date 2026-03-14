import os
from contextlib import contextmanager
from typing import Optional

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from src.config import settings
from src.observability.logger import get_logger

_db_pool: Optional[pool.ThreadedConnectionPool] = None


def init_db_pool(minconn: int = 1, maxconn: int = 10):
    global _db_pool
    if _db_pool is not None:
        return _db_pool

    database_url = os.getenv("DATABASE_URL", settings.database_url)
    logger = get_logger()
    logger.info("db.init_pool", database_url=database_url, minconn=minconn, maxconn=maxconn)

    _db_pool = pool.ThreadedConnectionPool(minconn, maxconn, dsn=database_url)
    return _db_pool


def get_db_pool():
    if _db_pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_db_pool from startup.")
    return _db_pool


def close_db_pool():
    global _db_pool
    if _db_pool is not None:
        _db_pool.closeall()
        _db_pool = None


@contextmanager
def get_db_connection():
    pool_instance = get_db_pool()
    conn = pool_instance.getconn()
    try:
        yield conn
    finally:
        pool_instance.putconn(conn)


@contextmanager
def get_db_cursor():
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
