"""Cost tracking from token usage to cost per ticket"""
from typing import Dict, Optional
from src.config import settings

# Price per 1M tokens (approximate)
TOKEN_PRICES = {
    "claude-sonnet-4-20250514": {
        "input": 3.00,   # $3 per 1M input tokens
        "output": 15.00, # $15 per 1M output tokens
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.20,   # $0.20 per 1M input tokens
        "output": 1.00,  # $1 per 1M output tokens
    },
}


class CostTracker:
    """Track cost per conversation and ticket"""

    def __init__(self):
        self.conversation_costs: Dict[str, float] = {}

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for token usage"""
        prices = TOKEN_PRICES.get(model, TOKEN_PRICES["claude-sonnet-4-20250514"])

        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]

        return input_cost + output_cost

    def track_conversation(self, conversation_id: str, cost: float):
        """Track cost for a conversation"""
        self.conversation_costs[conversation_id] = cost

    def get_conversation_cost(self, conversation_id: str) -> float:
        """Get cost for a specific conversation"""
        return self.conversation_costs.get(conversation_id, 0.0)

    def get_average_cost(self) -> float:
        """Get average cost per conversation"""
        if not self.conversation_costs:
            return 0.0
        return sum(self.conversation_costs.values()) / len(self.conversation_costs)

    def is_within_budget(self, cost: float) -> bool:
        """Check if cost is within budget"""
        return cost <= settings.target_cost_per_ticket_usd


# Singleton
_cost_tracker = None


def get_cost_tracker() -> CostTracker:
    """Get or create the cost tracker"""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker