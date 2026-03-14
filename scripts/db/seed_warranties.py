import random
from datetime import datetime, timedelta
from scripts.db.connection import get_db_connection

WARRANTY_CATEGORIES = [
    "Electronics",
    "Mobile_Phones",
    "Laptops_Computers",
    "Home_Appliances"
]

WARRANTY_TYPES = ["manufacturer", "extended", "noon_protect"]

WARRANTY_STATUS_WEIGHTS = [
    ("active",   0.50),
    ("expired",  0.30),
    ("claimed",  0.15),
    ("void",     0.05),
]

def weighted_warranty_status():
    statuses = [s for s, _ in WARRANTY_STATUS_WEIGHTS]
    weights = [w for _, w in WARRANTY_STATUS_WEIGHTS]
    return random.choices(statuses, weights=weights, k=1)[0]


def seed_warranties(count: int = 300):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT oi.order_id, o.user_id, oi.product_id, p.warranty_months, p.category
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.order_id
                JOIN products p ON oi.product_id = p.product_id
                WHERE o.status = 'delivered'
                  AND p.warranty_months > 0
                  AND p.category IN %s
            """, (tuple(WARRANTY_CATEGORIES),))

            eligible = cur.fetchall()
            if not eligible:
                print("  Warning: no warranty-eligible items found")
                return

            if len(eligible) < count:
                count = len(eligible)

            selected = random.sample(eligible, count)
            inserted = 0

            for i, (order_id, user_id, product_id, warranty_months, category) in enumerate(selected, start=1):
                warranty_id = f"WRN-{i:05d}"
                start_date = datetime.now().date() - timedelta(days=random.randint(0, 365))
                end_date = start_date + timedelta(days=warranty_months * 30)

                if end_date > datetime.now().date():
                    status = random.choices(["active", "claimed"], weights=[0.85, 0.15], k=1)[0]
                else:
                    status = random.choices(["expired", "claimed", "void"], weights=[0.70, 0.20, 0.10], k=1)[0]

                claim_count = 1 if status == "claimed" else 0
                last_claim_at = datetime.now() if claim_count > 0 else None

                cur.execute("""
                    INSERT INTO warranties
                        (warranty_id, order_id, user_id, product_id,
                         warranty_type, start_date, end_date,
                         status, claim_count, last_claim_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (warranty_id) DO NOTHING
                """, (
                    warranty_id,
                    order_id,
                    user_id,
                    product_id,
                    random.choice(WARRANTY_TYPES),
                    start_date,
                    end_date,
                    status,
                    claim_count,
                    last_claim_at,
                ))

                if cur.rowcount > 0:
                    inserted += 1

            conn.commit()
            print(f"  Warranties inserted: {inserted}")


if __name__ == "__main__":
    seed_warranties()