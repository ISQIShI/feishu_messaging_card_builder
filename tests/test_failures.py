# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
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
from feishu_messaging_card_builder.renderer import OversizeCardError, UnsupportedContentError
from feishu_messaging_card_builder.state import BridgeStateError, BridgeStateManager, Status

FIXTURES_DIR = Path(__file__).parent / "fixtures"
HAPPY_FIXTURE = FIXTURES_DIR / "hermes_final_reply.json"
UNSUPPORTED_FIXTURE = FIXTURES_DIR / "hermes_unsupported_attachment.json"
OVERSIZE_FIXTURE = FIXTURES_DIR / "hermes_oversize_reply.json"
HAPPY_DUPLICATE_FIXTURE = FIXTURES_DIR / "hermes_final_reply_duplicate.json"


def build_orchestrator(
    tmp_path: Path,
    *,
    transport: MockFeishuTransport | None = None,
    state: BridgeStateManager | None = None,
) -> tuple[BridgeOrchestrator, BridgeStateManager, MockFeishuTransport]:
    chosen_transport = transport or MockFeishuTransport()
    chosen_state = state or BridgeStateManager(str(tmp_path / "bridge.sqlite"))
    orchestrator = BridgeOrchestrator(chosen_state, client=FeishuCardClient(chosen_transport))
    return orchestrator, chosen_state, chosen_transport


def configure_fail_first_send(transport: MockFeishuTransport) -> None:
    original_send = transport.record_send
    did_fail_send = False

    def fail_first_send(card_id: str, recipient: str) -> JSONDict:
        nonlocal did_fail_send
        if not did_fail_send:
            did_fail_send = True
            request = build_card_entity_send_request(card_id, recipient)
            error_response = cast(
                JSONDict,
                {
                    "error": "mock send failure",
                    "status_code": 503,
                    "tenant_key": "tenant-secret",
                    "troubleshooter": "https://example.invalid/troubleshooter?id=abc123",
                    "message": "Bearer abc.def.ghi",
                },
            )
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
            error_response = cast(
                JSONDict,
                {"code": 230020, "msg": "invalid receive_id", "status_code": 400},
            )
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


def test_unsupported_content_fails_before_transport(tmp_path: Path) -> None:
    orchestrator, state, transport = build_orchestrator(tmp_path)

    with pytest.raises(UnsupportedContentError, match="attachments"):
        _ = orchestrator.process_fixture(UNSUPPORTED_FIXTURE, "open_id:attachment")

    records = state.list_records()
    assert len(transport.calls) == 0
    assert len(records) == 1
    assert records[0]["status"] == Status.NEW.value


def test_oversize_card_fails_before_transport(tmp_path: Path) -> None:
    orchestrator, state, transport = build_orchestrator(tmp_path)

    with pytest.raises(OversizeCardError, match="exceeding"):
        _ = orchestrator.process_fixture(OVERSIZE_FIXTURE, "open_id:oversize")

    records = state.list_records()
    assert len(transport.calls) == 0
    assert len(records) == 1
    assert records[0]["status"] == Status.NEW.value


def test_duplicate_replay_is_fully_idempotent(tmp_path: Path) -> None:
    orchestrator, state, transport = build_orchestrator(tmp_path)

    first = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:dedupe")
    calls_after_first = copy.deepcopy(transport.calls)
    second = orchestrator.process_fixture(HAPPY_DUPLICATE_FIXTURE, "open_id:dedupe")

    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert second.bridge_message_id == first.bridge_message_id
    assert second.card_id == first.card_id
    assert second.feishu_message_id == first.feishu_message_id
    assert second.mock_calls == []
    assert len(state.list_records()) == 1
    assert transport.calls == calls_after_first


def test_ambiguous_failure_no_longer_retries(tmp_path: Path) -> None:
    transport = MockFeishuTransport()
    configure_fail_first_send(transport)
    orchestrator, state, _transport = build_orchestrator(tmp_path, transport=transport)

    with pytest.raises(BridgeOrchestrationError) as exc_info:
        _ = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:retry")

    failed_record = state.list_records()[0]
    create_calls_after_failure = [call for call in transport.calls if call["path"] == "/open-apis/cardkit/v1/cards"]
    retry_result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:retry")
    retried_record = state.get_record(retry_result.bridge_message_id)
    create_calls = [call for call in transport.calls if call["path"] == "/open-apis/cardkit/v1/cards"]
    send_calls = [call for call in transport.calls if call["path"] == "/open-apis/im/v1/messages"]


    assert exc_info.value.card_id is not None
    assert failed_record["status"] == Status.SEND_FAILED.value
    assert failed_record["card_id"] == exc_info.value.card_id
    assert len(create_calls_after_failure) == 1
    assert retry_result.card_id == exc_info.value.card_id
    assert retry_result.is_duplicate is False
    assert retry_result.status == Status.RECONCILIATION_REQUIRED.value
    assert retry_result.recovery_instruction is not None
    assert len(create_calls) == 1
    assert len(send_calls) == 1
    assert retried_record is not None
    assert retried_record["status"] == Status.RECONCILIATION_REQUIRED.value


def test_explicit_rejection_allows_retry(tmp_path: Path) -> None:
    transport = MockFeishuTransport()
    configure_explicit_rejection_first_send(transport)
    orchestrator, state, _transport = build_orchestrator(tmp_path, transport=transport)

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


@pytest.mark.parametrize(
    ("failure_reason", "expected"),
    [
        (
            "FeishuApiError; status_code=400; summary=code=230020; msg=invalid receive_id",
            True,
        ),
        (
            "FeishuApiError; status_code=400; summary=code=230020; msg=receive_id is invalid",
            True,
        ),
        (
            "FeishuApiError; status_code=400; summary=code=230020; msg=invalid chat_id",
            False,
        ),
        (
            "FeishuApiError; status_code=400; summary=code=230020; msg=invalid recipient",
            False,
        ),
        (
            "FeishuApiError; status_code=400; summary=code=230020; msg=generic bad request",
            False,
        ),
        ("FeishuApiError; status_code=503; summary=error=timeout", False),
        ("FeishuApiError; status_code=500; summary=error=upstream unavailable", False),
        ("FeishuApiError; status_code=400; summary=msg=invalid receive_id", False),
        ('FeishuApiError; status_code=400; summary={"code": 0, "msg": "invalid receive_id"}', False),
        (
            "FeishuApiError; status_code=400; summary=msg: invalid receive_id",
            False,
        ),
        (None, False),
    ],
)
def test_explicit_pre_acceptance_rejection_classifier(
    failure_reason: str | None,
    expected: bool,
) -> None:
    assert BridgeOrchestrator.is_explicit_pre_acceptance_rejection(failure_reason) is expected


def test_send_success_persist_fail_triggers_reconciliation(tmp_path: Path) -> None:
    state = BridgeStateManager(str(tmp_path / "bridge.sqlite"))
    configure_fail_first_sent_persist(state)
    orchestrator, used_state, transport = build_orchestrator(tmp_path, state=state)

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


def test_failed_send_reason_is_redacted(tmp_path: Path) -> None:
    transport = MockFeishuTransport()
    configure_fail_first_send(transport)
    orchestrator, state, _transport = build_orchestrator(tmp_path, transport=transport)

    with pytest.raises(BridgeOrchestrationError):
        _ = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:redacted")

    record = state.list_records()[0]
    failure_reason = record["failure_reason"]

    assert failure_reason is not None
    assert "tenant-secret" not in failure_reason
    assert "troubleshooter" not in failure_reason
    assert "Bearer abc.def.ghi" not in failure_reason
    assert "FeishuApiError" in failure_reason
    assert "status_code=503" in failure_reason


def test_failed_send_reason_redacts_colon_separated_values(tmp_path: Path) -> None:
    transport = MockFeishuTransport()
    original_send = transport.record_send
    did_fail_send = False

    def fail_first_send(card_id: str, recipient: str) -> JSONDict:
        nonlocal did_fail_send
        if not did_fail_send:
            did_fail_send = True
            request = build_card_entity_send_request(card_id, recipient)
            error_response = cast(
                JSONDict,
                {
                    "error": "mock send failure",
                    "status_code": 503,
                    "message": (
                        "tenant_key: tenant-secret; app_secret: app-secret-value; "
                        "token: token-value; troubleshooter: https://example.invalid/troubleshooter?id=abc123"
                    ),
                },
            )
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
    orchestrator, state, _transport = build_orchestrator(tmp_path, transport=transport)

    with pytest.raises(BridgeOrchestrationError):
        _ = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:redacted-colon")

    failure_reason = state.list_records()[0]["failure_reason"]

    assert failure_reason is not None
    assert "tenant-secret" not in failure_reason
    assert "app-secret-value" not in failure_reason
    assert "token-value" not in failure_reason
    assert "tenant_key:[REDACTED]" in failure_reason
    assert "app_secret:[REDACTED]" in failure_reason
    assert "token:[REDACTED]" in failure_reason
    assert "troubleshooter:[REDACTED]" in failure_reason


def test_update_sequence_monotonicity(tmp_path: Path) -> None:
    orchestrator, state, transport = build_orchestrator(tmp_path)

    process_result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:sequence")
    first_update = orchestrator.update_card(process_result.bridge_message_id)
    second_update = orchestrator.update_card(process_result.bridge_message_id)
    record = state.get_record(process_result.bridge_message_id)
    update_calls = [call for call in transport.calls if call["method"] == "PUT"]

    assert first_update.previous_sequence == 1
    assert first_update.new_sequence == 2
    assert second_update.previous_sequence == 2
    assert second_update.new_sequence == 3
    assert [call["body"]["sequence"] for call in update_calls] == [2, 3]
    assert record is not None
    assert record["status"] == Status.UPDATED.value
    assert record["sequence"] == 3


def test_expired_non_updatable_local_gate_skips_remote_update(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    transport = MockFeishuTransport()
    orchestrator, state, _transport = build_orchestrator(tmp_path, transport=transport)

    process_result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:expired")

    expired_timestamp = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute(
            "UPDATE card_deliveries SET updatable_until = ? WHERE bridge_message_id = ?",
            (expired_timestamp, process_result.bridge_message_id),
        )

    result = orchestrator.update_card(process_result.bridge_message_id)

    record = state.get_record(process_result.bridge_message_id)
    assert result.status == Status.EXPIRED.value
    assert result.previous_sequence == 1
    assert result.new_sequence == 1
    assert result.mock_calls == []
    assert not any(call["method"] == "PUT" for call in transport.calls)
    assert record is not None
    assert record["status"] == Status.EXPIRED.value
    assert record["card_id"] == process_result.card_id
    assert record["version"] == 1


def test_failed_update_does_not_advance_version(tmp_path: Path) -> None:
    transport = MockFeishuTransport(failure_status_codes={"update": 410})
    orchestrator, state, _transport = build_orchestrator(tmp_path, transport=transport)

    process_result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:version")

    with pytest.raises(BridgeOrchestrationError, match="Feishu update failed"):
        _ = orchestrator.update_card(process_result.bridge_message_id)

    record = state.get_record(process_result.bridge_message_id)
    assert record is not None
    assert record["status"] == Status.UPDATE_FAILED.value
    assert record["sequence"] == 1
    assert record["version"] == 1


def test_ambiguous_update_failure_requires_reconciliation(tmp_path: Path) -> None:
    transport = MockFeishuTransport(failure_status_codes={"update": 503})
    orchestrator, state, _transport = build_orchestrator(tmp_path, transport=transport)

    process_result = orchestrator.process_fixture(HAPPY_FIXTURE, "open_id:ambiguous-update")

    with pytest.raises(BridgeOrchestrationError, match="Feishu update failed") as exc_info:
        _ = orchestrator.update_card(process_result.bridge_message_id)

    record = state.get_record(process_result.bridge_message_id)
    assert exc_info.value.status == Status.RECONCILIATION_REQUIRED.value
    assert record is not None
    assert record["status"] == Status.RECONCILIATION_REQUIRED.value
    assert record["sequence"] == 1
    assert record["version"] == 1
