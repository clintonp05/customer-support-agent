"""Emotion and intent-signal detection for customer messages.

Detects tone (frustrated/angry), churn signals, repeat-complaint signals,
and high-value item mentions — without crossing into toxicity detection
(that stays in toxicity.py).

Results are stored in state["emotion"] and influence:
 - escalation authority (repeat issue + churn → auto-escalate)
 - response template (empathetic vs. standard)
 - human-agent packet (churn risk, recommended action)
"""
import re
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# Signal word lists
# ---------------------------------------------------------------------------
_CHURN_PHRASES = [
    "never ordering", "never order", "never shopping", "never shop",
    "never buying", "never buy", "never using", "never use",
    "switching to", "switch to", "going to amazon", "going to namshi",
    "cancel my account", "delete my account", "close my account",
    "done with noon", "done with you", "last time i",
    "last order from", "fed up", "had enough",
    "goodbye forever", "leaving noon",
]

_REPEAT_PHRASES = [
    "second time", "2nd time", "third time", "3rd time",
    "again", "same issue", "same problem", "still not",
    "still haven't", "still waiting", "happened before",
    "last time this", "this keeps happening", "always happens",
    "not the first", "another time",
]

_FRUSTRATED_PHRASES = [
    "frustrated", "annoyed", "upset", "disappointed", "unacceptable",
    "ridiculous", "terrible", "awful", "horrible", "disgusting",
    "waste of time", "worst service", "no one helps",
    "i've been waiting", "still no response", "hours ago",
    "days ago", "weeks ago",
]

_ANGRY_PHRASES = [
    "very angry", "extremely angry", "furious", "livid",
    "i demand", "i insist", "i require", "this is outrageous",
    "completely unacceptable", "absolutely disgusting",
    "worst ever", "sue you", "legal action",
]

# High-value items where "delivered but not received" is above bot's authority
_HIGH_VALUE_ITEMS = [
    "playstation", "ps5", "ps4", "xbox", "nintendo switch",
    "iphone", "ipad", "macbook", "apple watch", "airpods",
    "samsung galaxy", "samsung phone", "pixel", "oneplus",
    "laptop", "notebook", "tablet", "gaming console",
    "television", "tv", "smart tv", "oled", "qled",
    "camera", "dslr", "mirrorless",
    "gold", "jewellery", "jewelry", "diamond", "watch",
    "rolex", "omega", "gucci", "louis vuitton",
    "dyson", "vacuum",
]

_HIGH_VALUE_PRICE_THRESHOLD_AED = 500.0


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------
def detect_emotion(text: str) -> Dict[str, Any]:
    """Analyse customer message for emotional signals.

    Returns a dict with:
        tone: "normal" | "frustrated" | "angry"
        churn_signal: bool — customer threatens to leave / stop ordering
        repeat_complaint: bool — explicitly states this happened before
        high_value_item_mentioned: Optional[str] — item name if detected
        delivery_dispute: bool — "says delivered / marked delivered but didn't receive"
        escalation_weight: int — 0–4 score (sum of signal flags)
    """
    lower = text.lower()

    # Tone
    tone = "normal"
    if any(phrase in lower for phrase in _ANGRY_PHRASES):
        tone = "angry"
    elif any(phrase in lower for phrase in _FRUSTRATED_PHRASES):
        tone = "frustrated"
    # Softer tone indicators
    if tone == "normal":
        if "!" in text and any(w in lower for w in ["not", "wrong", "issue", "problem", "bad"]):
            tone = "frustrated"

    # Churn signal
    churn_signal = any(phrase in lower for phrase in _CHURN_PHRASES)

    # Repeat complaint
    repeat_complaint = any(phrase in lower for phrase in _REPEAT_PHRASES)

    # High-value item mentioned
    high_value_item: Optional[str] = None
    for item in _HIGH_VALUE_ITEMS:
        if item in lower:
            high_value_item = item
            break

    # Delivery dispute: "says delivered / marked as delivered / shows delivered" + denial
    delivery_dispute = bool(
        re.search(r"(says|marked|shows|status)\s+(as\s+)?deliver", lower)
        and re.search(r"(don.t|didn.t|haven.t|not)\s+(have|receive|get|arrived|come)", lower)
    )

    # Escalation weight: sum of risk signals
    weight = sum([
        tone in ("frustrated", "angry"),
        churn_signal,
        repeat_complaint,
        high_value_item is not None,
        delivery_dispute,
    ])

    return {
        "tone": tone,
        "churn_signal": churn_signal,
        "repeat_complaint": repeat_complaint,
        "high_value_item_mentioned": high_value_item,
        "delivery_dispute": delivery_dispute,
        "escalation_weight": weight,
    }


def is_high_value_order(order: Dict[str, Any]) -> bool:
    """Return True if the order total exceeds the high-value threshold."""
    total = order.get("total_aed") or 0
    try:
        return float(total) >= _HIGH_VALUE_PRICE_THRESHOLD_AED
    except (TypeError, ValueError):
        return False
