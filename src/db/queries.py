from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, date
import time

from src.db.connector import get_db_cursor
from src.observability.logger import get_logger

logger = get_logger()


def _convert_decimals(obj):
    """Recursively convert Decimal and datetime values for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_decimals(item) for item in obj]
    return obj


def get_order_by_id(order_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
    start = time.time()
    logger.info("db.query.start", query="get_order_by_id", order_id=order_id, user_id=user_id)

    try:
        with get_db_cursor() as cur:
            query = """
            SELECT o.order_id, o.user_id, o.status, o.total_aed, o.item_count, o.placed_at, o.updated_at,
                   o.shipping_address, o.notes
            FROM orders o
            WHERE o.order_id = %s
            """
            params = [order_id]
            if user_id:
                query += " AND o.user_id = %s"
                params.append(user_id)
            cur.execute(query, tuple(params))
            order = cur.fetchone()
            if not order:
                elapsed_ms = int((time.time() - start) * 1000)
                logger.info("db.query.not_found", query="get_order_by_id", order_id=order_id, elapsed_ms=elapsed_ms)
                return None

            cur.execute(
                "SELECT item_id, product_id, quantity, unit_price_aed, total_price_aed, item_status FROM order_items WHERE order_id = %s",
                (order_id,)
            )
            items = cur.fetchall()
            order["items"] = items

            cur.execute(
                "SELECT payment_id, method, amount_aed, status, transaction_ref, paid_at FROM payments WHERE order_id = %s",
                (order_id,)
            )
            payments = cur.fetchall()
            order["payments"] = payments

            cur.execute(
                "SELECT delivery_id, carrier, tracking_number, status, estimated_date, delivered_at, delivery_address FROM deliveries WHERE order_id = %s",
                (order_id,)
            )
            delivery = cur.fetchone()
            order["delivery"] = delivery

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info("db.query.complete", query="get_order_by_id", order_id=order_id, elapsed_ms=elapsed_ms, found=True)
            return _convert_decimals(order)

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error("db.query.error", query="get_order_by_id", order_id=order_id, error=str(e), elapsed_ms=elapsed_ms)
        raise


def get_delivery_by_order(order_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
    start = time.time()
    logger.info("db.query.start", query="get_delivery_by_order", order_id=order_id)

    try:
        with get_db_cursor() as cur:
            query = "SELECT delivery_id, order_id, user_id, carrier, tracking_number, status, estimated_date, delivered_at, delivery_address, delivery_notes FROM deliveries WHERE order_id = %s"
            params = [order_id]
            if user_id:
                query += " AND user_id = %s"
                params.append(user_id)
            cur.execute(query, tuple(params))
            result = cur.fetchone()

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info("db.query.complete", query="get_delivery_by_order", order_id=order_id, elapsed_ms=elapsed_ms, found=result is not None)
            return _convert_decimals(result)

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error("db.query.error", query="get_delivery_by_order", order_id=order_id, error=str(e), elapsed_ms=elapsed_ms)
        raise


def get_refunds_by_order(order_id: str, user_id: Optional[str] = None) -> List[Dict]:
    start = time.time()
    logger.info("db.query.start", query="get_refunds_by_order", order_id=order_id)

    try:
        with get_db_cursor() as cur:
            query = "SELECT refund_id, order_id, user_id, amount_aed, reason, status, processed_at FROM refunds WHERE order_id = %s"
            params = [order_id]
            if user_id:
                query += " AND user_id = %s"
                params.append(user_id)
            cur.execute(query, tuple(params))
            results = cur.fetchall()

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info("db.query.complete", query="get_refunds_by_order", order_id=order_id, elapsed_ms=elapsed_ms, count=len(results))
            return _convert_decimals(results)

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error("db.query.error", query="get_refunds_by_order", order_id=order_id, error=str(e), elapsed_ms=elapsed_ms)
        raise


def get_warranty_by_order(order_id: str, user_id: str, product_id: Optional[str] = None) -> Optional[Dict]:
    start = time.time()
    logger.info("db.query.start", query="get_warranty_by_order", order_id=order_id, product_id=product_id)

    try:
        with get_db_cursor() as cur:
            query = "SELECT warranty_id, order_id, user_id, product_id, warranty_type, start_date, end_date, status, claim_count, last_claim_at FROM warranties WHERE order_id = %s AND user_id = %s"
            params = [order_id, user_id]
            if product_id:
                query += " AND product_id = %s"
                params.append(product_id)
            cur.execute(query, tuple(params))
            result = cur.fetchone()

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info("db.query.complete", query="get_warranty_by_order", order_id=order_id, elapsed_ms=elapsed_ms, found=result is not None)
            return _convert_decimals(result)

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error("db.query.error", query="get_warranty_by_order", order_id=order_id, error=str(e), elapsed_ms=elapsed_ms)
        raise


def get_payment_by_order(order_id: str, user_id: Optional[str] = None) -> List[Dict]:
    start = time.time()
    logger.info("db.query.start", query="get_payment_by_order", order_id=order_id)

    try:
        with get_db_cursor() as cur:
            query = "SELECT payment_id, order_id, user_id, amount_aed, method, status, paid_at FROM payments WHERE order_id = %s"
            params = [order_id]
            if user_id:
                query += " AND user_id = %s"
                params.append(user_id)
            cur.execute(query, tuple(params))
            results = cur.fetchall()

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info("db.query.complete", query="get_payment_by_order", order_id=order_id, elapsed_ms=elapsed_ms, count=len(results))
            return _convert_decimals(results)

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error("db.query.error", query="get_payment_by_order", order_id=order_id, error=str(e), elapsed_ms=elapsed_ms)
        raise


def get_product_by_id(product_id: str) -> Optional[Dict]:
    start = time.time()
    logger.info("db.query.start", query="get_product_by_id", product_id=product_id)

    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT product_id, name_en, name_ar, category, subcategory, brand, price_aed, warranty_months, in_stock FROM products WHERE product_id = %s",
                (product_id,)
            )
            result = cur.fetchone()

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info("db.query.complete", query="get_product_by_id", product_id=product_id, elapsed_ms=elapsed_ms, found=result is not None)
            return _convert_decimals(result)

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error("db.query.error", query="get_product_by_id", product_id=product_id, error=str(e), elapsed_ms=elapsed_ms)
        raise


def search_products(query_text: str, limit: int = 5) -> List[Dict]:
    start = time.time()
    logger.info("db.query.start", query="search_products", query_text=query_text[:50], limit=limit)

    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT product_id, name_en, category, brand, price_aed, in_stock FROM products WHERE name_en ILIKE %s OR category ILIKE %s OR brand ILIKE %s LIMIT %s",
                (f"%{query_text}%", f"%{query_text}%", f"%{query_text}%", limit)
            )
            results = cur.fetchall()

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info("db.query.complete", query="search_products", query_text=query_text[:50], elapsed_ms=elapsed_ms, count=len(results))
            return _convert_decimals(results)

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error("db.query.error", query="search_products", query_text=query_text[:50], error=str(e), elapsed_ms=elapsed_ms)
        raise
