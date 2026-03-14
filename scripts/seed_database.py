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
    run_sql("scripts/db/schema.sql")
    print("Schema created")

    seed_customers(count=500)
    print("Customers seeded")

    seed_products(count=500)
    print("Products seeded")

    seed_orders()
    print("Orders seeded")

    seed_order_items()
    print("Order items seeded")

    seed_payments()
    print("Payments seeded")

    seed_deliveries()
    print("Deliveries seeded")

    seed_refunds()
    print("Refunds seeded")

    seed_warranties()
    print("Warranties seeded")

    verify_integrity()
    print("Referential integrity verified")


if __name__ == "__main__":
    main()
