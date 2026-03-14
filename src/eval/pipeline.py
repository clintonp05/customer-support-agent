"""Evaluation pipeline runner"""
import json
from pathlib import Path
from typing import List, Dict, Any
from src.eval.judges import LLMJudge
from src.eval.metrics import EvalMetrics
from src.agent.graph import process_conversation


GOLDEN_SET_DIR = Path("src/eval/golden_sets")


class EvalPipeline:
    """Run evaluation against golden sets"""

    def __init__(self, judge: LLMJudge = None):
        self.judge = judge or LLMJudge()

    async def run(self, golden_set_name: str) -> EvalMetrics:
        """Run evaluation on a golden set"""
        golden_file = GOLDEN_SET_DIR / f"{golden_set_name}.json"

        if not golden_file.exists():
            raise FileNotFoundError(f"Golden set not found: {golden_set_name}")

        cases = json.loads(golden_file.read_text())
        results = []

        for case in cases:
            result = await self._evaluate_case(case)
            results.append(result)

        return EvalMetrics.aggregate(results)

    async def _evaluate_case(self, case: Dict) -> Dict[str, Any]:
        """Evaluate a single test case"""
        user_id = case.get("user_id", "USR-TEST0001")
        conversation = case.get("conversation", [])
        expected_intent = case.get("expected_intent", "")
        expected_tool = case.get("expected_tool", "")
        expected_params = case.get("expected_params", {})
        expected_output = case.get("expected_output_contains", [])

        # Get the last user message
        user_message = ""
        messages = []
        for msg in conversation:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            if msg.get("role") == "user":
                user_message = msg.get("content", "")

        # Run through agent
        result = await process_conversation(
            conversation_id=f"eval_{case.get('id', 'unknown')}",
            user_id=user_id,
            session_id="eval_session",
            message=user_message,
            messages=messages[:-1] if messages else []
        )

        actual_response = result.get("final_response", "")
        actual_intent = result.get("primary_intent", "")
        actual_tool = result.get("tools_executed", [""])[0] if result.get("tools_executed") else ""
        actual_params = result.get("extracted_params", {})

        # Judge evaluation
        scores = await self.judge.evaluate(
            input=user_message,
            expected=expected_output,
            actual=actual_response,
            expected_tool=expected_tool,
            actual_tool=actual_tool,
            expected_params=expected_params,
            actual_params=actual_params
        )

        return scores


async def run_all_evals() -> Dict[str, EvalMetrics]:
    """Run all golden set evaluations"""
    pipeline = EvalPipeline()
    results = {}

    for golden_file in GOLDEN_SET_DIR.glob("*.json"):
        name = golden_file.stem
        try:
            metrics = await pipeline.run(name)
            results[name] = metrics
        except Exception as e:
            print(f"Error running eval {name}: {e}")

    return results