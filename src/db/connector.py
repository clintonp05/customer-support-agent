import os
import time
from contextlib import contextmanager
from typing import Optional

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from src.config import settings
from src.observability.logger import get_logger

_db_pool: Optional[pool.ThreadedConnectionPool] = None


def init_db_pool(minconn: int = 1, maxconn: int = 10, retries: int = 3, delay_s: float = 1.0):
    global _db_pool
    if _db_pool is not None:
        return _db_pool

    database_url = os.getenv("DATABASE_URL", settings.database_url)
    logger = get_logger()
    last_err = None
    for attempt in range(1, retries + 1):
        logger.info("db.init_pool_attempt", attempt=attempt, retries=retries, database_url=database_url)
        try:
            _db_pool = pool.ThreadedConnectionPool(minconn, maxconn, dsn=database_url)
            logger.info("db.init_pool_success", database_url=database_url)
            return _db_pool
        except Exception as exc:
            last_err = exc
            logger.warning("db.init_pool_failed", attempt=attempt, exc=str(exc))
            if attempt < retries:
                time.sleep(delay_s)

    logger.error("db.init_pool_failed_all_attempts", retries=retries, exc=str(last_err))
    raise last_err


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
