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