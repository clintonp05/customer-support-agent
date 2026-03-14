"""Conversation summarization for storage"""
from typing import List, Dict


class ConversationSummarizer:
    """Summarizes conversations for efficient storage"""

    def __init__(self):
        pass

    async def summarize(self, messages: List[Dict[str, str]]) -> str:
        """
        Summarize conversation messages

        In production, this would use an LLM to generate summaries
        """
        if not messages:
            return "Empty conversation"

        # Simple extractive summarization
        user_messages = [
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == "user"
        ]

        if not user_messages:
            return "No user messages"

        # Take first and last few
        if len(user_messages) <= 3:
            full = " | ".join(user_messages)
        else:
            first = user_messages[0]
            last = user_messages[-1]
            full = f"{first[:50]}... {last[:50]}"

        # Simple truncation
        if len(full) > 200:
            full = full[:200] + "..."

        return f"User queries: {full}"

    def extract_intent_history(self, messages: List[Dict[str, str]]) -> List[str]:
        """Extract intent history from messages"""
        # Would extract from message metadata in production
        return []


# Singleton
_summarizer = None


def get_summarizer() -> ConversationSummarizer:
    """Get or create the summarizer"""
    global _summarizer
    if _summarizer is None:
        _summarizer = ConversationSummarizer()
    return _summarizer