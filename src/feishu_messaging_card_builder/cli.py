from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Protocol, TypedDict, cast
from pathlib import Path

from .bridge import BridgeOrchestrationError, BridgeOrchestrator, redact_failure_text
from .feishu_client import FeishuCardClient, MockFeishuTransport
from .runtime_bridge import CredentialGuard, DeliveryMode, RuntimeBridge, normalize_delivery_mode
from .state import BridgeStateManager


DEFAULT_DB_PATH = ".fmcb/bridge.sqlite"


class CommandFunc(Protocol):
    def __call__(self, args: CLIArgs) -> int: ...


class CLIArgs(Protocol):
    func: CommandFunc
    fixture_path: str
    db: str
    mock_feishu: bool
    live_feishu: bool
    evidence: str
    recipient: str
    bridge_message_id: str
    fixture: str
    delivery_mode: str
    evidence_dir: str
    require_live_env: bool


def _ensure_live_guard(live_feishu: bool) -> bool:
    if not live_feishu:
        return True

    print("Live Feishu transport is not yet implemented", file=sys.stderr)
    return True


def _build_stack(db_path: str) -> tuple[BridgeStateManager, MockFeishuTransport, FeishuCardClient, BridgeOrchestrator]:
    state = BridgeStateManager(db_path)
    transport = MockFeishuTransport()
    client = FeishuCardClient(transport)
    orchestrator = BridgeOrchestrator(state, client)
    return state, transport, client, orchestrator


def _runtime_bridge_harness_evidence(result: object, *, delivery_mode: str) -> dict[str, object]:
    typed_result = cast("RuntimeBridgeResultLike", result)
    normalized_mode = normalize_delivery_mode(delivery_mode)
    return {
        "normalized_event_count": typed_result.normalized_event_count,
        "native_delivery_recorded": typed_result.native_delivery_recorded,
        "card_create_count": typed_result.card_create_count,
        "card_send_count": typed_result.card_send_count,
        "card_update_count": typed_result.card_update_count,
        "entity_first": typed_result.entity_first,
        "classification": typed_result.classification,
        "status": typed_result.status,
        "live": False,
        "bridge_disabled": normalized_mode is DeliveryMode.DISABLED,
        "delivery_mode": normalized_mode.value,
        "bridge_message_id_sha256": typed_result.bridge_message_id_sha256,
        "card_id_sha256": typed_result.card_id_sha256,
        "feishu_message_id_sha256": typed_result.feishu_message_id_sha256,
        "hermes_message_id_sha256": typed_result.hermes_message_id_sha256,
        "recipient_id_sha256": typed_result.recipient_id_sha256,
        "sequence": typed_result.sequence,
        "is_duplicate": typed_result.is_duplicate,
        "recovery_instruction": typed_result.recovery_instruction,
    }


class RuntimeBridgeResultLike(Protocol):
    normalized_event_count: int
    native_delivery_recorded: bool
    card_create_count: int
    card_send_count: int
    card_update_count: int
    entity_first: bool
    classification: str
    status: str
    live: bool
    bridge_message_id_sha256: str | None
    card_id_sha256: str | None
    feishu_message_id_sha256: str | None
    hermes_message_id_sha256: str | None
    recipient_id_sha256: str | None
    sequence: int | None
    is_duplicate: bool
    recovery_instruction: str | None


def _write_json(path: str | Path, payload: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


_SAFE_RECORD_FIELDS = {
    "bridge_message_id",
    "source_platform",
    "session_key",
    "final_reply_index",
    "content_hash",
    "status",
    "version",
    "sequence",
    "updatable_until",
    "created_at",
    "updated_at",
    "failure_reason",
    "idempotency_key",
}

_SENSITIVE_BODY_KEY_NAMES = frozenset({"content", "receive_id"})


def _safe_record_view(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key in _SAFE_RECORD_FIELDS}


def _safe_records_view(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [_safe_record_view(record) for record in records]


def _sha256_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _key_names(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    mapping = cast(Mapping[object, object], value)
    return sorted(str(key) for key in mapping.keys())


def _safe_body_key_names(value: object) -> list[str]:
    return [key for key in _key_names(value) if key not in _SENSITIVE_BODY_KEY_NAMES]


def _safe_path(path: str) -> str:
    return re.sub(r"(/open-apis/cardkit/v1/cards)/[^/]+$", r"\1/{card_id}", path)


class MockCallSummary(TypedDict):
    method: str
    path: str
    count: int
    param_key_names: list[str]
    body_key_names: list[str]


def _safe_mock_call_summary(mock_calls: list[dict[str, object]]) -> list[MockCallSummary]:
    summaries: list[MockCallSummary] = []
    by_signature: dict[tuple[str, str], MockCallSummary] = {}

    for call in mock_calls:
        method = str(call.get("method", ""))
        path = _safe_path(str(call.get("path", "")))
        signature = (method, path)
        summary = by_signature.get(signature)
        if summary is None:
            summary = MockCallSummary(
                method=method,
                path=path,
                count=0,
                param_key_names=[],
                body_key_names=[],
            )
            by_signature[signature] = summary
            summaries.append(summary)

        summary["count"] += 1
        param_key_names = set(summary["param_key_names"])
        body_key_names = set(summary["body_key_names"])
        summary["param_key_names"] = sorted(param_key_names.union(_key_names(call.get("params"))))
        summary["body_key_names"] = sorted(body_key_names.union(_safe_body_key_names(call.get("body"))))

    return summaries


def _safe_process_evidence(result: ProcessResultLike) -> dict[str, object]:
    return {
        "bridge_message_id_sha256": _sha256_token(result.bridge_message_id),
        "sequence": result.sequence,
        "status": result.status,
        "mock_call_summary": _safe_mock_call_summary(result.mock_calls),
        "recovery_instruction": result.recovery_instruction,
        "live": False,
    }


def _safe_update_evidence(result: UpdateResultLike) -> dict[str, object]:
    return {
        "bridge_message_id_sha256": _sha256_token(result.bridge_message_id),
        "previous_sequence": result.previous_sequence,
        "new_sequence": result.new_sequence,
        "status": result.status,
        "mock_call_summary": _safe_mock_call_summary(result.mock_calls),
        "live": False,
    }


class ProcessResultLike(Protocol):
    bridge_message_id: str
    sequence: int
    status: str
    mock_calls: list[dict[str, object]]
    recovery_instruction: str | None


class UpdateResultLike(Protocol):
    bridge_message_id: str
    previous_sequence: int
    new_sequence: int
    status: str
    mock_calls: list[dict[str, object]]


def _process_fixture_command(args: argparse.Namespace) -> int:
    typed_args = cast(CLIArgs, cast(object, args))
    if not _ensure_live_guard(typed_args.live_feishu):
        return 1
    if typed_args.live_feishu:
        return 1

    _state, _transport, _client, orchestrator = _build_stack(typed_args.db)
    result = orchestrator.process_fixture(typed_args.fixture_path, typed_args.recipient)
    evidence = _safe_process_evidence(result)
    _write_json(typed_args.evidence, evidence)
    return 1 if result.status == "reconciliation_required" else 0


def _update_card_command(args: argparse.Namespace) -> int:
    typed_args = cast(CLIArgs, cast(object, args))
    if not _ensure_live_guard(typed_args.live_feishu):
        return 1
    if typed_args.live_feishu:
        return 1

    state, _transport, _client, orchestrator = _build_stack(typed_args.db)
    record = state.get_record(typed_args.bridge_message_id)
    if record is None:
        raise BridgeOrchestrationError("No bridge record found for the requested bridge message")

    result = orchestrator.update_card(typed_args.bridge_message_id)
    evidence = _safe_update_evidence(result)
    _write_json(typed_args.evidence, evidence)
    return 0


def _inspect_state_command(args: argparse.Namespace) -> int:
    typed_args = cast(CLIArgs, cast(object, args))
    state = BridgeStateManager(typed_args.db)
    raw_mode = bool(getattr(typed_args, "raw", False) or getattr(typed_args, "debug", False))
    if typed_args.bridge_message_id:
        record = (
            state.materialize_expired(typed_args.bridge_message_id)
            if raw_mode
            else state.get_record_for_inspect(typed_args.bridge_message_id)
        )
        if record is None:
            raise BridgeOrchestrationError("No bridge record found for the requested bridge message")
        output: dict[str, object] = dict(record) if raw_mode else _safe_record_view(dict(record))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    records = state.list_records() if raw_mode else state.list_records_for_inspect()
    output_records: list[dict[str, object]] = (
        [dict(record) for record in records]
        if raw_mode
        else _safe_records_view([dict(record) for record in records])
    )
    print(json.dumps(output_records, ensure_ascii=False, indent=2))
    return 0


def _runtime_bridge_harness_command(args: argparse.Namespace) -> int:
    typed_args = cast(CLIArgs, cast(object, args))
    evidence_dir = Path(typed_args.evidence_dir)
    summary_path = evidence_dir / "summary.json"
    run_evidence_path = evidence_dir / "run.json"

    if typed_args.require_live_env:
        ok, missing_keys = CredentialGuard.check_live_credentials()
        if not ok:
            evidence = {
                "normalized_event_count": 0,
                "native_delivery_recorded": False,
                "card_create_count": 0,
                "card_send_count": 0,
                "card_update_count": 0,
                "entity_first": True,
                "classification": "credential_guard",
                "status": "missing_live_env",
                "live": False,
                "bridge_disabled": normalize_delivery_mode(typed_args.delivery_mode) is DeliveryMode.DISABLED,
                "delivery_mode": normalize_delivery_mode(typed_args.delivery_mode).value,
                "bridge_message_id_sha256": None,
                "card_id_sha256": None,
                "feishu_message_id_sha256": None,
                "hermes_message_id_sha256": None,
                "recipient_id_sha256": None,
                "sequence": None,
                "is_duplicate": False,
                "recovery_instruction": None,
                "credential_check": "missing",
                "missing_credential_keys": missing_keys,
            }
            _write_json(summary_path, evidence)
            _write_json(run_evidence_path, evidence)
            diagnostic = CredentialGuard.diagnostic_message()
            if diagnostic:
                print(diagnostic, file=sys.stderr)
            return 1

    fixture_payload = cast(dict[str, object], json.loads(Path(typed_args.fixture_path).read_text(encoding="utf-8")))
    _state, _transport, _client, orchestrator = _build_stack(typed_args.db)
    runtime_bridge = RuntimeBridge(orchestrator, typed_args.delivery_mode)
    result = runtime_bridge.process_payload(fixture_payload)
    evidence = _runtime_bridge_harness_evidence(result, delivery_mode=typed_args.delivery_mode)
    _write_json(summary_path, evidence)
    _write_json(run_evidence_path, evidence)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feishu-messaging-card-builder",
        description="Feishu Messaging Card Builder command line interface.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    process_parser = subparsers.add_parser(
        "process-fixture",
        help="Process a Hermes final-reply fixture and write evidence.",
    )
    _ = process_parser.add_argument("fixture_path", help="Path to the fixture JSON file.")
    _ = process_parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite bridge database path.")
    live_group = process_parser.add_mutually_exclusive_group()
    _ = live_group.add_argument("--mock-feishu", action="store_true", help="Use mock Feishu transport.")
    _ = live_group.add_argument("--live-feishu", action="store_true", help="Request live Feishu mode.")
    _ = process_parser.add_argument("--evidence", required=True, help="JSON evidence output path.")
    _ = process_parser.add_argument("--recipient", default="mock-open-id", help="Feishu recipient open id.")
    process_parser.set_defaults(func=_process_fixture_command)

    update_parser = subparsers.add_parser(
        "update-card",
        help="Update a previously sent card and write evidence.",
    )
    _ = update_parser.add_argument("bridge_message_id", help="Bridge message id to update.")
    _ = update_parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite bridge database path.")
    live_group = update_parser.add_mutually_exclusive_group()
    _ = live_group.add_argument("--mock-feishu", action="store_true", help="Use mock Feishu transport.")
    _ = live_group.add_argument("--live-feishu", action="store_true", help="Request live Feishu mode.")
    _ = update_parser.add_argument("--evidence", required=True, help="JSON evidence output path.")
    update_parser.set_defaults(func=_update_card_command)

    inspect_parser = subparsers.add_parser(
        "inspect-state",
        help="Inspect persisted bridge state as JSON.",
    )
    _ = inspect_parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite bridge database path.")
    _ = inspect_parser.add_argument(
        "--bridge-message-id",
        dest="bridge_message_id",
        help="Optional bridge message id filter.",
    )
    _ = inspect_parser.add_argument("--raw", action="store_true", help="Print full internal state for local debugging.")
    _ = inspect_parser.add_argument("--debug", action="store_true", help="Alias for --raw for local debugging.")
    inspect_parser.set_defaults(func=_inspect_state_command)

    runtime_bridge_parser = subparsers.add_parser(
        "runtime-bridge",
        help="Runtime bridge commands.",
    )
    runtime_bridge_subparsers = runtime_bridge_parser.add_subparsers(dest="runtime_bridge_command", required=True)

    harness_parser = runtime_bridge_subparsers.add_parser(
        "harness",
        help="Run the controlled runtime bridge harness.",
    )
    _ = harness_parser.add_argument("--fixture", required=True, dest="fixture_path", help="Path to the fixture JSON file.")
    _ = harness_parser.add_argument("--db", required=True, help="SQLite bridge database path.")
    _ = harness_parser.add_argument(
        "--delivery-mode",
        default="default",
        choices=[mode.value for mode in DeliveryMode],
        help="Runtime delivery mode.",
    )
    _ = harness_parser.add_argument("--evidence-dir", required=True, help="Directory for evidence output.")
    _ = harness_parser.add_argument(
        "--require-live-env",
        action="store_true",
        help="Require live Feishu credentials before processing.",
    )
    harness_parser.set_defaults(func=_runtime_bridge_harness_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = cast(CLIArgs, cast(object, parser.parse_args(argv)))

    try:
        return int(args.func(args))
    except BridgeOrchestrationError as exc:
        print(redact_failure_text(str(exc)), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(redact_failure_text(str(exc)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
