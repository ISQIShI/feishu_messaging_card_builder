from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Protocol, cast
from pathlib import Path

from .bridge import BridgeOrchestrationError, BridgeOrchestrator
from .feishu_client import FeishuCardClient, MockFeishuTransport
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


def _safe_record_view(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key in _SAFE_RECORD_FIELDS}


def _safe_records_view(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [_safe_record_view(record) for record in records]


def _process_fixture_command(args: argparse.Namespace) -> int:
    typed_args = cast(CLIArgs, cast(object, args))
    if not _ensure_live_guard(typed_args.live_feishu):
        return 1
    if typed_args.live_feishu:
        return 1

    _state, _transport, _client, orchestrator = _build_stack(typed_args.db)
    result = orchestrator.process_fixture(typed_args.fixture_path, typed_args.recipient)
    evidence = {
        "bridge_message_id": result.bridge_message_id,
        "card_id": result.card_id,
        "feishu_message_id": result.feishu_message_id,
        "sequence": result.sequence,
        "status": result.status,
        "mock_calls": result.mock_calls,
        "recovery_instruction": result.recovery_instruction,
        "live": False,
    }
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
        raise BridgeOrchestrationError(f"No bridge record found for {typed_args.bridge_message_id}")

    result = orchestrator.update_card(typed_args.bridge_message_id)
    evidence = {
        "bridge_message_id": result.bridge_message_id,
        "previous_sequence": result.previous_sequence,
        "new_sequence": result.new_sequence,
        "status": result.status,
        "mock_calls": result.mock_calls,
        "live": False,
    }
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
            raise BridgeOrchestrationError(f"No bridge record found for {typed_args.bridge_message_id}")
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = cast(CLIArgs, cast(object, parser.parse_args(argv)))

    try:
        return int(args.func(args))
    except BridgeOrchestrationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
