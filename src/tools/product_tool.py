from src.tools.base import BaseTool
from src.db.queries import get_product_by_id, search_products
from typing import Dict, Any


class ProductTool(BaseTool):
    """Product lookup tool."""

    def __init__(self):
        super().__init__(name="get_product_info")

    async def _call(self, params: dict, state: dict) -> dict:
        product_id = params.get("product_id")
        query = params.get("query")

        if product_id:
            product = get_product_by_id(product_id)
            if product:
                return {"success": True, "product": product}
            return {"success": False, "error": "PRODUCT_NOT_FOUND", "message": f"Product {product_id} not found"}

        if query:
            products = search_products(query_text=query)
            return {"success": True, "products": products}

        return {"success": False, "error": "MISSING_PARAMS", "message": "product_id or query is required"}
