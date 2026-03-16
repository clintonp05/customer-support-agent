"""Multi-intent detection with sentence chunking and DAG.

Splitting strategy (in order):
  1. Sentence boundaries (. ! ?)
  2. Coordinating conjunctions: "and", "also", "plus", "additionally"
  3. Implicit topic-shift markers: "what about", "how about", "regarding"

A segment must be >= MIN_SEGMENT_WORDS words to be kept — this filters
fragments like "and a warranty" that appear after splitting on "and".
"""
from typing import List, Tuple
import re

# Minimum meaningful segment length (words)
_MIN_SEGMENT_WORDS = 3

# Patterns that signal a topic shift without a sentence boundary
_TOPIC_SHIFT_RE = re.compile(
    r'\s+(?:and|also|plus|additionally|,\s*and)\s+(?=\w)',
    re.IGNORECASE,
)

# Further split on "what about X", "how about X", "regarding X"
_SHIFT_PHRASE_RE = re.compile(
    r'\s+(?:what about|how about|regarding|concerning)\s+',
    re.IGNORECASE,
)


def split_into_intents(query: str) -> List[str]:
    """Split a query into one or more intent segments.

    Returns a list with at least one element (the original query if
    no multi-intent signals are found or all sub-parts are too short).

    Examples:
        "what is the refund policy and warranty for electronics"
        → ["what is the refund policy", "warranty for electronics"]

        "where is my order? I also want a refund"
        → ["where is my order", "I also want a refund"]
    """
    # 1. Split on sentence boundaries
    sentences = re.split(r'[.!?]+', query)
    sentences = [s.strip() for s in sentences if s.strip()]

    segments: List[str] = []
    for sentence in sentences:
        # 2. Split on coordinating conjunctions
        parts = _TOPIC_SHIFT_RE.split(sentence)
        # 3. Within each part, split on topic-shift phrases
        refined: List[str] = []
        for part in parts:
            sub = _SHIFT_PHRASE_RE.split(part)
            refined.extend(sub)
        segments.extend([s.strip() for s in refined if s.strip()])

    # Filter segments that are too short to carry a standalone intent
    meaningful = [s for s in segments if len(s.split()) >= _MIN_SEGMENT_WORDS]

    # If filtering removed everything, return the full query
    return meaningful if len(meaningful) >= 2 else [query]


def detect_parallel_intents(query: str) -> Tuple[List[str], bool]:
    """Return (segments, is_multi_intent).

    Uses split_into_intents() and treats any result with >= 2 segments
    as parallel multi-intent (no char_count gate — that was the bug).
    """
    segments = split_into_intents(query)
    is_parallel = len(segments) > 1
    return segments, is_parallel


def build_intent_dag(intents: List[str]) -> dict:
    """Build a simple dependency-free DAG for parallel intent execution."""
    nodes = [{"id": f"intent_{i}", "intent": intent, "dependencies": []}
             for i, intent in enumerate(intents)]
    return {"nodes": nodes, "edges": [], "parallel_groups": [nodes]}
