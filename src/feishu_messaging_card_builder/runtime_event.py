"""Minimal runtime event normalization for Phase 1 bridge input."""

# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from feishu_messaging_card_builder.parser import InvalidFinalReplyError, parse_final_reply
from feishu_messaging_card_builder.state import DeliveryFixture


class EventClassification(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    MALFORMED = "malformed"
    MISSING_RECIPIENT = "missing_recipient"


@dataclass(frozen=True, slots=True)
class NormalizedRuntimeEvent:
    source_platform: str
    session_key: str
    hermes_message_id: str
    final_reply_index: int
    content_markdown: str
    recipient_id: str
    recipient_type: str

    def to_delivery_fixture(self) -> DeliveryFixture:
        return cast(
            DeliveryFixture,
            cast(
                object,
                {
                "source_platform": self.source_platform,
                "session_key": self.session_key,
                "hermes_message_id": self.hermes_message_id,
                "final_reply_index": self.final_reply_index,
                "content_markdown": self.content_markdown,
                },
            ),
        )

    def recipient_tuple(self) -> tuple[str, str]:
        return (self.recipient_id, self.recipient_type)


_SUPPORTED_SOURCE_PLATFORM = "feishu"
_SUPPORTED_FIELDS = frozenset(
    {
        "source_platform",
        "session_key",
        "hermes_message_id",
        "final_reply_index",
        "content_markdown",
        "recipient_id",
        "recipient_type",
    }
)
_CORE_FIELDS = frozenset(
    {
        "source_platform",
        "session_key",
        "hermes_message_id",
        "final_reply_index",
        "content_markdown",
    }
)


def parse_runtime_event(data: dict[str, object]) -> tuple[EventClassification, NormalizedRuntimeEvent | None]:
    payload = data
    payload_keys = frozenset(payload)
    if not payload_keys.issubset(_SUPPORTED_FIELDS):
        return EventClassification.UNSUPPORTED, None

    if payload.get("source_platform") != _SUPPORTED_SOURCE_PLATFORM:
        return EventClassification.UNSUPPORTED, None

    recipient_id = payload.get("recipient_id")
    recipient_type = payload.get("recipient_type")
    missing_recipient = any(
        value is None or not isinstance(value, str) or not value.strip()
        for value in (recipient_id, recipient_type)
    )

    if missing_recipient:
        try:
            _ = parse_final_reply({key: payload[key] for key in _CORE_FIELDS})
        except InvalidFinalReplyError:
            return EventClassification.MALFORMED, None
        return EventClassification.MISSING_RECIPIENT, None

    if not isinstance(recipient_id, str) or not isinstance(recipient_type, str):
        return EventClassification.MALFORMED, None

    try:
        parsed = parse_final_reply({key: payload[key] for key in _CORE_FIELDS})
    except InvalidFinalReplyError:
        return EventClassification.MALFORMED, None

    return (
        EventClassification.SUPPORTED,
        NormalizedRuntimeEvent(
            source_platform=parsed.source_platform,
            session_key=parsed.session_key,
            hermes_message_id=parsed.hermes_message_id,
            final_reply_index=parsed.final_reply_index,
            content_markdown=parsed.content_markdown,
            recipient_id=recipient_id,
            recipient_type=recipient_type,
        ),
    )
