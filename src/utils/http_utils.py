from typing import Any, Dict, Optional, Type
from pydantic import BaseModel


class ResponseModel(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None


def success_response(
    data: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> ResponseModel:
    return ResponseModel(success=True, data=data or {}, message=message)


def error_response(
    error: str,
    message: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> ResponseModel:
    return ResponseModel(success=False, error=error, message=message, data=data or {})
