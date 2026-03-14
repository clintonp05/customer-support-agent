from src.tools.base import BaseTool
from typing import Dict, Any


class EscalationTool(BaseTool):
    """Human handoff tool with full context"""

    def __init__(self):
        super().__init__(name="escalation_tool")

    async def _call(self, params: dict, state: dict) -> dict:
        user_id = params.get("user_id")
        reason = params.get("reason")
        conversation_summary = params.get("conversation_summary")

        # Build context for human agent
        messages = state.get("messages", [])
        tool_results = state.get("tool_results", {})

        # Format conversation history
        conversation_history = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages[-5:]  # Last 5 messages
        ])

        # Format tool execution results
        tool_summary = "\n".join([
            f"- {tool_name}: {result.get('success', False)}"
            for tool_name, result in tool_results.items()
        ])

        escalation_context = f"""
Customer ID: {user_id}
Escalation Reason: {reason}

Conversation History:
{conversation_history}

Tool Executions:
{tool_summary}

User Request: {messages[-1].get('content', '') if messages else 'N/A'}
"""

        # Mock escalation ticket creation
        import uuid
        return {
            "success": True,
            "ticket_id": f"ESC-{uuid.uuid4().hex[:12].upper()}",
            "user_id": user_id,
            "reason": reason,
            "priority": "high" if "urgent" in reason.lower() else "normal",
            "context": escalation_context,
            "message": "A customer support agent will contact you shortly."
        }