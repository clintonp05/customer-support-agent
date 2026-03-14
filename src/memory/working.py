"""LangGraph checkpointer using PostgresSaver"""
from typing import Optional, Dict, Any
import uuid
import traceback

from src.config import settings

try:
    from langgraph.checkpoint.postgres import PostgresSaver
except ImportError:
    PostgresSaver = None


class PostgresCheckpointer:
    """Postgres-backed checkpointer for LangGraph"""

    def __init__(self, database_url: Optional[str] = None):
        if PostgresSaver is None:
            raise RuntimeError("langgraph-checkpoint-postgres is required for checkpointer")

        self.database_url = database_url or settings.database_url
        self.saver = None
        self._init_saver()

    def _init_saver(self):
        try:
            # PostgresSaver accepts a DB connection object
            import psycopg2
            conn = psycopg2.connect(self.database_url)
            self.saver = PostgresSaver(conn)
        except Exception:
            traceback.print_exc()
            self.saver = None

    async def get(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Dict]:
        """Get checkpoint from Postgres"""
        if not self.saver:
            return None

        try:
            if checkpoint_id:
                # PostgresSaver may support get with checkpoint id
                return self.saver.get(thread_id, checkpoint_id)
            checkpoint = self.saver.get(thread_id)
            return checkpoint
        except Exception:
            traceback.print_exc()
            return None

    async def put(self, thread_id: str, checkpoint_id: str, checkpoint_data: Dict[str, Any]):
        """Save checkpoint to Postgres"""
        if not self.saver:
            return

        try:
            self.saver.put(thread_id, checkpoint_id, checkpoint_data)
        except Exception:
            traceback.print_exc()


# Singleton
_checkpointer = None


def get_checkpointer() -> PostgresCheckpointer:
    """Get or create the checkpointer"""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = PostgresCheckpointer()
    return _checkpointer