import random
from scripts.db.connection import get_db_connection


def seed_payments():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, user_id FROM orders")
            rows = cur.fetchall()
            for i, (order_id, user_id) in enumerate(rows, start=1):
                payment_id = f"PAY-{i:05d}"
                amount = round(random.uniform(80, 1500), 2)
                method = random.choice(["credit_card", "debit_card", "noon_pay", "cod", "wallet"])
                status = random.choice(["success", "failed", "pending"])
                cur.execute(
                    "INSERT INTO payments (payment_id, order_id, user_id, amount_aed, method, status, transaction_ref, paid_at) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW()) ON CONFLICT (payment_id) DO NOTHING",
                    (payment_id, order_id, user_id, amount, method, status, f"TRX-{i:06d}"),
                )
        conn.commit()


if __name__ == "__main__":
    seed_payments()