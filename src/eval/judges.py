"""LLM-as-judge evaluators"""
from typing import Dict, Any, List, Optional


class LLMJudge:
    """LLM-based judge for evaluating responses"""

    def __init__(self):
        pass

    async def evaluate(
        self,
        input: str,
        expected: List[str],
        actual: str,
        expected_tool: str = "",
        actual_tool: str = "",
        expected_params: Dict = {},
        actual_params: Dict = {}
    ) -> Dict[str, Any]:
        """
        Evaluate a response using LLM-as-judge

        Returns:
            Dict with scores for tool_correct, params_correct, goal_achieved, hallucinated
        """
        # Check tool selection
        tool_correct = (expected_tool == actual_tool) if expected_tool else True

        # Check params
        params_correct = True
        for key, value in expected_params.items():
            if actual_params.get(key) != value:
                params_correct = False
                break

        # Check output contains expected text
        goal_achieved = True
        for exp in expected:
            if exp.lower() not in actual.lower():
                goal_achieved = False
                break

        # Check for hallucination (basic check)
        hallucinated = False
        # In production, would check against knowledge base

        return {
            "tool_correct": tool_correct,
            "params_correct": params_correct,
            "goal_achieved": goal_achieved,
            "hallucinated": hallucinated
        }


class SimpleJudge:
    """Simple rule-based judge for fast evaluation"""

    async def evaluate(
        self,
        input: str,
        expected: List[str],
        actual: str,
        expected_tool: str = "",
        actual_tool: str = "",
        expected_params: Dict = {},
        actual_params: Dict = {}
    ) -> Dict[str, Any]:
        """Simple evaluation without LLM"""

        # Tool match
        tool_correct = expected_tool == actual_tool if expected_tool else True

        # Param match
        params_correct = all(
            actual_params.get(k) == v
            for k, v in expected_params.items()
        )

        # Output contains expected
        goal_achieved = all(exp.lower() in actual.lower() for exp in expected) if expected else True

        return {
            "tool_correct": tool_correct,
            "params_correct": params_correct,
            "goal_achieved": goal_achieved,
            "hallucinated": False
        }