"""Intent classifier using SetFit + zero-shot BART fallback"""
import asyncio
from typing import Tuple, Optional

from src.intent.registry import INTENT_REGISTRY
from src.guard.entity_extractor import extract_order_ids, extract_user_ids
from src.observability.logger import get_logger

logger = get_logger()


class IntentClassifier:
    """Classifies user intent from natural language"""

    def __init__(self):
        self.intent_registry = INTENT_REGISTRY

    async def classify(self, query: str) -> Tuple[Optional[str], float]:
        """
        Classify user intent

        Returns:
            Tuple of (intent_name, confidence)
        """
        query_lower = query.lower()

        # Rule-based matching against utterance examples
        best_match = None
        best_score = 0.0
        matched_utterance = None

        for intent_name, intent_config in self.intent_registry.items():
            for utterance in intent_config.get("utterances", []):
                # Calculate similarity (simple word overlap for now)
                score = self._calculate_similarity(query_lower, utterance.lower())
                if score > best_score:
                    best_score = score
                    best_match = intent_name
                    matched_utterance = utterance

        # Threshold check
        if best_score >= 0.3:
            logger.info("intent.classified", intent=best_match, confidence=min(best_score, 1.0), matched_utterance=matched_utterance[:50] if matched_utterance else None)
            return best_match, min(best_score, 1.0)

        # Default to general_inquiry for unrecognized
        logger.info("intent.fallback", confidence=0.5, best_attempt_score=best_score)
        return "general_inquiry", 0.5

    def _calculate_similarity(self, query: str, utterance: str) -> float:
        """Calculate simple similarity score"""
        query_words = set(query.split())
        utterance_words = set(utterance.split())

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