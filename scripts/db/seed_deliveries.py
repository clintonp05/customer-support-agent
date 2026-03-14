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
            inserted = 0

            for i, (order_id, user_id, order_status, placed_at, shipping_address) in enumerate(orders, start=1):
                delivery_id = f"DEL-{i:05d}"
                carrier = random.choice(CARRIERS)
                prefix = CARRIER_PREFIX[carrier]
                tracking_number = f"{prefix}-{i:08d}"

                delivery_status = ORDER_TO_DELIVERY_STATUS.get(order_status, "awaiting_pickup")
                status_ar = ARABIC_DELIVERY_STATUS.get(delivery_status, "")

                estimated_date = (placed_at + timedelta(days=random.randint(1, 5))).date() if placed_at else datetime.now().date() + timedelta(days=random.randint(1, 5))

                if (delivery_status in ["in_transit", "out_for_delivery"]
                        and delayed_count < MAX_DELAYED
                        and estimated_date < datetime.now().date()):
                    delivery_notes = "Delayed - customs clearance"
                    failed_attempts = 0
                    delayed_count += 1
                else:
                    delivery_notes = None
                    failed_attempts = random.choice([0, 0, 0, 0, 1])

                delivered_at = None
                if delivery_status == "delivered":
                    delivered_at = placed_at + timedelta(days=random.randint(1, 5)) if placed_at else datetime.now()

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
                inserted += 1

            conn.commit()
            print(f"  Deliveries inserted: {inserted}, delayed orders: {delayed_count}")


if __name__ == "__main__":
    seed_deliveries()