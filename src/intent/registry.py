INTENT_REGISTRY = {
    "refund_request": {
        "supported": True,
        "utterances": [
            "I want my money back",
            "please refund me",
            "charge is wrong",
            "I was overcharged",
            "أريد استرداد أموالي",
            "can I get a refund",
            "return my money",
            "money back please",
        ],
        "conditions": [
            "order_exists",
            "order_belongs_to_user",
            "order_age_days <= 30",
            "refund_not_already_processed"
        ],
        "required_params": ["order_id", "user_id"],
        "tool_chain": {
            "sequential": ["check_order", "check_refund_eligibility"],
            "conditional": {
                "eligible": "initiate_refund",
                "ineligible": "escalate_to_human"
            }
        },
        "fallback": "escalate_to_human"
    },
    "order_status": {
        "supported": True,
        "utterances": [
            "where is my order",
            "track my order",
            "order status",
            "أين طلبي",
            "my order",
            "order update",
            "shipping status",
        ],
        "conditions": ["order_exists", "order_belongs_to_user"],
        "required_params": ["order_id", "user_id"],
        "tool_chain": {
            "sequential": ["check_order"]
        },
        "fallback": "escalate_to_human"
    },
    "delivery_tracking": {
        "supported": True,
        "utterances": [
            "when will it arrive",
            "delivery date",
            "shipping update",
            "package location",
            "متى سيصل طلبي",
            "تتبع الشحنة",
        ],
        "conditions": ["order_exists", "order_belongs_to_user"],
        "required_params": ["order_id", "user_id"],
        "tool_chain": {
            "sequential": ["track_delivery"]
        },
        "fallback": "escalate_to_human"
    },
    "warranty_claim": {
        "supported": True,
        "utterances": [
            "warranty claim",
            "product is defective",
            "broken product",
            "guarantee claim",
            "product warranty",
            "إصلاح الضمان",
        ],
        "conditions": ["order_exists", "order_belongs_to_user", "product_has_warranty"],
        "required_params": ["order_id", "user_id", "product_id"],
        "tool_chain": {
            "sequential": ["check_warranty", "initiate_claim"]
        },
        "fallback": "escalate_to_human"
    },
    "cancel_order": {
        "supported": True,
        "utterances": [
            "cancel my order",
            "order cancellation",
            "cancel please",
            "إلغاء الطلب",
            "cancel",
        ],
        "conditions": ["order_exists", "order_belongs_to_user", "order_not_shipped"],
        "required_params": ["order_id", "user_id"],
        "tool_chain": {
            "sequential": ["check_order", "cancel_order"]
        },
        "fallback": "escalate_to_human"
    },
    "change_delivery_address": {
        "supported": True,
        "utterances": [
            "change address",
            "update delivery address",
            "different delivery location",
            "تغيير العنوان",
        ],
        "conditions": ["order_exists", "order_belongs_to_user", "order_not_shipped"],
        "required_params": ["order_id", "user_id", "new_address"],
        "tool_chain": {
            "sequential": ["check_order", "update_address"]
        },
        "fallback": "escalate_to_human"
    },
    "payment_issue": {
        "supported": True,
        "utterances": [
            "payment failed",
            "payment problem",
            "charge issue",
            "billing problem",
            "مشكلة في الدفع",
        ],
        "conditions": [],
        "required_params": ["user_id"],
        "tool_chain": {
            "sequential": ["check_payment"]
        },
        "fallback": "escalate_to_human"
    },
    "product_inquiry": {
        "supported": True,
        "utterances": [
            "product information",
            "product details",
            "is this available",
            "about this product",
            "معلومات عن المنتج",
        ],
        "conditions": [],
        "required_params": ["product_id"],
        "tool_chain": {
            "sequential": ["get_product_info"]
        },
        "fallback": "escalate_to_human"
    },
    "account_help": {
        "supported": True,
        "utterances": [
            "help with account",
            "account issue",
            "login problem",
            "password reset",
            "مشكلة في الحساب",
        ],
        "conditions": [],
        "required_params": ["user_id"],
        "tool_chain": {
            "sequential": ["check_account"]
        },
        "fallback": "escalate_to_human"
    },
    "general_inquiry": {
        "supported": True,
        "utterances": [
            "how does this work",
            "help me",
            "what is your policy",
            "general question",
            "كيف يعمل",
        ],
        "conditions": [],
        "required_params": [],
        "tool_chain": {
            "sequential": []
        },
        "fallback": "escalate_to_human"
    },
    "speak_to_human": {
        "supported": True,
        "utterances": [
            "speak to agent",
            "talk to human",
            "speak to manager",
            "إ talking to a person",
        ],
        "conditions": [],
        "required_params": [],
        "tool_chain": {
            "sequential": ["escalate_to_human"]
        },
        "fallback": "escalate_to_human"
    },
}

# Intent support status constants
SUPPORT_STATUS = {
    "SUPPORTED": "SUPPORTED",
    "IN_DOMAIN_OUT_OF_SCOPE": "IN_DOMAIN_OUT_OF_SCOPE",
    "UNSUPPORTED": "UNSUPPORTED",
}

# Param validation status constants
PARAM_STATUS = {
    "COMPLETE": "COMPLETE",
    "INCOMPLETE": "INCOMPLETE",
    "SWAP_DETECTED": "SWAP_DETECTED",
}