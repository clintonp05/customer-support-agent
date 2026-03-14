from scripts.db.connection import get_db_connection


def verify_integrity():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            checks = [
                ("customers", "SELECT COUNT(*) FROM customers"),
                ("products", "SELECT COUNT(*) FROM products"),
                ("orders", "SELECT COUNT(*) FROM orders"),
                ("order_items", "SELECT COUNT(*) FROM order_items"),
                ("payments", "SELECT COUNT(*) FROM payments"),
                ("deliveries", "SELECT COUNT(*) FROM deliveries"),
                ("refunds", "SELECT COUNT(*) FROM refunds"),
                ("warranties", "SELECT COUNT(*) FROM warranties"),
            ]
            for name, sql in checks:
                cur.execute(sql)
                count = cur.fetchone()[0]
                print(f"{name}: {count}")

            # Referential checks
            cur.execute("SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON o.user_id=c.user_id WHERE c.user_id IS NULL")
            missing_orders = cur.fetchone()[0]
            assert missing_orders == 0, "Orders refer to missing customers"
            print("Referential integrity checks passed")


if __name__ == "__main__":
    verify_integrity()