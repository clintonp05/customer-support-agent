import os
import psycopg2
from psycopg2.extras import execute_values


def get_db_connection():
    database_url = os.getenv("DATABASE_URL", "postgresql://noon:noon_local@localhost:5432/noon_agent")
    return psycopg2.connect(database_url)


def run_sql(script_path: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            with open(script_path, "r", encoding="utf-8") as f:
                sql = f.read()
            cur.execute(sql)
        conn.commit()
