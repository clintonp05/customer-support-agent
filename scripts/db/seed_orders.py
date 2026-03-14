import random
import string
from datetime import datetime, timedelta
from scripts.db.connection import get_db_connection

ARABIC_STATUS_MAP = {
    "pending":          "قيد الانتظار",
    "confirmed":        "تم التأكيد",
    "shipped":          "تم الشحن",
    "out_for_delivery": "قيد التوصيل",
    "delivered":        "تم التسليم",
    "cancelled":        "ملغى",
    "returned":         "تم الإرجاع"
}

UAE_AREAS = {
    "Dubai":        ["Downtown", "Marina", "JBR", "Deira", "Bur Dubai", "JLT", "Silicon Oasis"],
    "Abu Dhabi":    ["Corniche", "Khalidiyah", "Mussafah", "Al Reem"],
    "Sharjah":      ["Al Majaz", "Al Nahda", "Al Qasimiyah"],
    "Ajman":        ["Al Nuaimia", "Al Rashidiya"],
    "RAK":          ["Al Nakheel", "Al Qawasem"]
}

# Weighted status distribution — matches spec
STATUS_WEIGHTS = [
    ("delivered",        0.30),
    ("shipped",          0.20),
    ("confirmed",        0.15),
    ("pending",          0.10),
    ("out_for_delivery", 0.10),
    ("cancelled",        0.10),
    ("returned",         0.05),
]

def weighted_status():
    statuses = [s for s, _ in STATUS_WEIGHTS]
    weights = [w for _, w in STATUS_WEIGHTS]
    return random.choices(statuses, weights=weights, k=1)[0]


def random_suffix(n=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))


def seed_orders(count: int = 1000):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, city FROM customers")
            users = cur.fetchall()
            if not users:
                raise RuntimeError("No customers found — run seed_customers first")

            inserted = 0
            attempts = 0

            while inserted < count and attempts < count * 3:
                attempts += 1
                date_str = datetime.now().strftime('%Y%m%d')
                order_id = f"N-{date_str}-{random_suffix()}"

                user_id, city = random.choice(users)
                status = weighted_status()
                placed_at = datetime.now() - timedelta(days=random.randint(1, 90))
                item_count = random.randint(1, 5)
                total_aed = round(random.uniform(100, 5000), 2)

                areas = UAE_AREAS.get(city, ["Central"])
                area = random.choice(areas)
                address = {
                    "city": city,
                    "area": area,
                    "street": f"{random.randint(1, 200)} Street",
                    "building": f"Building {random.randint(1, 50)}"
                }

                import json
                cur.execute("""
                    INSERT INTO orders
                        (order_id, user_id, status, total_aed, item_count, placed_at, shipping_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (order_id) DO NOTHING
                """, (order_id, user_id, status, total_aed, item_count, placed_at, json.dumps(address)))

                if cur.rowcount > 0:
                    inserted += 1

            conn.commit()
            print(f"  Orders inserted: {inserted}")


if __name__ == "__main__":
    seed_orders()