"""Parser for Phase 1 Hermes final-reply fixtures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast


class InvalidFinalReplyError(ValueError):
    """Raised when a Hermes final-reply payload is malformed."""


@dataclass(frozen=True, slots=True)
class ParsedFinalReply:
    """Validated Phase 1 final-reply payload."""

    source_platform: str
    session_key: str
    hermes_message_id: str
    final_reply_index: int
    content_markdown: str
    created_at: str | None = None
    attachments: tuple[dict[str, object], ...] = field(default_factory=tuple)
    tool_payloads: tuple[dict[str, object], ...] = field(default_factory=tuple)


def parse_final_reply(data: object) -> ParsedFinalReply:
    """Extract and validate the supported final-reply fixture fields."""

    if not isinstance(data, dict):
        raise InvalidFinalReplyError("final reply payload must be a dictionary")

    payload = cast(dict[str, object], data)

    source_platform = _require_non_empty_string(payload, "source_platform")
    session_key = _require_non_empty_string(payload, "session_key")
    hermes_message_id = _require_non_empty_string(payload, "hermes_message_id")
    final_reply_index = _require_positive_int(payload, "final_reply_index")
    content_markdown = _require_non_empty_string(payload, "content_markdown")

    created_at_value = payload.get("created_at")
    created_at: str | None
    created_at = None
    if created_at_value is not None:
        if not isinstance(created_at_value, str) or not created_at_value.strip():
            raise InvalidFinalReplyError("created_at must be a non-empty ISO 8601 string")
        _validate_iso8601(created_at_value)
        created_at = created_at_value

    attachments = _normalize_record_list(payload, "attachments")
    tool_payloads = _normalize_record_list(payload, "tool_payloads")

    return ParsedFinalReply(
        source_platform=source_platform,
        session_key=session_key,
        hermes_message_id=hermes_message_id,
        final_reply_index=final_reply_index,
        content_markdown=content_markdown,
        created_at=created_at,
        attachments=attachments,
        tool_payloads=tool_payloads,
    )


def _require_non_empty_string(data: Mapping[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise InvalidFinalReplyError(f"{field_name} is required and must be a non-empty string")
    return value


def _require_positive_int(data: Mapping[str, object], field_name: str) -> int:
    value = data.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidFinalReplyError(f"{field_name} is required and must be a positive integer")
    return value


def _normalize_record_list(
    data: Mapping[str, object], field_name: str
) -> tuple[dict[str, object], ...]:
    value = data.get(field_name, [])
    if value is None:
        return ()
    if not isinstance(value, list):
        raise InvalidFinalReplyError(f"{field_name} must be a list when provided")

    records = cast(list[object], value)
    normalized: list[dict[str, object]] = []
    for index, item in enumerate(records, start=1):
        if not isinstance(item, Mapping):
            raise InvalidFinalReplyError(f"{field_name}[{index}] must be an object")
        record: dict[str, object] = {}
        for key, record_value in cast(Mapping[object, object], item).items():
            if not isinstance(key, str):
                raise InvalidFinalReplyError(f"{field_name}[{index}] keys must be strings")
            record[key] = record_value
        normalized.append(record)
    return tuple(normalized)


def _validate_iso8601(value: str) -> None:
    candidate = value.replace("Z", "+00:00")
    try:
        _ = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise InvalidFinalReplyError("created_at must be a valid ISO 8601 timestamp") from exc
