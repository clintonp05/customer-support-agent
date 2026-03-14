# SEED_FIXES.md — Seed Script Corrections
## Claude Code Instructions

Fix all seed scripts in the order listed below.
Do not skip steps. Each step depends on the previous.
After all fixes, run: python scripts/seed_database.py

---

## Step 1 — Fix seed_orders.py

Problems to fix:
- Status is random — must use weighted distribution
- order_id collision risk on same-day runs
- count default is 50 — must default to 1000

```python
# scripts/db/seed_orders.py

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
    weights  = [w for _, w in STATUS_WEIGHTS]
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
```

---

## Step 2 — Fix seed_deliveries.py

Problems to fix:
- Delivery status must align with parent order status
- Add estimated_date field
- Hardcode 30 delayed orders (past estimated date, not delivered)
- Add Arabic status labels

```python
# scripts/db/seed_deliveries.py

import random
import json
from datetime import datetime, timedelta
from scripts.db.connection import get_db_connection

CARRIERS = ["noon_express", "aramex", "fetchr", "smsa"]

CARRIER_PREFIX = {
    "noon_express": "NE",
    "aramex":       "ARM",
    "fetchr":       "FTR",
    "smsa":         "SMS"
}

# Delivery status must match order status exactly
ORDER_TO_DELIVERY_STATUS = {
    "pending":          "awaiting_pickup",
    "confirmed":        "awaiting_pickup",
    "shipped":          "in_transit",
    "out_for_delivery": "out_for_delivery",
    "delivered":        "delivered",
    "cancelled":        "cancelled",
    "returned":         "returned"
}

ARABIC_DELIVERY_STATUS = {
    "awaiting_pickup":   "في انتظار الاستلام",
    "in_transit":        "في الطريق",
    "out_for_delivery":  "قيد التوصيل",
    "delivered":         "تم التسليم",
    "cancelled":         "ملغى",
    "returned":          "تم الإرجاع"
}

def seed_deliveries():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, user_id, status, placed_at, shipping_address FROM orders")
            orders = cur.fetchall()

            delayed_count = 0
            MAX_DELAYED = 30

            for i, (order_id, user_id, order_status, placed_at, shipping_address) in enumerate(orders, start=1):
                delivery_id = f"DEL-{i:05d}"
                carrier = random.choice(CARRIERS)
                prefix = CARRIER_PREFIX[carrier]
                tracking_number = f"{prefix}-{i:08d}"

                delivery_status = ORDER_TO_DELIVERY_STATUS.get(order_status, "awaiting_pickup")
                status_ar = ARABIC_DELIVERY_STATUS.get(delivery_status, "")

                # Estimated delivery date
                estimated_date = (placed_at + timedelta(days=random.randint(1, 5))).date()

                # Delayed orders — shipped/in_transit but past estimated date
                if (delivery_status == "in_transit"
                        and delayed_count < MAX_DELAYED
                        and estimated_date < datetime.now().date()):
                    delivery_notes = "Delayed - customs clearance"
                    failed_attempts = 0
                    delayed_count += 1
                else:
                    delivery_notes = None
                    failed_attempts = random.choice([0, 0, 0, 0, 1])  # 20% chance of 1 failed attempt

                delivered_at = None
                if delivery_status == "delivered":
                    delivered_at = placed_at + timedelta(days=random.randint(1, 5))

                cur.execute("""
                    INSERT INTO deliveries
                        (delivery_id, order_id, user_id, carrier, tracking_number,
                         status, estimated_date, delivered_at,
                         delivery_address, delivery_notes, failed_attempts)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (delivery_id) DO NOTHING
                """, (
                    delivery_id, order_id, user_id, carrier, tracking_number,
                    delivery_status, estimated_date, delivered_at,
                    json.dumps(shipping_address) if isinstance(shipping_address, dict) else shipping_address,
                    delivery_notes, failed_attempts
                ))

            conn.commit()
            print(f"  Deliveries inserted: {len(orders)}, delayed orders: {delayed_count}")

if __name__ == "__main__":
    seed_deliveries()
```

---

## Step 3 — Fix seed_refunds.py

Problems to fix:
- LIMIT 20 must be removed
- Only create refunds for delivered/returned/cancelled orders
- Add order_age_days distribution for eligibility testing
- Rejected refunds must have order_age_days > 30

```python
# scripts/db/seed_refunds.py

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
                        ["processed", "pending", "rejected"],
                        weights=[0.70, 0.25, 0.05]
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
```

---

## Step 4 — Fix seed_warranties.py

Problems to fix:
- Must only create warranties for products with warranty_months > 0
- Only Electronics, Mobile_Phones, Laptops_Computers, Home_Appliances
- Only for delivered orders (warranty starts on delivery)

```python
# scripts/db/seed_warranties.py

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
    weights  = [w for _, w in WARRANTY_STATUS_WEIGHTS]
    return random.choices(statuses, weights=weights, k=1)[0]

def seed_warranties(count: int = 300):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Only warranty-eligible products in delivered orders
            cur.execute("""
                SELECT oi.order_id, o.user_id, oi.product_id, p.warranty_months
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

            for i, (order_id, user_id, product_id, warranty_months) in enumerate(selected, start=1):
                warranty_id = f"WRN-{i:05d}"
                start_date = datetime.now().date() - timedelta(days=random.randint(0, 365))
                end_date = start_date + timedelta(days=warranty_months * 30)

                # Status based on end_date
                if end_date > datetime.now().date():
                    status = random.choices(
                        ["active", "claimed"],
                        weights=[0.85, 0.15]
                    )[0]
                else:
                    status = random.choices(
                        ["expired", "claimed", "void"],
                        weights=[0.70, 0.20, 0.10]
                    )[0]

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
                    warranty_id, order_id, user_id, product_id,
                    random.choice(WARRANTY_TYPES),
                    start_date, end_date,
                    status, claim_count, last_claim_at
                ))

                if cur.rowcount > 0:
                    inserted += 1

            conn.commit()
            print(f"  Warranties inserted: {inserted}")

if __name__ == "__main__":
    seed_warranties()
```

---

## Step 5 — Fix seed_order_items.py

Problem to fix:
- item_status hardcoded to "pending" — must inherit from parent order

```python
# scripts/db/seed_order_items.py

from scripts.db.connection import get_db_connection


def seed_order_items():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, item_count, status FROM orders")
            orders = cur.fetchall()

            if not orders:
                raise RuntimeError("No orders found — run seed_orders first")

            total_inserted = 0

            for order_id, item_count, order_status in orders:
                cur.execute("""
                    SELECT product_id, price_aed
                    FROM products
                    ORDER BY RANDOM()
                    LIMIT %s
                """, (item_count,))
                products = cur.fetchall()

                for product_id, price in products:
                    quantity = 1
                    total_price = quantity * float(price)

                    cur.execute("""
                        INSERT INTO order_items
                            (order_id, product_id, quantity,
                             unit_price_aed, total_price_aed, item_status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        order_id, product_id, quantity,
                        price, total_price,
                        order_status   # inherits from order
                    ))
                    total_inserted += 1

            conn.commit()
            print(f"  Order items inserted: {total_inserted}")


if __name__ == "__main__":
    seed_order_items()
```

---

## Step 6 — Fix seed_payments.py

Problem to fix:
- failure_reason missing when status = failed
- payment amount should match order total not random

```python
# scripts/db/seed_payments.py

import random
from scripts.db.connection import get_db_connection

PAYMENT_METHODS = {
    "credit_card":  0.35,
    "noon_pay":     0.25,
    "debit_card":   0.20,
    "cod":          0.15,
    "wallet":       0.05,
}

PAYMENT_STATUS_WEIGHTS = {
    "success":          0.88,
    "failed":           0.05,
    "pending":          0.03,
    "refunded":         0.03,
    "partial_refund":   0.01,
}

FAILURE_REASONS = [
    "Insufficient funds",
    "Card expired",
    "Card declined by bank",
    "Transaction limit exceeded",
    "Invalid CVV",
    "3D Secure authentication failed",
    "Network timeout"
]

def weighted_method():
    methods  = list(PAYMENT_METHODS.keys())
    weights  = list(PAYMENT_METHODS.values())
    return random.choices(methods, weights=weights, k=1)[0]

def weighted_status():
    statuses = list(PAYMENT_STATUS_WEIGHTS.keys())
    weights  = list(PAYMENT_STATUS_WEIGHTS.values())
    return random.choices(statuses, weights=weights, k=1)[0]

def seed_payments():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, user_id, total_aed, placed_at FROM orders")
            rows = cur.fetchall()

            for i, (order_id, user_id, total_aed, placed_at) in enumerate(rows, start=1):
                payment_id = f"PAY-{i:05d}"
                method = weighted_method()
                status = weighted_status()

                failure_reason = None
                paid_at = placed_at

                if status == "failed":
                    failure_reason = random.choice(FAILURE_REASONS)
                    paid_at = None
                elif status == "pending":
                    paid_at = None

                cur.execute("""
                    INSERT INTO payments
                        (payment_id, order_id, user_id, amount_aed,
                         method, status, failure_reason,
                         transaction_ref, paid_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (payment_id) DO NOTHING
                """, (
                    payment_id, order_id, user_id, total_aed,
                    method, status, failure_reason,
                    f"TXN-{i:08d}", paid_at
                ))

            conn.commit()
            print(f"  Payments inserted: {len(rows)}")


if __name__ == "__main__":
    seed_payments()
```

---

## Step 7 — Fix verify_integrity.py

Problem to fix:
- Too few checks
- Must verify delivery/order status alignment
- Must verify delayed orders exist for eval
- Must fail loudly with SystemExit on critical failures

```python
# scripts/db/verify_integrity.py

from scripts.db.connection import get_db_connection

CHECKS = [
    {
        "name": "Orders → valid customers",
        "sql": """
            SELECT COUNT(*) FROM orders o
            LEFT JOIN customers c ON o.user_id = c.user_id
            WHERE c.user_id IS NULL
        """,
        "critical": True,
        "expect": 0
    },
    {
        "name": "Order items → valid orders",
        "sql": """
            SELECT COUNT(*) FROM order_items oi
            LEFT JOIN orders o ON oi.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "critical": True,
        "expect": 0
    },
    {
        "name": "Deliveries → valid orders",
        "sql": """
            SELECT COUNT(*) FROM deliveries d
            LEFT JOIN orders o ON d.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "critical": True,
        "expect": 0
    },
    {
        "name": "Refunds → valid orders",
        "sql": """
            SELECT COUNT(*) FROM refunds r
            LEFT JOIN orders o ON r.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "critical": True,
        "expect": 0
    },
    {
        "name": "Warranties → valid orders + products",
        "sql": """
            SELECT COUNT(*) FROM warranties w
            LEFT JOIN orders o ON w.order_id = o.order_id
            LEFT JOIN products p ON w.product_id = p.product_id
            WHERE o.order_id IS NULL OR p.product_id IS NULL
        """,
        "critical": True,
        "expect": 0
    },
    {
        "name": "Refund user matches order user",
        "sql": """
            SELECT COUNT(*) FROM refunds r
            JOIN orders o ON r.order_id = o.order_id
            WHERE r.user_id != o.user_id
        """,
        "critical": True,
        "expect": 0
    },
    {
        "name": "Warranties on non-warranty products",
        "sql": """
            SELECT COUNT(*) FROM warranties w
            JOIN products p ON w.product_id = p.product_id
            WHERE p.warranty_months = 0
        """,
        "critical": True,
        "expect": 0
    },
    {
        "name": "Rejected refunds have order_age > 30 days",
        "sql": """
            SELECT COUNT(*) FROM refunds
            WHERE status = 'rejected'
            AND (order_age_days IS NULL OR order_age_days <= 30)
        """,
        "critical": True,
        "expect": 0
    },
    {
        "name": "Delayed orders exist for eval testing",
        "sql": """
            SELECT COUNT(*) FROM deliveries
            WHERE estimated_date < NOW()
            AND status = 'in_transit'
        """,
        "critical": False,
        "expect_min": 20
    },
    {
        "name": "Refunds with order_age > 30 exist for eval testing",
        "sql": """
            SELECT COUNT(*) FROM refunds
            WHERE order_age_days > 30
        """,
        "critical": False,
        "expect_min": 30
    },
]

def verify_integrity():
    with get_db_connection() as conn:
        with conn.cursor() as cur:

            # Record counts
            tables = ["customers", "products", "orders", "order_items",
                      "payments", "deliveries", "refunds", "warranties"]
            print("\nRecord counts:")
            print("─" * 35)
            for table in tables:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"  {table:<20} {count:>6}")

            # Integrity checks
            print("\nIntegrity checks:")
            print("─" * 45)
            failures = []

            for check in CHECKS:
                cur.execute(check["sql"])
                count = cur.fetchone()[0]

                if check["critical"] and count != check["expect"]:
                    print(f"  ❌ FAIL: {check['name']} → {count} violations")
                    failures.append(check["name"])
                elif "expect_min" in check and count < check["expect_min"]:
                    print(f"  ⚠️  WARN: {check['name']} → only {count} (need ≥ {check['expect_min']})")
                else:
                    print(f"  ✅ PASS: {check['name']}")

            if failures:
                raise SystemExit(f"\n❌ Critical failures: {failures}\nFix seed data and re-run.")

            print("\n✅ All integrity checks passed.\n")


if __name__ == "__main__":
    verify_integrity()
```

---

## Step 8 — Fix seed_database.py

Problem to fix:
- seed_orders() called without count argument
- seed_refunds() called without count argument
- Add print separator between steps

```python
# scripts/seed_database.py

from scripts.db.connection import run_sql
from scripts.db.seed_customers import seed_customers
from scripts.db.seed_products import seed_products
from scripts.db.seed_orders import seed_orders
from scripts.db.seed_order_items import seed_order_items
from scripts.db.seed_payments import seed_payments
from scripts.db.seed_deliveries import seed_deliveries
from scripts.db.seed_refunds import seed_refunds
from scripts.db.seed_warranties import seed_warranties
from scripts.db.verify_integrity import verify_integrity


def main():
    print("=== Noon Agent Database Seed ===\n")

    print("Step 0: Creating schema...")
    run_sql("scripts/db/schema.sql")

    print("Step 1: Seeding customers...")
    seed_customers(count=500)

    print("Step 2: Seeding products...")
    seed_products(count=500)

    print("Step 3: Seeding orders...")
    seed_orders(count=1000)

    print("Step 4: Seeding order items...")
    seed_order_items()

    print("Step 5: Seeding payments...")
    seed_payments()

    print("Step 6: Seeding deliveries...")
    seed_deliveries()

    print("Step 7: Seeding refunds...")
    seed_refunds(count=200)

    print("Step 8: Seeding warranties...")
    seed_warranties(count=300)

    print("Step 9: Verifying integrity...")
    verify_integrity()

    print("=== Seed Complete ===")


if __name__ == "__main__":
    main()
```

---

## After All Fixes — Run This

```bash
# Clear existing data first (fresh seed)
psql -U noon -d noon_agent -c "
TRUNCATE warranties, refunds, deliveries, payments, order_items, orders, products, customers RESTART IDENTITY CASCADE;
"

# Re-run seed
python scripts/seed_database.py
```

Expected output:
```
=== Noon Agent Database Seed ===

Step 0: Creating schema...
Step 1: Seeding customers...
Step 2: Seeding products...
Step 3: Seeding orders...
  Orders inserted: 1000
Step 4: Seeding order items...
  Order items inserted: ~3000
Step 5: Seeding payments...
  Payments inserted: 1000
Step 6: Seeding deliveries...
  Deliveries inserted: 1000, delayed orders: 30
Step 7: Seeding refunds...
  Refunds inserted: 200
Step 8: Seeding warranties...
  Warranties inserted: 300

Record counts:
───────────────────────────────────
  customers              500
  products               500
  orders                1000
  order_items           ~3000
  payments              1000
  deliveries            1000
  refunds                200
  warranties             300

Integrity checks:
─────────────────────────────────────────────
  ✅ PASS: Orders → valid customers
  ✅ PASS: Order items → valid orders
  ✅ PASS: Deliveries → valid orders
  ✅ PASS: Refunds → valid orders
  ✅ PASS: Warranties → valid orders + products
  ✅ PASS: Refund user matches order user
  ✅ PASS: Warranties on non-warranty products
  ✅ PASS: Rejected refunds have order_age > 30 days
  ✅ PASS: Delayed orders exist for eval testing
  ✅ PASS: Refunds with order_age > 30 exist

✅ All integrity checks passed.