"""Field masking rules for compliant (PII-safe) export batches."""

from __future__ import annotations

import hashlib
from typing import Any

MASK_TYPES = ("none", "keep_edges", "blank", "hash")
MASK_CHAR = "*"


def validate_rule(mask_type: str, keep_head: int = 0, keep_tail: int = 0) -> None:
    if mask_type not in MASK_TYPES:
        raise ValueError(f"unsupported mask_type: {mask_type}")
    if keep_head < 0 or keep_tail < 0:
        raise ValueError("keep_head/keep_tail must be >= 0")


def mask_value(value: Any, mask_type: str, keep_head: int = 0, keep_tail: int = 0) -> Any:
    """Apply one masking rule to a single field value."""
    validate_rule(mask_type, keep_head, keep_tail)
    if mask_type == "none":
        return value
    if value is None:
        return None
    text = str(value)
    if mask_type == "blank":
        return ""
    if mask_type == "hash":
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        return f"sha256:{digest}"
    # keep_edges: keep first keep_head / last keep_tail chars, mask the middle.
    if len(text) <= keep_head + keep_tail:
        return MASK_CHAR * len(text)
    head = text[:keep_head] if keep_head else ""
    tail = text[len(text) - keep_tail :] if keep_tail else ""
    return head + MASK_CHAR * (len(text) - keep_head - keep_tail) + tail


def mask_record(
    record: dict[str, Any],
    rules: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Mask every field of a record per rules map; fields without a rule pass through."""
    out: dict[str, Any] = {}
    for field, value in record.items():
        rule = rules.get(field)
        if rule is None:
            out[field] = value
        else:
            out[field] = mask_value(
                value,
                rule["mask_type"],
                int(rule.get("keep_head") or 0),
                int(rule.get("keep_tail") or 0),
            )
    return out
