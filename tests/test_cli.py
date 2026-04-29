# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from feishu_messaging_card_builder.parser import parse_final_reply
from feishu_messaging_card_builder.state import BridgeStateManager, Status


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
FIXTURE = ROOT / "tests" / "fixtures" / "hermes_final_reply.json"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [str(PYTHON), "-m", "feishu_messaging_card_builder.cli", *args]
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=merged_env)


def test_process_fixture_with_mock_exits_zero_and_writes_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence = tmp_path / "process.json"

    result = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(evidence),
    )

    payload = cast(dict[str, object], json.loads(evidence.read_text(encoding="utf-8")))
    assert result.returncode == 0
    assert payload["status"] == "sent"
    assert payload["card_id"]
    assert payload["feishu_message_id"]
    assert payload["sequence"] == 1
    assert payload["live"] is False


def test_update_card_after_process(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    process_evidence = tmp_path / "process.json"
    update_evidence = tmp_path / "update.json"

    process_result = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(process_evidence),
    )
    process_payload = cast(dict[str, object], json.loads(process_evidence.read_text(encoding="utf-8")))
    bridge_message_id = cast(str, process_payload["bridge_message_id"])
    update_result = _run(
        "update-card",
        bridge_message_id,
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(update_evidence),
    )

    payload = cast(dict[str, object], json.loads(update_evidence.read_text(encoding="utf-8")))
    assert process_result.returncode == 0
    assert update_result.returncode == 0
    assert payload["status"] == "updated"
    assert payload["new_sequence"] == 2


def test_live_feishu_placeholder_blocks_without_env(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence = tmp_path / "guard.json"

    result = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--live-feishu",
        "--evidence",
        str(evidence),
        env={"FEISHU_APP_ID": "", "FEISHU_APP_SECRET": ""},
    )

    assert result.returncode != 0
    assert result.stderr.strip() == "Live Feishu transport is not yet implemented"


def test_live_feishu_placeholder_blocks_with_env(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence = tmp_path / "guard.json"

    result = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--live-feishu",
        "--evidence",
        str(evidence),
        env={"FEISHU_APP_ID": "app-id", "FEISHU_APP_SECRET": "app-secret"},
    )

    assert result.returncode != 0
    assert result.stderr.strip() == "Live Feishu transport is not yet implemented"


def test_process_fixture_reconciliation_required_exits_non_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence = tmp_path / "reconciliation.json"
    state = BridgeStateManager(str(db_path))
    parsed = parse_final_reply(cast(object, json.loads(FIXTURE.read_text(encoding="utf-8"))))
    record = state.get_or_create(
        {
            "source_platform": parsed.source_platform,
            "session_key": parsed.session_key,
            "hermes_message_id": parsed.hermes_message_id,
            "final_reply_index": parsed.final_reply_index,
            "content_markdown": parsed.content_markdown,
        },
        hashlib.sha256(parsed.content_markdown.encode("utf-8")).hexdigest(),
    ).record
    state.update_status(
        record["bridge_message_id"],
        Status.SEND_FAILED,
        card_id="mock-card-ambiguous",
        sequence=1,
        failure_reason="Mock Feishu send failed; status_code=503; error=timeout",
    )

    result = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(evidence),
    )

    payload = cast(dict[str, object], json.loads(evidence.read_text(encoding="utf-8")))
    assert result.returncode == 1
    assert payload["status"] == Status.RECONCILIATION_REQUIRED.value
    assert payload["recovery_instruction"]


def test_inspect_state_prints_json(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence = tmp_path / "process.json"

    _ = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(evidence),
    )

    result = _run("inspect-state", "--db", str(db_path))

    payload = cast(object, json.loads(result.stdout))
    assert result.returncode == 0
    assert isinstance(payload, list)


def test_inspect_state_defaults_to_safe_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence = tmp_path / "process.json"

    _ = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(evidence),
    )

    result = _run("inspect-state", "--db", str(db_path))
    payload = cast(list[dict[str, object]], json.loads(result.stdout))

    assert result.returncode == 0
    assert payload
    record = payload[0]
    assert "content_markdown" not in record
    assert "card_id" not in record
    assert "feishu_message_id" not in record
    assert "tenant_key" not in record


def test_inspect_state_raw_flag_exposes_full_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence = tmp_path / "process.json"

    _ = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(evidence),
    )

    result = _run("inspect-state", "--db", str(db_path), "--raw")
    payload = cast(list[dict[str, object]], json.loads(result.stdout))

    assert result.returncode == 0
    assert payload
    record = payload[0]
    assert "content_markdown" in record
    assert "card_id" in record
    assert "feishu_message_id" in record


def test_inspect_state_materializes_expired_status(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence = tmp_path / "process.json"

    _ = _run(
        "process-fixture",
        str(FIXTURE),
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(evidence),
    )

    process_payload = cast(dict[str, object], json.loads(evidence.read_text(encoding="utf-8")))
    bridge_message_id = cast(str, process_payload["bridge_message_id"])
    expired_timestamp = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute(
            "UPDATE card_deliveries SET updatable_until = ? WHERE bridge_message_id = ?",
            (expired_timestamp, bridge_message_id),
        )

    result = _run(
        "inspect-state",
        "--db",
        str(db_path),
        "--bridge-message-id",
        bridge_message_id,
    )

    payload = cast(dict[str, object], json.loads(result.stdout))
    assert result.returncode == 0
    assert payload["bridge_message_id"] == bridge_message_id
    assert payload["status"] == Status.EXPIRED.value


def test_cli_help_lists_all_subcommands() -> None:
    result = subprocess.run(
        [str(PYTHON), "-m", "feishu_messaging_card_builder.cli", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=dict(os.environ),
    )

    assert result.returncode == 0
    assert "process-fixture" in result.stdout
    assert "update-card" in result.stdout
    assert "inspect-state" in result.stdout
