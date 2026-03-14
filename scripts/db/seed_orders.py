import random
from datetime import datetime, timedelta
from scripts.db.connection import get_db_connection


def seed_orders(count: int = 50):
    statuses = ["pending", "confirmed", "shipped", "out_for_delivery", "delivered", "cancelled", "returned"]
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM customers")
            users = [row[0] for row in cur.fetchall()]
            if not users:
                raise RuntimeError("No users found to seed orders")

            for i in range(1, count + 1):
                order_id = f"N-{datetime.now().strftime('%Y%m%d')}-{i:05d}"
                user_id = random.choice(users)
                status = random.choice(statuses)
                placed_at = datetime.now() - timedelta(days=random.randint(1, 60))
                item_count = random.randint(1, 5)
                total_aed = round(random.uniform(100, 1500), 2)
                cur.execute(
                    "INSERT INTO orders (order_id, user_id, status, total_aed, item_count, placed_at, shipping_address) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (order_id) DO NOTHING",
                    (
                        order_id,
                        user_id,
                        status,
                        total_aed,
                        item_count,
                        placed_at,
                        '{"city": "Dubai", "area": "Marina", "street": "123 Street", "building": "A1"}',
                    ),
                )
        conn.commit()


if __name__ == "__main__":
    seed_orders()