"""Golden dataset test runner.

Usage:
    python scripts/run_golden_dataset.py [dataset_path] [api_url]

Defaults:
    dataset_path = data/golden_dataset.jsonl
    api_url      = http://127.0.0.1:4500/support
"""
import json
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from collections import defaultdict


API_URL = "http://127.0.0.1:4500/support"
HEADERS_BASE = {
    "x-channel-id": "golden",
    "Content-Type": "application/json",
}


def call_api(payload: Dict[str, Any], req_id: str, url: str, timeout_s: int = 60) -> Dict[str, Any]:
    headers = {**HEADERS_BASE, "x-request-id": req_id}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "body": json.loads(body)}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return {"ok": False, "status": exc.code, "error": body}
    except Exception as exc:
        return {"ok": False, "status": None, "error": str(exc)}


def check_keywords(response: str, keywords: List[str]) -> List[str]:
    """Return keywords missing from the response (case-insensitive)."""
    missing = [kw for kw in keywords if kw.lower() not in response.lower()]
    return missing


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def green(t: str) -> str: return color(t, "32")
def red(t: str) -> str:   return color(t, "31")
def yellow(t: str) -> str: return color(t, "33")
def bold(t: str) -> str:  return color(t, "1")


def main(path: str, url: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    # Group by scenario
    scenarios: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        scenarios[row["scenario_id"]].append(row)

    total_turns = 0
    passed_turns = 0
    failed_turns = 0
    issues: List[str] = []

    for sid, turns in sorted(scenarios.items()):
        turns.sort(key=lambda r: r["turn"])
        name = turns[0].get("scenario_name", sid)
        print(bold(f"\n{'='*60}"))
        print(bold(f"Scenario {sid}: {name}  ({len(turns)} turns)"))
        print(bold(f"{'='*60}"))

        for turn in turns:
            total_turns += 1
            turn_num = turn["turn"]
            expected_intent = turn.get("expected_intent", "")
            expected_keywords = turn.get("expected_keywords", [])

            # Build API payload (strip golden-specific fields)
            payload = {
                "conversation_id": turn["conversation_id"],
                "user_id": turn["user_id"],
                "session_id": turn["session_id"],
                "message": turn["message"],
                "messages": turn.get("messages", []),
                "execution_budget_ms": turn.get("execution_budget_ms", 8000),
            }
            if turn.get("order_id"):
                payload["order_id"] = turn["order_id"]
            if turn.get("product_id"):
                payload["product_id"] = turn["product_id"]

            req_id = f"golden-{sid}-t{turn_num}-{int(time.time())}"
            print(f"\n  Turn {turn_num}/{turn['total_turns']}")
            print(f"  User : {turn['message'][:120]}")

            t0 = time.perf_counter()
            result = call_api(payload, req_id, url)
            elapsed = (time.perf_counter() - t0) * 1000

            if not result["ok"]:
                failed_turns += 1
                msg = f"  {red('FAIL')} HTTP {result['status']}: {result.get('error','')[:200]}"
                print(msg)
                issues.append(f"[{sid} T{turn_num}] API error: {result.get('error','')[:120]}")
                continue

            body = result["body"]
            final_response = body.get("final_response", "")
            response_source = body.get("response_source", "unknown")
            tool_results = body.get("tool_results", {})
            timings = body.get("timings_ms", {})
            next_node = body.get("next_node", "")

            # --- Checks ---
            turn_ok = True

            # 1. Check for non-empty response
            if not final_response.strip():
                issues.append(f"[{sid} T{turn_num}] Empty final_response")
                turn_ok = False

            # 2. Check for dollar sign ($) in response - should use AED
            if "$" in final_response:
                issues.append(f"[{sid} T{turn_num}] Response contains '$' — should use AED")
                turn_ok = False

            # 3. Check expected keywords
            missing_kw = check_keywords(final_response, expected_keywords)
            if missing_kw:
                issues.append(f"[{sid} T{turn_num}] Missing expected keywords in response: {missing_kw}")
                turn_ok = False

            # 4. Check tool success for tool-dependent intents
            tool_errors = {
                name: res
                for name, res in tool_results.items()
                if isinstance(res, dict) and res.get("success") is False
            }
            if tool_errors:
                issues.append(f"[{sid} T{turn_num}] Tool failures: {list(tool_errors.keys())}")

            # 5. Flag escalation if not expected
            if body.get("escalation_required") and expected_intent not in ("general_inquiry", "speak_to_human"):
                issues.append(f"[{sid} T{turn_num}] Unexpected escalation (intent={expected_intent})")

            status_icon = green("PASS") if turn_ok else red("FAIL")
            if turn_ok:
                passed_turns += 1
            else:
                failed_turns += 1

            print(f"  Agent: {final_response[:160]}")
            print(f"  [{status_icon}] source={response_source}  next_node={next_node}  elapsed={elapsed:.0f}ms")
            print(f"  Tools: {list(tool_results.keys()) or 'none'}")
            if tool_errors:
                print(f"  {yellow('Tool errors:')} {tool_errors}")
            if missing_kw:
                print(f"  {yellow('Missing keywords:')} {missing_kw}")
            if expected_keywords:
                print(f"  Expected keywords: {expected_keywords}")

    # --- Summary ---
    print(bold(f"\n{'='*60}"))
    print(bold("SUMMARY"))
    print(bold(f"{'='*60}"))
    print(f"Total turns : {total_turns}")
    print(f"Passed      : {green(str(passed_turns))}")
    print(f"Failed      : {red(str(failed_turns))}")

    if issues:
        print(bold(f"\n{yellow('ISSUES FOUND:')}"))
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print(green("\nAll checks passed!"))

    return 0 if failed_turns == 0 else 1


if __name__ == "__main__":
    dataset_path = sys.argv[1] if len(sys.argv) > 1 else "data/golden_dataset.jsonl"
    api_url = sys.argv[2] if len(sys.argv) > 2 else API_URL
    sys.exit(main(dataset_path, api_url))
