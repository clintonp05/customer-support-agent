import random
from scripts.db.connection import get_db_connection


def seed_refunds():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, user_id FROM orders LIMIT 20")
            rows = cur.fetchall()
            for i, (order_id, user_id) in enumerate(rows, start=1):
                refund_id = f"REF-{i:05d}"
                amount = round(random.uniform(20, 500), 2)
                status = random.choice(["processed", "pending", "rejected"])
                rejection_reason = None
                if status == "rejected":
                    rejection_reason = random.choice(["Order older than 30 days", "Product is non-returnable", "Refund already processed"])
                cur.execute(
                    "INSERT INTO refunds (refund_id, order_id, user_id, amount_aed, reason, status, rejection_reason, order_age_days, refund_method) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (refund_id) DO NOTHING",
                    (refund_id, order_id, user_id, amount, "Defective product", status, rejection_reason, random.randint(1, 90), random.choice(["original_payment", "wallet", "bank_transfer"])),
                )
        conn.commit()


if __name__ == "__main__":
    seed_refunds()