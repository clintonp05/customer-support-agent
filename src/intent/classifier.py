"""Intent classifier using utterance overlap + conversation history context"""
import asyncio
import re
from typing import Dict, List, Optional, Tuple

from src.intent.registry import INTENT_REGISTRY
from src.guard.entity_extractor import extract_order_ids, extract_user_ids
from src.observability.logger import get_logger

logger = get_logger()

# How many previous turns to include in classification context
_HISTORY_TURNS = 2


class IntentClassifier:
    """Classifies user intent from natural language, optionally using conversation history."""

    def __init__(self):
        self.intent_registry = INTENT_REGISTRY

    # Confidence threshold above which history is not needed
    _HISTORY_FALLBACK_THRESHOLD = 0.5

    async def classify(
        self,
        query: str,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[Optional[str], float]:
        """
        Classify user intent.

        Classification strategy:
          1. Classify the current query alone (no history).
          2. If confidence >= _HISTORY_FALLBACK_THRESHOLD, return immediately —
             the query is self-contained and history would only introduce noise.
          3. Only if confidence is low (ambiguous follow-up like "My order is N-xxx")
             do we retry with history appended to disambiguate.

        Args:
            query: The current user message.
            messages: Full conversation history (role/content dicts). When provided,
                      history is used as a fallback only when current-query confidence
                      is below the threshold.

        Returns:
            Tuple of (intent_name, confidence)
        """
        # --- Pass 1: classify current query alone ---
        best_match, best_score, matched_utterance = self._score_text(query.lower())

        used_history = False
        if best_score < self._HISTORY_FALLBACK_THRESHOLD and messages:
            # --- Pass 2: low confidence — retry with history context ---
            enriched = self._build_classification_text(query, messages)
            h_match, h_score, h_utterance = self._score_text(enriched.lower())
            if h_score > best_score:
                best_match, best_score, matched_utterance = h_match, h_score, h_utterance
                used_history = True

        # Entity-based override: if classifier is uncertain and the query contains
        # an order ID pattern, it almost certainly is an order-related intent.
        # Prevents "check this one N-20260314-XYZ" being misclassified as product_inquiry.
        _ORDER_RELATED = {"order_status", "delivery_tracking", "refund_request", "cancel_order"}
        if best_score < self._HISTORY_FALLBACK_THRESHOLD and best_match not in _ORDER_RELATED:
            if extract_order_ids(query):
                best_match = "order_status"
                best_score = 0.5
                matched_utterance = "(order_id detected in query)"
                used_history = False

        # Threshold check
        if best_score >= 0.3:
            logger.info(
                "intent.classified",
                intent=best_match,
                confidence=min(best_score, 1.0),
                matched_utterance=matched_utterance[:50] if matched_utterance else None,
                used_history=used_history,
            )
            return best_match, min(best_score, 1.0)

        # Default to general_inquiry for unrecognized
        logger.info("intent.fallback", confidence=0.5, best_attempt_score=best_score)
        return "general_inquiry", 0.5

    def _score_text(self, text_lower: str) -> Tuple[Optional[str], float, Optional[str]]:
        """Score all utterances against a pre-lowercased text string."""
        best_match = None
        best_score = 0.0
        matched_utterance = None
        for intent_name, intent_config in self.intent_registry.items():
            for utterance in intent_config.get("utterances", []):
                score = self._calculate_similarity(text_lower, utterance.lower())
                if score > best_score:
                    best_score = score
                    best_match = intent_name
                    matched_utterance = utterance
        return best_match, best_score, matched_utterance

    def _build_classification_text(
        self, query: str, messages: Optional[List[Dict[str, str]]]
    ) -> str:
        """Combine current query with recent user turns for richer classification."""
        if not messages:
            return query

        # Collect last _HISTORY_TURNS user messages (excluding the current query)
        user_turns = [
            m.get("content", "")
            for m in messages
            if m.get("role") == "user" and m.get("content", "").strip()
        ]
        recent_context = " ".join(user_turns[-_HISTORY_TURNS:])
        if recent_context:
            return f"{recent_context} {query}"
        return query

    @staticmethod
    def _tokenize(text: str) -> set:
        """Tokenize text: lowercase, strip punctuation, split on whitespace."""
        return set(re.sub(r"[^\w\s]", " ", text).split())

    def _calculate_similarity(self, query: str, utterance: str) -> float:
        """Word-overlap similarity: |intersection| / |utterance_words|."""
        query_words = self._tokenize(query)
        utterance_words = self._tokenize(utterance)

        if not utterance_words:
            return 0.0

        intersection = query_words & utterance_words
        return len(intersection) / len(utterance_words)


# Singleton instance
_classifier = None


def get_classifier() -> IntentClassifier:
    """Get or create the classifier instance"""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier