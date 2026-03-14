"""Evaluation metrics calculations"""
from typing import List, Dict, Any
from src.config import settings


class EvalMetrics:
    """Evaluation metrics aggregator"""

    def __init__(self, results: List[Dict[str, Any]]):
        self.results = results

        if results:
            self.tool_selection_accuracy = sum(r.get("tool_correct", False) for r in results) / len(results)
            self.param_accuracy = sum(r.get("params_correct", False) for r in results) / len(results)
            self.goal_success_rate = sum(r.get("goal_achieved", False) for r in results) / len(results)
            self.hallucination_rate = sum(r.get("hallucinated", False) for r in results) / len(results)
        else:
            self.tool_selection_accuracy = 0.0
            self.param_accuracy = 0.0
            self.goal_success_rate = 0.0
            self.hallucination_rate = 0.0

    def passes_gates(self) -> bool:
        """Check if metrics pass the evaluation gates"""
        return (
            self.tool_selection_accuracy >= settings.eval_tool_accuracy_min and
            self.param_accuracy >= settings.eval_param_accuracy_min and
            self.goal_success_rate >= settings.eval_goal_success_min and
            self.hallucination_rate <= settings.eval_hallucination_max
        )

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            "tool_selection_accuracy": self.tool_selection_accuracy,
            "param_accuracy": self.param_accuracy,
            "goal_success_rate": self.goal_success_rate,
            "hallucination_rate": self.hallucination_rate,
            "passes_gates": self.passes_gates()
        }

    @classmethod
    def aggregate(cls, results: List[Dict[str, Any]]) -> "EvalMetrics":
        """Aggregate results into metrics"""
        return cls(results)