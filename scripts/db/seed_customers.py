from faker import Faker
import random
from scripts.db.connection import get_db_connection

fake = Faker()


def seed_customers(count: int = 50):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for i in range(1, count + 1):
                user_id = f"USR-{i:05d}"
                email = f"{user_id.lower()}@example.com"
                city = random.choice(["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "RAK"])
                tier = random.choice(["STANDARD", "SILVER", "GOLD", "PLATINUM"])
                cur.execute(
                    "INSERT INTO customers (user_id, name_en, name_ar, email, phone, city, tier, preferred_language) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING",
                    (
                        user_id,
                        fake.name(),
                        fake.name(),
                        email,
                        fake.msisdn()[:20],
                        city,
                        tier,
                        random.choice(["en", "ar"]),
                    ),
                )
        conn.commit()


if __name__ == "__main__":
    seed_customers()