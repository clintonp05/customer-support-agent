# DATABASE_SEED.md — Operational Database Seed
## Claude Code Instructions for Noon Customer Support Agent

---

## Objective

Create all operational database tables and seed realistic data.
This is the data the agent tools query when a customer contacts support.
Scope: support for orders already placed. No product discovery.
Context: UAE e-commerce. Arabic + English. Currency AED.

---

## Build Order

Run in this exact sequence:
1. Create schema (tables + indexes + constraints)
2. Seed customers
3. Seed products (with categories)
4. Seed orders
5. Seed order_items (references orders + products)
6. Seed payments (references orders)
7. Seed deliveries (references orders)
8. Seed refunds (references orders + customers)
9. Seed warranties (references orders + products)
10. Verify referential integrity

---

## File Structure to Create

```
scripts/
├── db/
│   ├── schema.sql              ← all table definitions
│   ├── seed_customers.py
│   ├── seed_products.py
│   ├── seed_orders.py
│   ├── seed_order_items.py
│   ├── seed_payments.py
│   ├── seed_deliveries.py
│   ├── seed_refunds.py
│   ├── seed_warranties.py
│   └── verify_integrity.py
└── seed_database.py            ← master script, runs all above in order
```

---

## Schema — scripts/db/schema.sql

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────
-- CUSTOMERS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    user_id             VARCHAR(20) PRIMARY KEY,  -- USR-XXXXXXXX
    name_en             VARCHAR(100) NOT NULL,
    name_ar             VARCHAR(100),
    email               VARCHAR(150) UNIQUE NOT NULL,
    phone               VARCHAR(20),              -- +971-5X-XXXXXXX
    city                VARCHAR(50),              -- Dubai, Abu Dhabi, Sharjah, Ajman, RAK
    tier                VARCHAR(20) DEFAULT 'STANDARD',  -- STANDARD, SILVER, GOLD, PLATINUM
    preferred_language  VARCHAR(10) DEFAULT 'en', -- en, ar
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- PRODUCTS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    product_id          VARCHAR(20) PRIMARY KEY,  -- PRD-XXXXXXXX
    name_en             VARCHAR(200) NOT NULL,
    name_ar             VARCHAR(200),
    category            VARCHAR(50) NOT NULL,     -- see categories below
    subcategory         VARCHAR(50),
    brand               VARCHAR(100),
    price_aed           DECIMAL(10, 2) NOT NULL,
    warranty_months     INTEGER DEFAULT 0,         -- 0 = no warranty
    is_returnable       BOOLEAN DEFAULT TRUE,
    return_window_days  INTEGER DEFAULT 30,
    in_stock            BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- Product categories:
-- Electronics, Mobile_Phones, Laptops_Computers, Home_Appliances,
-- Fashion_Men, Fashion_Women, Kids, Home_Living, Beauty_Health,
-- Sports_Outdoors, Grocery, Automotive, Books_Media

-- ─────────────────────────────────────────
-- ORDERS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    order_id            VARCHAR(25) PRIMARY KEY,   -- N-YYYYMMDD-XXXXX
    user_id             VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    status              VARCHAR(30) NOT NULL,       -- see distribution below
    status_ar           VARCHAR(50),               -- Arabic status label
    total_aed           DECIMAL(10, 2) NOT NULL,
    item_count          INTEGER NOT NULL,
    placed_at           TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP DEFAULT NOW(),
    shipping_address    JSONB,                     -- {city, area, street, building}
    notes               TEXT
);

-- Status distribution (enforce in seed):
-- pending          10%  (100 orders)
-- confirmed        15%  (150 orders)
-- shipped          20%  (200 orders)
-- out_for_delivery 10%  (100 orders)
-- delivered        30%  (300 orders)
-- cancelled        10%  (100 orders)
-- returned          5%  (50 orders)

-- ─────────────────────────────────────────
-- ORDER ITEMS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_items (
    item_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    product_id          VARCHAR(20) NOT NULL REFERENCES products(product_id),
    quantity            INTEGER NOT NULL DEFAULT 1,
    unit_price_aed      DECIMAL(10, 2) NOT NULL,
    total_price_aed     DECIMAL(10, 2) NOT NULL,
    item_status         VARCHAR(30),               -- can differ from order status
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- PAYMENTS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payments (
    payment_id          VARCHAR(25) PRIMARY KEY,   -- PAY-YYYYMMDD-XXXXX
    order_id            VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    user_id             VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    amount_aed          DECIMAL(10, 2) NOT NULL,
    method              VARCHAR(30) NOT NULL,       -- credit_card, debit_card, noon_pay, cod, wallet
    status              VARCHAR(20) NOT NULL,       -- success, failed, pending, refunded, partial_refund
    failure_reason      VARCHAR(100),              -- populated when status = failed
    transaction_ref     VARCHAR(50),
    paid_at             TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- Payment method distribution:
-- credit_card  35%
-- noon_pay     25%
-- debit_card   20%
-- cod          15%
-- wallet        5%

-- Payment status distribution:
-- success          88%
-- failed            5%
-- pending           3%
-- refunded          3%
-- partial_refund    1%

-- ─────────────────────────────────────────
-- DELIVERIES
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id         VARCHAR(25) PRIMARY KEY,   -- DEL-YYYYMMDD-XXXXX
    order_id            VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    user_id             VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    carrier             VARCHAR(50),               -- noon_express, aramex, fetchr, smsa
    tracking_number     VARCHAR(50),
    status              VARCHAR(30) NOT NULL,       -- must align with order status
    status_ar           VARCHAR(50),
    estimated_date      DATE,
    delivered_at        TIMESTAMP,
    delivery_address    JSONB,
    delivery_notes      TEXT,
    failed_attempts     INTEGER DEFAULT 0,         -- for failed delivery cases
    created_at          TIMESTAMP DEFAULT NOW()
);

-- Delivery status must align with order status:
-- order.pending          → delivery.awaiting_pickup
-- order.confirmed        → delivery.awaiting_pickup
-- order.shipped          → delivery.in_transit
-- order.out_for_delivery → delivery.out_for_delivery
-- order.delivered        → delivery.delivered
-- order.cancelled        → delivery.cancelled
-- order.returned         → delivery.returned

-- Include these edge cases (deliberate):
-- 50 deliveries with failed_attempts >= 1  (delivery attempt failed)
-- 30 deliveries with estimated_date < NOW() but status != delivered (delayed)
-- 20 deliveries with wrong_address flag in delivery_notes

-- ─────────────────────────────────────────
-- REFUNDS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS refunds (
    refund_id           VARCHAR(25) PRIMARY KEY,   -- REF-YYYYMMDD-XXXXX
    order_id            VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    user_id             VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    payment_id          VARCHAR(25) REFERENCES payments(payment_id),
    amount_aed          DECIMAL(10, 2) NOT NULL,
    reason              VARCHAR(100),
    status              VARCHAR(20) NOT NULL,       -- pending, processed, rejected
    rejection_reason    VARCHAR(200),              -- populated when status = rejected
    order_age_days      INTEGER,                   -- days between order placed and refund request
    refund_method       VARCHAR(30),               -- original_payment, wallet, bank_transfer
    processed_at        TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- Refund status distribution:
-- processed  60% (120)
-- pending    25%  (50)
-- rejected   15%  (30)

-- Order age distribution (critical for eligibility rules):
-- < 7 days     40%  (80)   → clearly eligible
-- 7-30 days    30%  (60)   → eligible
-- 31-60 days   20%  (40)   → ineligible (outside 30 day policy)
-- > 60 days    10%  (20)   → ineligible

-- Rejection reasons to include:
-- "Order older than 30 days"
-- "Product is non-returnable"
-- "Refund already processed for this order"
-- "Item shows signs of use"

-- ─────────────────────────────────────────
-- WARRANTIES
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS warranties (
    warranty_id         VARCHAR(25) PRIMARY KEY,   -- WRN-YYYYMMDD-XXXXX
    order_id            VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    user_id             VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    product_id          VARCHAR(20) NOT NULL REFERENCES products(product_id),
    warranty_type       VARCHAR(30),               -- manufacturer, extended, noon_protect
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    status              VARCHAR(20) NOT NULL,       -- active, expired, claimed, void
    claim_count         INTEGER DEFAULT 0,
    last_claim_at       TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- Warranty status distribution:
-- active    50% (150)
-- expired   30%  (90)
-- claimed   15%  (45)
-- void       5%  (15)

-- Only products with warranty_months > 0 get warranty records
-- warranty categories: Electronics, Mobile_Phones, Laptops_Computers, Home_Appliances

-- ─────────────────────────────────────────
-- INDEXES
-- ─────────────────────────────────────────

-- Orders
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_placed_at ON orders(placed_at);

-- Order items
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);

-- Payments
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

-- Deliveries
CREATE INDEX IF NOT EXISTS idx_deliveries_order_id ON deliveries(order_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_user_id ON deliveries(user_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status);

-- Refunds
CREATE INDEX IF NOT EXISTS idx_refunds_order_id ON refunds(order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_user_id ON refunds(user_id);
CREATE INDEX IF NOT EXISTS idx_refunds_status ON refunds(status);
CREATE INDEX IF NOT EXISTS idx_refunds_order_age ON refunds(order_age_days);

-- Warranties
CREATE INDEX IF NOT EXISTS idx_warranties_order_id ON warranties(order_id);
CREATE INDEX IF NOT EXISTS idx_warranties_user_id ON warranties(user_id);
CREATE INDEX IF NOT EXISTS idx_warranties_product_id ON warranties(product_id);
CREATE INDEX IF NOT EXISTS idx_warranties_status ON warranties(status);
```

---

## Seed Data Specifications

---

### customers — 500 records

```python
# scripts/db/seed_customers.py

UAE_CITIES = ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah"]

ARABIC_NAMES = [
    "محمد الأحمدي", "فاطمة العلي", "أحمد المنصوري", "مريم الهاشمي",
    "عمر الشامسي", "نور الكتبي", "خالد الزعابي", "لطيفة المزروعي",
    "سالم الرميثي", "عائشة الفلاسي", "يوسف الظاهري", "هند المهيري",
    "راشد النعيمي", "شيخة البلوشي", "سعيد الحمادي", "منى الطنيجي"
]

ENGLISH_NAMES = [
    "James Wilson", "Priya Sharma", "David Chen", "Sarah Johnson",
    "Mohammed Al-Rashid", "Aisha Rahman", "Carlos Rodriguez", "Emily Thompson",
    "Raj Patel", "Lisa Park", "Omar Hassan", "Jennifer Smith",
    "Kevin O'Brien", "Fatima Malik", "Andrew Brown", "Zara Ahmed"
]

TIER_DISTRIBUTION = {
    "STANDARD":  0.60,   # 300 customers
    "SILVER":    0.25,   # 125 customers
    "GOLD":      0.12,   #  60 customers
    "PLATINUM":  0.03,   #  15 customers
}

LANGUAGE_DISTRIBUTION = {
    "en": 0.60,   # 300 customers prefer English
    "ar": 0.40,   # 200 customers prefer Arabic
}

# ID format: USR-XXXXXXXX (8 random alphanumeric uppercase)
# Phone format: +971-5X-XXXXXXX
# Email: firstname.lastname@domain.com (gmail, yahoo, hotmail, icloud)
# Generate 500 customers with realistic distribution above
# 200 customers must have name_ar populated (Arabic-preferring customers)
```

---

### products — 500 records

```python
# scripts/db/seed_products.py

PRODUCT_CATEGORIES = {
    "Electronics": {
        "count": 80,
        "subcategories": ["TVs", "Audio", "Cameras", "Gaming", "Tablets"],
        "brands": ["Samsung", "LG", "Sony", "Philips", "JBL", "Bose"],
        "price_range": (199, 8999),
        "warranty_months": 24,
        "return_window_days": 15
    },
    "Mobile_Phones": {
        "count": 60,
        "subcategories": ["Smartphones", "Feature_Phones", "Accessories"],
        "brands": ["Apple", "Samsung", "Huawei", "Xiaomi", "OnePlus", "Google"],
        "price_range": (299, 6999),
        "warranty_months": 12,
        "return_window_days": 15
    },
    "Laptops_Computers": {
        "count": 50,
        "subcategories": ["Laptops", "Desktops", "Monitors", "Peripherals"],
        "brands": ["Apple", "Dell", "HP", "Lenovo", "ASUS", "Microsoft"],
        "price_range": (999, 12999),
        "warranty_months": 12,
        "return_window_days": 15
    },
    "Home_Appliances": {
        "count": 70,
        "subcategories": ["Refrigerators", "Washing_Machines", "AC", "Microwaves", "Vacuums"],
        "brands": ["Samsung", "LG", "Bosch", "Midea", "Panasonic"],
        "price_range": (299, 7999),
        "warranty_months": 24,
        "return_window_days": 7
    },
    "Fashion_Men": {
        "count": 50,
        "subcategories": ["Shirts", "Trousers", "Shoes", "Watches", "Bags"],
        "brands": ["Nike", "Adidas", "Zara", "H&M", "Polo"],
        "price_range": (49, 1499),
        "warranty_months": 0,
        "return_window_days": 30
    },
    "Fashion_Women": {
        "count": 50,
        "subcategories": ["Dresses", "Tops", "Shoes", "Bags", "Jewelry"],
        "brands": ["Zara", "H&M", "Mango", "Charles_Keith", "Michael_Kors"],
        "price_range": (49, 2999),
        "warranty_months": 0,
        "return_window_days": 30
    },
    "Kids": {
        "count": 40,
        "subcategories": ["Toys", "Clothing", "School_Supplies", "Baby"],
        "brands": ["LEGO", "Fisher_Price", "Mattel", "VTech", "Chicco"],
        "price_range": (29, 799),
        "warranty_months": 0,
        "return_window_days": 30
    },
    "Home_Living": {
        "count": 40,
        "subcategories": ["Furniture", "Bedding", "Kitchen", "Decor"],
        "brands": ["IKEA", "Pan_Emirates", "Homes_r_us", "Pottery_Barn"],
        "price_range": (49, 4999),
        "warranty_months": 0,
        "return_window_days": 14
    },
    "Beauty_Health": {
        "count": 30,
        "subcategories": ["Skincare", "Haircare", "Fragrances", "Vitamins"],
        "brands": ["LOreal", "Nivea", "Neutrogena", "Garnier", "Cetaphil"],
        "price_range": (19, 599),
        "warranty_months": 0,
        "return_window_days": 0,   # non-returnable
        "is_returnable": False
    },
    "Sports_Outdoors": {
        "count": 30,
        "subcategories": ["Fitness", "Outdoor", "Team_Sports", "Swimming"],
        "brands": ["Nike", "Adidas", "Under_Armour", "Decathlon"],
        "price_range": (49, 2999),
        "warranty_months": 0,
        "return_window_days": 30
    }
}

# ID format: PRD-XXXXXXXX
# Generate realistic product names combining brand + subcategory + model
# e.g. "Samsung 55-inch 4K Smart TV UA55CU8000"
# Arabic name: "سامسونج تلفزيون ذكي 55 بوصة"
# Ensure price variety within each category range
# 20% of products set in_stock = False
```

---

### orders — 1000 records

```python
# scripts/db/seed_orders.py

import random
from datetime import datetime, timedelta

# ID format: N-YYYYMMDD-XXXXX (5 random uppercase alphanumeric)
# e.g. N-20240312-AB123

ORDER_STATUS_DISTRIBUTION = {
    "pending":          0.10,   # 100 orders
    "confirmed":        0.15,   # 150 orders
    "shipped":          0.20,   # 200 orders
    "out_for_delivery": 0.10,   # 100 orders
    "delivered":        0.30,   # 300 orders
    "cancelled":        0.10,   # 100 orders
    "returned":         0.05,   #  50 orders
}

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
    "Dubai": ["Downtown", "Marina", "JBR", "Deira", "Bur_Dubai", "JLT", "Silicon_Oasis", "Al_Quoz"],
    "Abu Dhabi": ["Corniche", "Khalidiyah", "Mussafah", "Al_Reem", "Yas_Island"],
    "Sharjah": ["Al_Majaz", "Al_Nahda", "Al_Qasimiyah", "Al_Khan"],
    "Ajman": ["Al_Nuaimia", "Al_Rashidiya", "Al_Jurf"],
    "Ras Al Khaimah": ["Al_Nakheel", "Al_Qawasem", "Dafan"]
}

# Order date range: last 12 months
# Each customer should have 1-5 orders
# shipping_address must match customer city
# total_aed = sum of order_items (calculated after items seeded)
# item_count = number of items in order_items (calculated after items seeded)

# Deliberate edge cases to include:
# - 50 orders placed exactly 29-31 days ago (refund eligibility boundary testing)
# - 30 orders with same customer, different statuses (repeat customer testing)
# - 20 orders with COD payment and delivered status (cash on delivery edge case)
# - 10 orders with multiple items from different categories
```

---

### order_items — 3000 records

```python
# scripts/db/seed_order_items.py

# Each order gets 1-5 items
# Distribution:
# 1 item:  40% of orders (400 orders)
# 2 items: 30% of orders (300 orders)
# 3 items: 20% of orders (200 orders)
# 4-5 items: 10% of orders (100 orders)

# Total: ~3000 items across 1000 orders

# Rules:
# unit_price_aed = product.price_aed (at time of order)
# total_price_aed = unit_price_aed * quantity
# item_status = order.status (inherit from parent order)
# quantity is almost always 1 — use quantity > 1 for only 5% of items

# After inserting all items:
# UPDATE orders SET
#   total_aed = (SELECT SUM(total_price_aed) FROM order_items WHERE order_id = orders.order_id),
#   item_count = (SELECT COUNT(*) FROM order_items WHERE order_id = orders.order_id)
```

---

### payments — 1200 records

```python
# scripts/db/seed_payments.py

# ID format: PAY-YYYYMMDD-XXXXX

# Every order has exactly 1 payment record
# 200 extra records = payment retries (failed first attempt, success on retry)

PAYMENT_METHOD_DISTRIBUTION = {
    "credit_card":  0.35,   # 420
    "noon_pay":     0.25,   # 300
    "debit_card":   0.20,   # 240
    "cod":          0.15,   # 180
    "wallet":       0.05,   #  60
}

PAYMENT_STATUS_DISTRIBUTION = {
    "success":          0.88,   # 1056
    "failed":           0.05,   #   60
    "pending":          0.03,   #   36
    "refunded":         0.03,   #   36
    "partial_refund":   0.01,   #   12
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

# paid_at: should be within minutes of order placed_at
# COD payments: paid_at = delivery delivered_at timestamp
# failed payments: failure_reason must be populated
# transaction_ref: realistic format e.g. "TXN-20240312-XXXXXXXX"
```

---

### deliveries — 1000 records

```python
# scripts/db/seed_deliveries.py

# ID format: DEL-YYYYMMDD-XXXXX
# One delivery record per order

CARRIERS = {
    "noon_express": 0.40,
    "aramex":       0.30,
    "fetchr":       0.20,
    "smsa":         0.10
}

ARABIC_DELIVERY_STATUS = {
    "awaiting_pickup":   "في انتظار الاستلام",
    "in_transit":        "في الطريق",
    "out_for_delivery":  "قيد التوصيل",
    "delivered":         "تم التسليم",
    "cancelled":         "ملغى",
    "returned":          "تم الإرجاع",
    "failed_attempt":    "محاولة توصيل فاشلة"
}

# CRITICAL: delivery.status must align with order.status
# Use ARABIC_DELIVERY_STATUS for status_ar field

# tracking_number format: carrier-specific
# noon_express: NE-XXXXXXXXXX
# aramex:       ARM-XXXXXXXXX
# fetchr:       FTR-XXXXXXXXX
# smsa:         SMS-XXXXXXXXX

# estimated_date rules:
# pending/confirmed: estimated_date = placed_at + 2-5 days
# shipped: estimated_date = placed_at + 1-3 days
# out_for_delivery: estimated_date = today
# delivered: estimated_date was within placed_at + 1-7 days
# delivered_at: populated only when status = delivered

# Deliberate edge cases (hard-code these):
# 50 records: failed_attempts = 1 (delivery attempted, nobody home)
# 30 records: estimated_date < NOW() AND status IN (shipped, out_for_delivery)
#             → these are DELAYED orders (past estimated date, not delivered)
# 20 records: delivery_notes contains "Wrong address - returned to hub"
```

---

### refunds — 200 records

```python
# scripts/db/seed_refunds.py

# ID format: REF-YYYYMMDD-XXXXX
# Only create refunds for orders with status IN (delivered, returned, cancelled)

REFUND_STATUS_DISTRIBUTION = {
    "processed":  0.60,   # 120
    "pending":    0.25,   #  50
    "rejected":   0.15,   #  30
}

REFUND_REASONS = [
    "Item not as described",
    "Wrong item delivered",
    "Item arrived damaged",
    "Item stopped working",
    "Changed my mind",
    "Found better price elsewhere",
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

REFUND_METHODS = {
    "original_payment":  0.60,
    "wallet":            0.30,
    "bank_transfer":     0.10
}

# order_age_days distribution (CRITICAL for eligibility testing):
# < 7 days:   40% (80 refunds)  → clearly eligible
# 7-30 days:  30% (60 refunds)  → eligible
# 31-60 days: 20% (40 refunds)  → ineligible — use these for rejection cases
# > 60 days:  10% (20 refunds)  → ineligible — use these for rejection cases

# Rules:
# rejected refunds MUST have rejection_reason populated
# rejected refunds MUST have order_age_days > 30 OR is_returnable = false
# processed refunds MUST have processed_at populated
# refund amount_aed must not exceed original payment amount
# refund.user_id must match refund.order.user_id
```

---

### warranties — 300 records

```python
# scripts/db/seed_warranties.py

# ID format: WRN-YYYYMMDD-XXXXX
# Only products with warranty_months > 0 get warranty records
# Categories with warranties: Electronics, Mobile_Phones, Laptops_Computers, Home_Appliances

WARRANTY_TYPES = {
    "manufacturer":  0.70,   # 210
    "extended":      0.20,   #  60
    "noon_protect":  0.10,   #  30
}

WARRANTY_STATUS_DISTRIBUTION = {
    "active":   0.50,   # 150
    "expired":  0.30,   #  90
    "claimed":  0.15,   #  45
    "void":     0.05,   #  15
}

# start_date = order delivered_at date
# end_date = start_date + product.warranty_months (in months)
# active: end_date > NOW()
# expired: end_date < NOW()
# claimed: claim_count >= 1, last_claim_at populated
# void: delivery failed or order cancelled

# CRITICAL referential integrity:
# warranty.product_id must exist in products AND in the order's items
# warranty.order_id must be a delivered order
# warranty.user_id must match order.user_id
```

---

## Master Seed Script — scripts/seed_database.py

```python
#!/usr/bin/env python3
"""
Master database seed script.
Runs all seed scripts in correct order.
Safe to run multiple times (idempotent).
"""
import subprocess
import sys
from pathlib import Path

SEED_SCRIPTS = [
    "scripts/db/seed_customers.py",
    "scripts/db/seed_products.py",
    "scripts/db/seed_orders.py",
    "scripts/db/seed_order_items.py",
    "scripts/db/seed_payments.py",
    "scripts/db/seed_deliveries.py",
    "scripts/db/seed_refunds.py",
    "scripts/db/seed_warranties.py",
    "scripts/db/verify_integrity.py",
]

def run_seed():
    print("=== Noon Agent Database Seed ===\n")
    
    # Run migrations first
    print("Step 0: Running migrations...")
    subprocess.run([sys.executable, "scripts/migrate.py"], check=True)
    
    for script in SEED_SCRIPTS:
        name = Path(script).stem
        print(f"\nRunning: {name}...")
        subprocess.run([sys.executable, script], check=True)
    
    print("\n=== Seed Complete ===")
    print_summary()

def print_summary():
    """Query DB and print record counts per table"""
    import psycopg2
    from src.config import settings
    
    tables = [
        "customers", "products", "orders",
        "order_items", "payments", "deliveries",
        "refunds", "warranties"
    ]
    
    conn = psycopg2.connect(settings.DATABASE_URL)
    cur = conn.cursor()
    
    print("\nDatabase Summary:")
    print("─" * 35)
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table:<20} {count:>6} records")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    run_seed()
```

---

## Verify Integrity — scripts/db/verify_integrity.py

```python
"""
Verify all foreign key relationships are valid.
Prints warnings for any orphaned records.
Fails loudly if critical integrity violations found.
"""
import psycopg2
from src.config import settings

CHECKS = [
    {
        "name": "Order items → valid orders",
        "sql": """
            SELECT COUNT(*) FROM order_items oi
            LEFT JOIN orders o ON oi.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "critical": True
    },
    {
        "name": "Deliveries → valid orders",
        "sql": """
            SELECT COUNT(*) FROM deliveries d
            LEFT JOIN orders o ON d.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "critical": True
    },
    {
        "name": "Refunds → valid orders",
        "sql": """
            SELECT COUNT(*) FROM refunds r
            LEFT JOIN orders o ON r.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "critical": True
    },
    {
        "name": "Warranties → valid orders + products",
        "sql": """
            SELECT COUNT(*) FROM warranties w
            LEFT JOIN orders o ON w.order_id = o.order_id
            LEFT JOIN products p ON w.product_id = p.product_id
            WHERE o.order_id IS NULL OR p.product_id IS NULL
        """,
        "critical": True
    },
    {
        "name": "Refund user matches order user",
        "sql": """
            SELECT COUNT(*) FROM refunds r
            JOIN orders o ON r.order_id = o.order_id
            WHERE r.user_id != o.user_id
        """,
        "critical": True
    },
    {
        "name": "Delayed orders exist (for eval cases)",
        "sql": """
            SELECT COUNT(*) FROM deliveries
            WHERE estimated_date < NOW()
            AND status IN ('in_transit', 'out_for_delivery')
        """,
        "critical": False,
        "expected_min": 20
    },
    {
        "name": "Refunds with order_age > 30 days exist",
        "sql": """
            SELECT COUNT(*) FROM refunds
            WHERE order_age_days > 30
        """,
        "critical": False,
        "expected_min": 30
    }
]

def verify():
    conn = psycopg2.connect(settings.DATABASE_URL)
    cur = conn.cursor()
    
    print("\nVerifying referential integrity...")
    print("─" * 45)
    
    failures = []
    
    for check in CHECKS:
        cur.execute(check["sql"])
        count = cur.fetchone()[0]
        
        if check["critical"] and count > 0:
            print(f"  ❌ FAIL: {check['name']} — {count} violations")
            failures.append(check["name"])
        elif "expected_min" in check and count < check["expected_min"]:
            print(f"  ⚠️  WARN: {check['name']} — only {count} (expected ≥ {check['expected_min']})")
        else:
            print(f"  ✅ PASS: {check['name']}")
    
    cur.close()
    conn.close()
    
    if failures:
        raise SystemExit(f"\nCritical integrity failures: {failures}")
    
    print("\nAll integrity checks passed.")

if __name__ == "__main__":
    verify()
```

---

## Updated Makefile Commands

Add these to your existing Makefile:

```makefile
migrate:
	python scripts/migrate.py

seed-db:
	python scripts/seed_database.py

seed-all: seed-db seed
	@echo "Database and intent index seeded."

db-shell:
	docker-compose exec postgres psql -U noon -d noon_agent

verify:
	python scripts/db/verify_integrity.py
```

---

## Run Sequence

```bash
# 1. Start infrastructure
make up

# 2. Run DB schema migrations
make migrate

# 3. Seed operational data
make seed-db

# 4. Verify integrity
make verify

# 5. Seed intent index (from original CLAUDE.md)
python scripts/seed_intent_index.py

# 6. Start the agent
make run
```

---

## Summary of What Gets Created

```
Table           Records    Key details
────────────────────────────────────────────────────────
customers           500    UAE cities, Arabic + English names, tier distribution
products            500    10 categories, warranty fields, returnable flags
orders             1000    7 status types, correct distribution, UAE addresses
order_items        3000    ~3 per order, references valid products
payments           1200    5 methods, failure reasons, retry records
deliveries         1000    4 carriers, delayed edge cases, failed attempts
refunds             200    3 statuses, age distribution, rejection reasons
warranties          300    4 statuses, warranty-eligible products only
────────────────────────────────────────────────────────
Total              7700    rows, full referential integrity
```