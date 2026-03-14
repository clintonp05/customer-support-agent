from typing import Any, Dict, Optional


def merge_non_null(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    """Merge dicts and ignore keys with None values."""
    result: Dict[str, Any] = {}
    for d in dicts:
        for key, value in d.items():
            if value is not None:
                result[key] = value
    return result


def safe_get(d: Dict[str, Any], key: str, default: Optional[Any] = None) -> Any:
    return d.get(key, default)
