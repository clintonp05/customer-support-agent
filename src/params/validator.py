import re
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, Any


# ID format signatures — MUST be distinct
ORDER_ID_PATTERN = r"^N-\d{8}-[A-Z0-9]{5}$"
USER_ID_PATTERN = r"^USR-[A-Z0-9]{5,12}$"


class RefundToolParams(BaseModel):
    order_id: str
    user_id: str
    reason: Optional[str] = None

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        if not re.match(ORDER_ID_PATTERN, v):
            if re.match(USER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: order_id looks like user_id: {v}")
            raise ValueError(f"Invalid order_id format: {v}")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v


class OrderStatusParams(BaseModel):
    order_id: str
    user_id: str

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        if not re.match(ORDER_ID_PATTERN, v):
            if re.match(USER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: order_id looks like user_id: {v}")
            raise ValueError(f"Invalid order_id format: {v}")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v


class DeliveryTrackingParams(BaseModel):
    order_id: str
    user_id: str

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        if not re.match(ORDER_ID_PATTERN, v):
            if re.match(USER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: order_id looks like user_id: {v}")
            raise ValueError(f"Invalid order_id format: {v}")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v


class WarrantyClaimParams(BaseModel):
    order_id: str
    user_id: str
    product_id: str
    issue_description: Optional[str] = None

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        if not re.match(ORDER_ID_PATTERN, v):
            if re.match(USER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: order_id looks like user_id: {v}")
            raise ValueError(f"Invalid order_id format: {v}")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v


class CancelOrderParams(BaseModel):
    order_id: str
    user_id: str
    cancellation_reason: Optional[str] = None

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        if not re.match(ORDER_ID_PATTERN, v):
            if re.match(USER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: order_id looks like user_id: {v}")
            raise ValueError(f"Invalid order_id format: {v}")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v


class ChangeAddressParams(BaseModel):
    order_id: str
    user_id: str
    new_address: str

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        if not re.match(ORDER_ID_PATTERN, v):
            if re.match(USER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: order_id looks like user_id: {v}")
            raise ValueError(f"Invalid order_id format: {v}")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v


class PaymentIssueParams(BaseModel):
    user_id: str

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v


class ProductInquiryParams(BaseModel):
    product_id: str


class AccountHelpParams(BaseModel):
    user_id: str

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(USER_ID_PATTERN, v):
            if re.match(ORDER_ID_PATTERN, v):
                raise ValueError(f"PARAM_SWAP: user_id looks like order_id: {v}")
            raise ValueError(f"Invalid user_id format: {v}")
        return v


class EscalationParams(BaseModel):
    user_id: str
    reason: str
    conversation_summary: Optional[str] = None


TOOL_PARAM_SCHEMAS = {
    "check_order": OrderStatusParams,
    "check_refund_eligibility": RefundToolParams,
    "initiate_refund": RefundToolParams,
    "track_delivery": DeliveryTrackingParams,
    "check_warranty": WarrantyClaimParams,
    "initiate_claim": WarrantyClaimParams,
    "cancel_order": CancelOrderParams,
    "update_address": ChangeAddressParams,
    "check_payment": PaymentIssueParams,
    "get_product_info": ProductInquiryParams,
    "check_account": AccountHelpParams,
    "escalate_to_human": EscalationParams,
}


def validate_params(tool_name: str, params: dict) -> tuple[bool, Optional[list], Optional[str]]:
    """
    Validate parameters against the tool's Pydantic schema.

    Returns:
        tuple: (is_valid, missing_params, swap_detected_error)
    """
    schema = TOOL_PARAM_SCHEMAS.get(tool_name)
    if not schema:
        return True, None, None

    # Check for missing required params
    missing = []
    for field_name, field_info in schema.model_fields.items():
        if field_info.is_required() and (field_name not in params or params[field_name] is None):
            missing.append(field_name)

    if missing:
        return False, missing, None

    # Validate params
    try:
        schema(**params)
        return True, None, None
    except ValueError as e:
        error_msg = str(e)
        if "PARAM_SWAP" in error_msg:
            return False, None, error_msg
        raise