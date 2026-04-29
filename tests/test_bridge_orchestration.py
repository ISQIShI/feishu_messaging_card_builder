# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import cast

import pytest

from feishu_messaging_card_builder.bridge import (
    BridgeOrchestrationError,
    BridgeOrchestrator,
)
from feishu_messaging_card_builder.feishu_client import (
    FeishuApiError,
    FeishuCardClient,
    JSONDict,
    MockFeishuTransport,
    build_card_entity_send_request,
)
from feishu_messaging_card_builder.state import BridgeStateError, BridgeStateManager, Status

FIXTURES_DIR = Path(__file__).parent / "fixtures"
HAPPY_FIXTURE = FIXTURES_DIR / "hermes_final_reply.json"


def load_fixture(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def write_fixture(directory: Path, name: str, **overrides: object) -> Path:
    fixture = load_fixture(HAPPY_FIXTURE)
    fixture.update(overrides)
    target = directory / name
    _ = target.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def build_orchestrator(
    temp_dir: tempfile.TemporaryDirectory[str],
    *,
    transport: MockFeishuTransport | None = None,
    state: BridgeStateManager | None = None,
) -> tuple[BridgeOrchestrator, BridgeStateManager, MockFeishuTransport]:
    chosen_transport = transport or MockFeishuTransport()
    chosen_state = state or BridgeStateManager(str(Path(temp_dir.name) / "bridge.sqlite"))
    orchestrator = BridgeOrchestrator(chosen_state, client=_build_client(chosen_transport))
    return orchestrator, chosen_state, chosen_transport


def _build_client(transport: MockFeishuTransport) -> FeishuCardClient:
    return FeishuCardClient(transport)


def configure_fail_first_send(transport: MockFeishuTransport) -> None:
    original_send = transport.record_send
    did_fail_send = False

    def fail_first_send(card_id: str, recipient: str) -> JSONDict:
        nonlocal did_fail_send
        if not did_fail_send:
            did_fail_send = True
            request = build_card_entity_send_request(card_id, recipient)
            error_response: JSONDict = {"error": "mock send failure", "status_code": 503}
            params = request.get("params")
            transport.calls.append(
                {
                    "method": request["method"],
                    "path": request["path"],
                    "params": params,
                    "body": request["body"],
                    "response": error_response,
                }
            )
            raise FeishuApiError(
                "Mock Feishu send failed",
                status_code=503,
                response=error_response,
            )
        return original_send(card_id, recipient)

    object.__setattr__(transport, "record_send", fail_first_send)


def configure_explicit_rejection_first_send(transport: MockFeishuTransport) -> None:
    original_send = transport.record_send
    did_fail_send = False

    def reject_first_send(card_id: str, recipient: str) -> JSONDict:
        nonlocal did_fail_send
        if not did_fail_send:
            did_fail_send = True
            request = build_card_entity_send_request(card_id, recipient)
            error_response: JSONDict = {
                "code": 230020,
                "msg": "invalid receive_id",
                "status_code": 400,
            }
            params = request.get("params")
            transport.calls.append(
                {
                    "method": request["method"],
                    "path": request["path"],
                    "params": params,
                    "body": request["body"],
                    "response": error_response,
                }
            )
            raise FeishuApiError(
                "Mock Feishu send rejected before acceptance",
                status_code=400,
                response=error_response,
            )
        return original_send(card_id, recipient)

    object.__setattr__(transport, "record_send", reject_first_send)


def configure_fail_first_sent_persist(state: BridgeStateManager) -> None:
    original_update_status = state.update_status
    did_fail_sent_update = False

    def fail_first_sent_update(
        bridge_message_id: str,
        status: Status,
        **extra_fields: object,
    ) -> None:
        nonlocal did_fail_sent_update
        if status is Status.SENT and not did_fail_sent_update:
            did_fail_sent_update = True
            raise BridgeStateError("Injected SENT persistence failure")
        original_update_status(bridge_message_id, status, **extra_fields)

    object.__setattr__(state, "update_status", fail_first_sent_update)


def test_process_final_reply_happy_path() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        orchestrator, state, transport = build_orchestrator(temp_dir)

        result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:alice")
        record = state.get_record(result.bridge_message_id)

        assert result.status == Status.SENT.value
        assert result.card_id is not None
        assert result.feishu_message_id is not None
        assert result.sequence == 1
        assert result.is_duplicate is False
        assert len(result.mock_calls) == 2
        assert record is not None
        assert record["status"] == Status.SENT.value
        assert record["card_id"] == result.card_id
        assert record["feishu_message_id"] == result.feishu_message_id
        assert len(transport.calls) == 2
    finally:
        temp_dir.cleanup()


def test_happy_path_creates_exactly_one_card_and_sends_once() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        orchestrator, _state, transport = build_orchestrator(temp_dir)

        _ = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:bob")

        assert len(transport.calls) == 2
        assert [call["path"] for call in transport.calls] == [
            "/open-apis/cardkit/v1/cards",
            "/open-apis/im/v1/messages",
        ]

    finally:
        temp_dir.cleanup()


def test_update_card_happy_path() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        orchestrator, state, transport = build_orchestrator(temp_dir)

        process_result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:carol")
        update_result = orchestrator.update_card(process_result.bridge_message_id)
        record = state.get_record(process_result.bridge_message_id)

        assert update_result.previous_sequence == 1
        assert update_result.new_sequence == 2
        assert update_result.status == Status.UPDATED.value
        assert len(update_result.mock_calls) == 1
        assert transport.calls[-1]["method"] == "PUT"
        assert transport.calls[-1]["body"]["sequence"] == 2
        card_payload = transport.calls[-1]["body"]["card"]
        assert isinstance(card_payload, dict)
        assert "> Updated by Phase 1 prototype" in str(card_payload["data"])

        assert record is not None
        assert record["status"] == Status.UPDATED.value
        assert record["sequence"] == 2
        assert record["version"] == 2
    finally:
        temp_dir.cleanup()


def test_duplicate_replay_creates_no_second_card() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        orchestrator, state, transport = build_orchestrator(temp_dir)

        first = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:duplicate")
        second = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:duplicate")

        assert first.is_duplicate is False
        assert second.is_duplicate is True
        assert second.bridge_message_id == first.bridge_message_id
        assert second.card_id == first.card_id
        assert second.feishu_message_id == first.feishu_message_id
        assert second.mock_calls == []
        assert len(state.list_records()) == 1
        assert len(transport.calls) == 2
    finally:
        temp_dir.cleanup()


def test_create_success_send_failure_requires_reconciliation_on_retry() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        transport = MockFeishuTransport()
        configure_fail_first_send(transport)
        orchestrator, state, _transport = build_orchestrator(temp_dir, transport=transport)

        with pytest.raises(BridgeOrchestrationError) as exc_info:
            _ = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:retry")

        failed_record = state.list_records()[0]
        retry_result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:retry")
        retried_record = state.get_record(retry_result.bridge_message_id)
        create_calls = [call for call in transport.calls if call["path"] == "/open-apis/cardkit/v1/cards"]
        send_calls = [call for call in transport.calls if call["path"] == "/open-apis/im/v1/messages"]


        assert exc_info.value.card_id is not None
        assert failed_record["status"] == Status.SEND_FAILED.value
        assert failed_record["card_id"] == exc_info.value.card_id
        assert retry_result.card_id == exc_info.value.card_id
        assert retry_result.status == Status.RECONCILIATION_REQUIRED.value
        assert retry_result.recovery_instruction is not None
        assert retry_result.mock_calls == []
        assert len(create_calls) == 1
        assert len(send_calls) == 1
        assert retried_record is not None
        assert retried_record["status"] == Status.RECONCILIATION_REQUIRED.value
    finally:
        temp_dir.cleanup()


def test_explicit_rejection_allows_retry() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        transport = MockFeishuTransport()
        configure_explicit_rejection_first_send(transport)
        orchestrator, state, _transport = build_orchestrator(temp_dir, transport=transport)

        with pytest.raises(BridgeOrchestrationError) as exc_info:
            _ = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:invalid")

        retry_result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:valid")
        retried_record = state.get_record(retry_result.bridge_message_id)
        create_calls = [call for call in transport.calls if call["path"] == "/open-apis/cardkit/v1/cards"]
        send_calls = [call for call in transport.calls if call["path"] == "/open-apis/im/v1/messages"]

        assert exc_info.value.card_id is not None
        assert retry_result.card_id == exc_info.value.card_id
        assert retry_result.status == Status.SENT.value
        assert len(create_calls) == 1
        assert len(send_calls) == 2
        assert retried_record is not None
        assert retried_record["status"] == Status.SENT.value
    finally:
        temp_dir.cleanup()


def test_restart_safe_update() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        db_path = str(Path(temp_dir.name) / "bridge.sqlite")
        first_orchestrator = BridgeOrchestrator(BridgeStateManager(db_path), client=_build_client(MockFeishuTransport()))
        process_result = first_orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:restart")

        second_transport = MockFeishuTransport()
        second_orchestrator = BridgeOrchestrator(BridgeStateManager(db_path), client=_build_client(second_transport))
        update_result = second_orchestrator.update_card(process_result.bridge_message_id)
        record = second_orchestrator.get_bridge_messages()[0]

        assert update_result.status == Status.UPDATED.value
        assert update_result.new_sequence == 2
        assert len(second_transport.calls) == 1
        assert second_transport.calls[0]["method"] == "PUT"
        assert record["status"] == Status.UPDATED.value
        assert record["version"] == 2
    finally:
        temp_dir.cleanup()


def test_send_success_persist_fail_returns_recovery_result() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        state = BridgeStateManager(str(Path(temp_dir.name) / "bridge.sqlite"))
        configure_fail_first_sent_persist(state)
        orchestrator, used_state, transport = build_orchestrator(temp_dir, state=state)

        result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:recover")
        record = used_state.get_record(result.bridge_message_id)

        assert result.status == Status.RECONCILIATION_REQUIRED.value
        assert result.recovery_instruction is not None
        assert result.card_id is not None
        assert result.feishu_message_id is not None
        assert len(result.mock_calls) == 2
        assert len(transport.calls) == 2
        assert record is not None
        assert record["status"] == Status.RECONCILIATION_REQUIRED.value
        assert record["failure_reason"] == result.recovery_instruction
    finally:
        temp_dir.cleanup()


def test_update_rejects_non_sent_record() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        orchestrator, state, _transport = build_orchestrator(temp_dir)
        result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:fail")
        failed_record = state.get_record(result.bridge_message_id)
        assert failed_record is not None
        state.update_status(
            failed_record["bridge_message_id"],
            Status.SEND_FAILED,
            card_id=failed_record["card_id"],
            sequence=1,
            failure_reason="forced non-sent state",
        )

        with pytest.raises(BridgeOrchestrationError, match="Only sent or updated"):
            _ = orchestrator.update_card(failed_record["bridge_message_id"])
    finally:
        temp_dir.cleanup()


def test_inspect_state_returns_all_records() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    try:
        orchestrator, _state, _transport = build_orchestrator(temp_dir)
        first_fixture = write_fixture(Path(temp_dir.name), "first.json", hermes_message_id="hermes-10")
        second_fixture = write_fixture(
            Path(temp_dir.name),
            "second.json",
            hermes_message_id="hermes-11",
            final_reply_index=2,
            content_markdown="A second final reply for inspect-state coverage.",
        )

        first_result = orchestrator.process_fixture(first_fixture, "open_id:first")
        second_result = orchestrator.process_fixture(second_fixture, "open_id:second")
        records = orchestrator.get_bridge_messages()
        bridge_ids = {record["bridge_message_id"] for record in records}

        assert len(records) == 2
        assert bridge_ids == {first_result.bridge_message_id, second_result.bridge_message_id}
    finally:
        temp_dir.cleanup()
