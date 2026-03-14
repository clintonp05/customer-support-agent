from scripts.db.connection import get_db_connection


def seed_order_items():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT order_id, item_count FROM orders")
            orders = cur.fetchall()
            if not orders:
                raise RuntimeError("No orders found to create order items")
            for order_id, item_count in orders:
                cur.execute("SELECT product_id, price_aed FROM products ORDER BY RANDOM() LIMIT %s", (item_count,))
                products = cur.fetchall()
                for product_id, price in products:
                    quantity = 1
                    total_price = quantity * float(price)
                    cur.execute(
                        "INSERT INTO order_items (order_id, product_id, quantity, unit_price_aed, total_price_aed, item_status) VALUES (%s,%s,%s,%s,%s,%s)",
                        (order_id, product_id, quantity, price, total_price, "pending"),
                    )
        conn.commit()


if __name__ == "__main__":
    seed_order_items()