import random
from datetime import datetime
from scripts.db.connection import get_db_connection

REFUND_REASONS = [
    "Item not as described",
    "Wrong item delivered",
    "Item arrived damaged",
    "Item stopped working",
    "Changed my mind",
    "Duplicate order",
    "Never arrived"
]

REJECTION_REASONS = [
    "Order older than 30 days - outside return window",
    "Product category is non-returnable",
    "Refund already processed for this order",
    "Item shows signs of use",
    "Original packaging missing"
]

REFUND_METHODS = ["original_payment", "wallet", "bank_transfer"]

# order_age_days distribution — critical for eligibility testing
# < 7 days   40% → clearly eligible
# 7-30 days  30% → eligible
# 31-60 days 20% → ineligible
# > 60 days  10% → ineligible
AGE_DISTRIBUTION = [
    (1,   6,   0.40),
    (7,   30,  0.30),
    (31,  60,  0.20),
    (61,  120, 0.10),
]

def pick_order_age():
    ranges = [(lo, hi) for lo, hi, _ in AGE_DISTRIBUTION]
    weights = [w for _, _, w in AGE_DISTRIBUTION]
    lo, hi = random.choices(ranges, weights=weights, k=1)[0]
    return random.randint(lo, hi)

def seed_refunds(count: int = 200):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Only refund eligible orders
            cur.execute("""
                SELECT order_id, user_id, total_aed
                FROM orders
                WHERE status IN ('delivered', 'returned', 'cancelled')
            """)
            eligible_orders = cur.fetchall()

            if not eligible_orders:
                raise RuntimeError("No delivered/returned/cancelled orders found")

            if len(eligible_orders) < count:
                print(f"  Warning: only {len(eligible_orders)} eligible orders, creating {len(eligible_orders)} refunds")
                count = len(eligible_orders)

            selected = random.sample(eligible_orders, count)
            inserted = 0

            for i, (order_id, user_id, total_aed) in enumerate(selected, start=1):
                refund_id = f"REF-{i:05d}"
                order_age_days = pick_order_age()
                amount = round(random.uniform(20, float(total_aed)), 2)

                # Rejected refunds MUST have age > 30 days
                if order_age_days > 30:
                    status = random.choices(
                        ["rejected", "processed", "pending"],
                        weights=[0.50, 0.30, 0.20]
                    )[0]
                else:
                    status = random.choices(
                        ["processed", "pending"],
                        weights=[0.74, 0.26]
                    )[0]

                rejection_reason = None
                processed_at = None

                if status == "rejected":
                    rejection_reason = random.choice(REJECTION_REASONS)
                elif status == "processed":
                    processed_at = datetime.now()

                cur.execute("""
                    INSERT INTO refunds
                        (refund_id, order_id, user_id, amount_aed, reason,
                         status, rejection_reason, order_age_days,
                         refund_method, processed_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (refund_id) DO NOTHING
                """, (
                    refund_id, order_id, user_id, amount,
                    random.choice(REFUND_REASONS),
                    status, rejection_reason, order_age_days,
                    random.choice(REFUND_METHODS), processed_at
                ))

                if cur.rowcount > 0:
                    inserted += 1

            conn.commit()
            print(f"  Refunds inserted: {inserted}")

if __name__ == "__main__":
    seed_refunds()