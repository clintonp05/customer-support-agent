import random
from scripts.db.connection import get_db_connection


def seed_deliveries():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, user_id FROM orders")
            rows = cur.fetchall()
            for i, (order_id, user_id) in enumerate(rows, start=1):
                delivery_id = f"DEL-{i:05d}"
                status = random.choice(["awaiting_pickup", "in_transit", "out_for_delivery", "delivered", "cancelled"])
                cur.execute(
                    "INSERT INTO deliveries (delivery_id, order_id, user_id, carrier, tracking_number, status, delivery_address) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (delivery_id) DO NOTHING",
                    (delivery_id, order_id, user_id, random.choice(["noon_express", "aramex", "fetchr", "smsa"]), f"TRACK{i:06d}", status, '{"city": "Dubai", "area": "JBR"}'),
                )
        conn.commit()


if __name__ == "__main__":
    seed_deliveries()