"""Episode store: write + retrieve conversation history"""
from typing import Optional, List, Dict, Any
import json
from datetime import datetime


class EpisodeStore:
    """Store and retrieve conversation episodes"""

    def __init__(self, db_pool=None):
        self.pool = db_pool
        self._episodes: Dict[str, List[Dict]] = {}  # In-memory for now

    async def write_episode(
        self,
        conversation_id: str,
        user_id: str,
        messages: List[Dict[str, str]],
        summary: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """Write a conversation episode"""
        episode = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "messages": messages,
            "summary": summary,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat()
        }

        # Store in memory (would be Postgres in production)
        if conversation_id not in self._episodes:
            self._episodes[conversation_id] = []

        self._episodes[conversation_id].append(episode)

    async def retrieve_episodes(
        self,
        user_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve recent episodes for a user"""
        # Filter and sort by most recent
        user_episodes = []
        for conv_id, episodes in self._episodes.items():
            for ep in episodes:
                if ep["user_id"] == user_id:
                    user_episodes.append(ep)

        # Sort by created_at descending
        user_episodes.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )

        return user_episodes[:limit]

    async def get_context(self, user_id: str) -> Optional[Dict]:
        """Get episodic context for a user session"""
        recent = await self.retrieve_episodes(user_id, limit=1)
        if recent:
            return {
                "previous_conversations": len(recent),
                "last_summary": recent[0].get("summary"),
                "recent_intents": []  # Would extract from episodes
            }
        return None


# Singleton
_episode_store = None


def get_episode_store() -> EpisodeStore:
    """Get or create the episode store"""
    global _episode_store
    if _episode_store is None:
        _episode_store = EpisodeStore()
    return _episode_store