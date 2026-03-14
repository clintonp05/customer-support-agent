from faker import Faker
import random
from scripts.db.connection import get_db_connection

fake = Faker()

CATEGORY_WARRANTY_MONTHS = {
    "Electronics": 24,
    "Mobile_Phones": 12,
    "Laptops_Computers": 12,
    "Home_Appliances": 24,
    "Fashion_Men": 0,
    "Fashion_Women": 0,
    "Kids": 0,
    "Home_Living": 0,
    "Beauty_Health": 0,
    "Sports_Outdoors": 0,
}


def seed_products(count: int = 50):
    categories = list(CATEGORY_WARRANTY_MONTHS.keys())
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for i in range(1, count + 1):
                product_id = f"PRD-{i:05d}"
                category = random.choice(categories)
                price = round(random.uniform(50, 3000), 2)
                warranty_months = CATEGORY_WARRANTY_MONTHS.get(category, 0)
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
                        warranty_months,
                        True,
                    ),
                )
        conn.commit()


if __name__ == "__main__":
    seed_products()