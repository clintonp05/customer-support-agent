"""Persist conversation turns to Postgres."""
import json
from typing import Any, Dict, List, Optional

from src.db.connector import get_db_cursor
from src.observability.logger import get_logger

logger = get_logger()

CREATE_TURNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conversation_turns (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    turn_index INT NOT NULL,
    raw_query TEXT NOT NULL,
    final_response TEXT NOT NULL,
    primary_intent TEXT,
    intent_confidence FLOAT,
    messages JSONB,
    query_analysis JSONB,
    tool_results JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

_ADD_INTENT_COLUMNS_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='conversation_turns' AND column_name='primary_intent'
    ) THEN
        ALTER TABLE conversation_turns ADD COLUMN primary_intent TEXT;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='conversation_turns' AND column_name='intent_confidence'
    ) THEN
        ALTER TABLE conversation_turns ADD COLUMN intent_confidence FLOAT;
    END IF;
END
$$;
"""

INSERT_TURN_SQL = """
INSERT INTO conversation_turns (
    conversation_id,
    user_id,
    session_id,
    turn_index,
    raw_query,
    final_response,
    primary_intent,
    intent_confidence,
    messages,
    query_analysis,
    tool_results
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
"""


def _json_or_none(value: Optional[Dict[str, Any]]):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_list_or_none(value: Optional[List[Dict[str, Any]]]):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def write_conversation_turn(
    conversation_id: str,
    user_id: str,
    session_id: str,
    turn_index: int,
    raw_query: str,
    final_response: str,
    primary_intent: Optional[str] = None,
    intent_confidence: Optional[float] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    query_analysis: Optional[Dict[str, Any]] = None,
    tool_results: Optional[Dict[str, Any]] = None,
) -> bool:
    """Persist a conversation turn. Returns True when stored."""
    try:
        with get_db_cursor() as cur:
            cur.execute(CREATE_TURNS_TABLE_SQL)
            cur.execute(_ADD_INTENT_COLUMNS_SQL)
            cur.execute(
                INSERT_TURN_SQL,
                (
                    conversation_id,
                    user_id,
                    session_id,
                    turn_index,
                    raw_query,
                    final_response,
                    primary_intent,
                    intent_confidence,
                    _json_list_or_none(messages),
                    _json_or_none(query_analysis),
                    _json_or_none(tool_results),
                ),
            )
        return True
    except Exception as exc:  # pragma: no cover - depends on env
        logger.warning("db.conversation_write_failed", error=str(exc))
        return False
