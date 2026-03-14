"""Intent recognition and classification"""

from src.intent.registry import INTENT_REGISTRY, SUPPORT_STATUS
from src.intent.classifier import IntentClassifier, get_classifier
from src.intent.vector_index import IntentVectorIndex, get_vector_index
from src.intent.multi_intent import split_into_intents, detect_parallel_intents, build_intent_dag
from src.intent.supported_check import check_intent_support, is_intent_supported

__all__ = [
    "INTENT_REGISTRY",
    "SUPPORT_STATUS",
    "IntentClassifier",
    "get_classifier",
    "IntentVectorIndex",
    "get_vector_index",
    "split_into_intents",
    "detect_parallel_intents",
    "build_intent_dag",
    "check_intent_support",
    "is_intent_supported",
]