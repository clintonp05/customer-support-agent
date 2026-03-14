from faker import Faker
import random
from scripts.db.connection import get_db_connection

fake = Faker()


def seed_products(count: int = 50):
    categories = ["Electronics", "Mobile_Phones", "Laptops_Computers", "Home_Appliances", "Fashion_Men", "Fashion_Women"]
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for i in range(1, count + 1):
                product_id = f"PRD-{i:05d}"
                category = random.choice(categories)
                price = round(random.uniform(50, 3000), 2)
                cur.execute(
                    "INSERT INTO products (product_id, name_en, name_ar, category, subcategory, brand, price_aed, warranty_months, in_stock) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (product_id) DO NOTHING",
                    (
                        product_id,
                        fake.sentence(nb_words=3),
                        fake.sentence(nb_words=3),
                        category,
                        "General",
                        fake.company(),
                        price,
                        random.choice([0, 6, 12, 24]),
                        True,
                    ),
                )
        conn.commit()


if __name__ == "__main__":
    seed_products()