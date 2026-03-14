"""Shared constants for the Noon Prep agent."""

# API header constants
X_REQUEST_ID_HEADER = "x-request-id"
X_CHANNEL_ID_HEADER = "x-channel-id"

# Conversation state keys
NEXT_NODE = "next_node"
FINAL_RESPONSE = "final_response"
ESCALATION_REQUIRED = "escalation_required"
TOOL_RESULTS = "tool_results"
EXTRACTED_PARAMS = "extracted_params"

# Responses and messages
MISSING_HEADERS_ERROR = "Missing required headers x-request-id and x-channel-id"
TOXICITY_RESPONSE = "I'm sorry, but I can't assist with that. Please contact customer support directly."
PARAM_SWAP_RESPONSE = "I noticed something unusual with the information provided. For your security, I'll connect you with a human agent."
ESCALATION_GENERIC_RESPONSE = "I'm having trouble processing your request. Please contact customer support directly."

# Param status
PARAM_STATUS_COMPLETE = "COMPLETE"
PARAM_STATUS_INCOMPLETE = "INCOMPLETE"
PARAM_STATUS_SWAP = "SWAP_DETECTED"

# Support status
SUPPORT_STATUS_SUPPORTED = "SUPPORTED"
SUPPORT_STATUS_IN_DOMAIN_OUT_OF_SCOPE = "IN_DOMAIN_OUT_OF_SCOPE"

# Default execution budget
DEFAULT_EXECUTION_BUDGET_MS = 8000

# Prompt templates
PARAM_REQUEST_TEMPLATE = "To help with your {intent} request, I need: {missing_params}. Could you provide these details?"

# Tool status
TOOL_SUCCESS = "success"
TOOL_ERROR = "error"

# Node names
NODE_GUARD_INPUT = "guard_input"
NODE_CLASSIFY_INTENT = "classify_intent"
NODE_EXTRACT_PARAMS = "extract_params"
NODE_VALIDATE_PARAMS = "validate_params"
NODE_REQUEST_PARAMS = "request_params"
NODE_HANDLE_PARAM_ERROR = "handle_param_error"
NODE_EXECUTE_TOOLS = "execute_tools"
NODE_GENERATE_RESPONSE = "generate_response"
NODE_HANDLE_UNSUPPORTED = "handle_unsupported"
NODE_ESCALATE = "escalate"
