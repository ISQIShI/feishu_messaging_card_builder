# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from feishu_messaging_card_builder.runtime_event import (
    EventClassification,
    parse_runtime_event,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8")))


def test_minimal_text_event_normalizes() -> None:
    fixture = load_fixture("hermes_final_reply.json")
    _ = fixture.pop("created_at")
    fixture["recipient_id"] = "ou_001"
    fixture["recipient_type"] = "open_id"

    classification, normalized = parse_runtime_event(fixture)

    assert classification is EventClassification.SUPPORTED
    assert normalized is not None
    assert normalized.recipient_tuple() == ("ou_001", "open_id")
    assert normalized.to_delivery_fixture() == {
        "source_platform": "feishu",
        "session_key": "sess-001",
        "hermes_message_id": "hermes-msg-0001",
        "final_reply_index": 1,
        "content_markdown": fixture["content_markdown"],
    }


def test_unsupported_event_classified() -> None:
    fixture = load_fixture("hermes_final_reply.json")
    _ = fixture.pop("created_at")
    fixture["source_platform"] = "slack"
    fixture["recipient_id"] = "ou_001"
    fixture["recipient_type"] = "open_id"

    classification, normalized = parse_runtime_event(fixture)

    assert classification is EventClassification.UNSUPPORTED
    assert normalized is None


def test_malformed_event_classified() -> None:
    fixture = load_fixture("hermes_final_reply.json")
    _ = fixture.pop("created_at")
    fixture["final_reply_index"] = 0
    fixture["recipient_id"] = "ou_001"
    fixture["recipient_type"] = "open_id"

    classification, normalized = parse_runtime_event(fixture)

    assert classification is EventClassification.MALFORMED
    assert normalized is None


def test_missing_recipient_classified() -> None:
    fixture = load_fixture("hermes_final_reply.json")
    _ = fixture.pop("created_at")

    classification, normalized = parse_runtime_event(fixture)

    assert classification is EventClassification.MISSING_RECIPIENT
    assert normalized is None
