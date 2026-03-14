import random
from datetime import datetime, timedelta
from scripts.db.connection import get_db_connection


def seed_warranties():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT oi.order_id, o.user_id, oi.product_id FROM order_items oi JOIN orders o ON oi.order_id = o.order_id LIMIT 20")
            rows = cur.fetchall()
            for i, (order_id, user_id, product_id) in enumerate(rows, start=1):
                warranty_id = f"WRN-{i:05d}"
                start_date = datetime.now().date() - timedelta(days=random.randint(0, 365))
                end_date = start_date + timedelta(days=365)
                status = random.choice(["active", "expired", "claimed", "void"])
                cur.execute(
                    "INSERT INTO warranties (warranty_id, order_id, user_id, product_id, warranty_type, start_date, end_date, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (warranty_id) DO NOTHING",
                    (warranty_id, order_id, user_id, product_id, random.choice(["manufacturer", "extended", "noon_protect"]), start_date, end_date, status),
                )
        conn.commit()


if __name__ == "__main__":
    seed_warranties()