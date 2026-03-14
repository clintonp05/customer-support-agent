"""Multi-intent detection with sentence chunking and DAG"""
from typing import List, Tuple
import re


def split_into_intents(query: str) -> List[str]:
    """
    Split a query into potential multiple intents

    Uses sentence boundary detection and conjunction splitting
    """
    # Split on sentence boundaries
    segments = re.split(r'[.!?]+', query)
    segments = [s.strip() for s in segments if s.strip()]

    # Further split on conjunctions for multiple intents
    intents = []
    for segment in segments:
        # Split on common conjunction patterns
        sub_parts = re.split(r'\s+(?:and|also|plus|additionally)\s+', segment, flags=re.IGNORECASE)
        intents.extend([s.strip() for s in sub_parts if s.strip()])

    return intents


def build_intent_dag(intents: List[str]) -> dict:
    """
    Build a DAG for multiple intents with dependencies

    Returns:
        Dict representing the intent execution graph
    """
    dag = {
        "nodes": [],
        "edges": [],
        "parallel_groups": []
    }

    for i, intent in enumerate(intents):
        dag["nodes"].append({
            "id": f"intent_{i}",
            "intent": intent,
            "dependencies": []
        })

    return dag


def detect_parallel_intents(query: str) -> Tuple[List[str], bool]:
    """
    Detect if query contains multiple parallel intents

    Returns:
        Tuple of (intent_list, is_parallel)
    """
    # Check for parallel intent markers
    parallel_markers = [
        r'\s+and\s+',
        r'\s+also\s+',
        r'\s+plus\s+',
        r',\s+and\s+',
    ]

    is_parallel = any(re.search(marker, query, re.IGNORECASE) for marker in parallel_markers)

    if is_parallel:
        intents = split_into_intents(query)
        return intents, True

    return [query], False