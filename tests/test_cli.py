from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


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

    payload = json.loads(evidence.read_text(encoding="utf-8"))
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
    bridge_message_id = json.loads(process_evidence.read_text(encoding="utf-8"))["bridge_message_id"]
    update_result = _run(
        "update-card",
        bridge_message_id,
        "--db",
        str(db_path),
        "--mock-feishu",
        "--evidence",
        str(update_evidence),
    )

    payload = json.loads(update_evidence.read_text(encoding="utf-8"))
    assert process_result.returncode == 0
    assert update_result.returncode == 0
    assert payload["status"] == "updated"
    assert payload["new_sequence"] == 2


def test_live_feishu_guard_blocks_without_env(tmp_path: Path) -> None:
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
    assert "Missing required env vars" in result.stderr


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

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert isinstance(payload, list)


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
