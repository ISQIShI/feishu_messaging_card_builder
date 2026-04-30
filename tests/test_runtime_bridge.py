# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import cast

import pytest

from feishu_messaging_card_builder.bridge import BridgeOrchestrator
from feishu_messaging_card_builder.feishu_client import FeishuCardClient, MockFeishuTransport
from feishu_messaging_card_builder.runtime_bridge import (
    CredentialGuard,
    DeliveryMode,
    RuntimeBridge,
    check_live_credentials,
    normalize_delivery_mode,
    should_create_or_send_cards,
    should_record_native_delivery,
)
from feishu_messaging_card_builder.runtime_event import EventClassification, NormalizedRuntimeEvent, parse_runtime_event
from feishu_messaging_card_builder.state import BridgeStateManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"
HAPPY_FIXTURE = FIXTURES_DIR / "hermes_final_reply.json"


def load_fixture(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def build_runtime_bridge(
    temp_dir: tempfile.TemporaryDirectory[str],
    *,
    delivery_mode: str | DeliveryMode,
) -> tuple[RuntimeBridge, MockFeishuTransport, BridgeStateManager]:
    transport = MockFeishuTransport()
    state = BridgeStateManager(str(Path(temp_dir.name) / "bridge.sqlite"))
    orchestrator = BridgeOrchestrator(state, FeishuCardClient(transport))
    return RuntimeBridge(orchestrator, delivery_mode), transport, state


def build_supported_event(**overrides: object) -> NormalizedRuntimeEvent:
    payload = load_fixture(HAPPY_FIXTURE)
    runtime_payload = {
        "source_platform": payload["source_platform"],
        "session_key": payload["session_key"],
        "hermes_message_id": payload["hermes_message_id"],
        "final_reply_index": payload["final_reply_index"],
        "content_markdown": payload["content_markdown"],
        "recipient_id": "open_id:test-user",
        "recipient_type": "open_id",
    }
    runtime_payload.update(overrides)
    classification, event = parse_runtime_event(runtime_payload)
    assert classification is EventClassification.SUPPORTED
    assert event is not None
    return event


def test_controlled_dual_requires_explicit_mode() -> None:
    assert normalize_delivery_mode(None) is DeliveryMode.DEFAULT
    assert should_record_native_delivery(None) is True
    assert should_create_or_send_cards(None) is False
    assert should_create_or_send_cards("default") is False
    assert should_create_or_send_cards("controlled-dual") is True


def test_missing_credentials_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)

    ok, missing_keys = check_live_credentials()
    message = CredentialGuard.diagnostic_message()

    assert ok is False
    assert missing_keys == ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]
    assert "FEISHU_APP_ID" in message
    assert "FEISHU_APP_SECRET" in message
    assert "app-id" not in message
    assert "app-secret" not in message


def test_controlled_dual_entity_first_lifecycle() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        bridge, transport, _state = build_runtime_bridge(temp_dir, delivery_mode="controlled-dual")

        result = bridge.process_event(build_supported_event())

        assert result.normalized_event_count == 1
        assert result.native_delivery_recorded is True
        assert result.card_create_count == 1
        assert result.card_send_count == 1
        assert result.card_update_count == 0
        assert result.entity_first is True
        assert result.classification == "supported"
        assert result.status == "sent"
        assert result.live is False
        assert result.bridge_message_id_sha256 is not None
        assert result.card_id_sha256 is not None
        assert result.feishu_message_id_sha256 is not None
        assert result.recipient_id_sha256 is not None
        assert len(transport.calls) == 2
        assert [call["path"] for call in transport.calls] == [
            "/open-apis/cardkit/v1/cards",
            "/open-apis/im/v1/messages",
        ]
    finally:
        temp_dir.cleanup()


def test_disabled_mode_invokes_no_card_operations() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        bridge, transport, _state = build_runtime_bridge(temp_dir, delivery_mode="disabled")

        result = bridge.process_event(build_supported_event())

        assert normalize_delivery_mode("disabled") is DeliveryMode.DISABLED
        assert result.normalized_event_count == 1
        assert result.native_delivery_recorded is True
        assert result.card_create_count == 0
        assert result.card_send_count == 0
        assert result.card_update_count == 0
        assert result.classification == "supported"
        assert result.status == "native_delivery_recorded"
        assert result.live is False
        assert transport.calls == []
    finally:
        temp_dir.cleanup()


def test_unsupported_event_zero_card_operations() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        bridge, transport, _state = build_runtime_bridge(temp_dir, delivery_mode="controlled-dual")
        payload = {
            "source_platform": "feishu",
            "session_key": "runtime-session-001",
            "hermes_message_id": "runtime-unsupported-001",
            "final_reply_index": 1,
            "content_markdown": "Runtime unsupported payload",
            "recipient_id": "open_id:test-user",
            "recipient_type": "open_id",
        }
        payload["streaming_chunk"] = True

        result = bridge.process_payload(payload)

        assert result.normalized_event_count == 0
        assert result.native_delivery_recorded is False
        assert result.card_create_count == 0
        assert result.card_send_count == 0
        assert result.card_update_count == 0
        assert result.classification == "unsupported"
        assert result.status == "unsupported"
        assert result.live is False
        assert transport.calls == []
    finally:
        temp_dir.cleanup()


def test_malformed_event_zero_card_operations() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        bridge, transport, _state = build_runtime_bridge(temp_dir, delivery_mode="controlled-dual")
        payload = {
            "source_platform": "feishu",
            "session_key": "runtime-session-002",
            "hermes_message_id": "runtime-malformed-001",
            "final_reply_index": "not-an-int",
            "content_markdown": "Runtime malformed payload",
            "recipient_id": "open_id:test-user",
            "recipient_type": "open_id",
        }

        result = bridge.process_payload(payload)

        assert result.normalized_event_count == 0
        assert result.native_delivery_recorded is False
        assert result.card_create_count == 0
        assert result.card_send_count == 0
        assert result.card_update_count == 0
        assert result.classification == "malformed"
        assert result.status == "malformed"
        assert result.live is False
        assert transport.calls == []
    finally:
        temp_dir.cleanup()


def test_duplicate_replay_does_not_create_second_card() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        bridge, transport, state = build_runtime_bridge(temp_dir, delivery_mode="controlled-dual")
        event = build_supported_event(hermes_message_id="runtime-duplicate-001")

        first = bridge.process_event(event)
        second = bridge.process_event(event)

        assert first.is_duplicate is False
        assert second.is_duplicate is True
        assert first.bridge_message_id_sha256 == second.bridge_message_id_sha256
        assert second.card_create_count == 0
        assert second.card_send_count == 0
        assert second.card_update_count == 0
        assert len(state.list_records()) == 1
        assert len(transport.calls) == 2
    finally:
        temp_dir.cleanup()
