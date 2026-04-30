# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "runtime_bridge"
MINIMAL_FIXTURE = FIXTURE_DIR / "minimal_text_turn.json"
UNSUPPORTED_FIXTURE = FIXTURE_DIR / "unsupported_streaming_chunk.json"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [str(PYTHON), "-m", "feishu_messaging_card_builder.cli", *args]
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=merged_env)


def test_cli_help_lists_runtime_bridge() -> None:
    result = subprocess.run(
        [str(PYTHON), "-m", "feishu_messaging_card_builder.cli", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=dict(os.environ),
    )

    assert result.returncode == 0
    assert "runtime-bridge" in result.stdout


def test_runtime_bridge_harness_controlled_dual_writes_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence_dir = tmp_path / "harness"

    result = _run(
        "runtime-bridge",
        "harness",
        "--fixture",
        str(MINIMAL_FIXTURE),
        "--db",
        str(db_path),
        "--delivery-mode",
        "controlled-dual",
        "--evidence-dir",
        str(evidence_dir),
    )

    payload = cast(dict[str, object], json.loads((evidence_dir / "summary.json").read_text(encoding="utf-8")))
    run_payload = cast(dict[str, object], json.loads((evidence_dir / "run.json").read_text(encoding="utf-8")))

    assert result.returncode == 0
    assert payload == run_payload
    assert payload["normalized_event_count"] == 1
    assert payload["native_delivery_recorded"] is True
    assert payload["card_create_count"] == 1
    assert payload["card_send_count"] == 1
    assert payload["card_update_count"] == 0
    assert payload["entity_first"] is True
    assert payload["classification"] == "supported"
    assert payload["status"] == "sent"
    assert payload["live"] is False
    assert len(cast(str, payload["bridge_message_id_sha256"])) == 64
    assert "test-hermes-msg-001" not in json.dumps(payload)


def test_runtime_bridge_harness_disabled_records_zero_card_ops(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence_dir = tmp_path / "harness"

    result = _run(
        "runtime-bridge",
        "harness",
        "--fixture",
        str(MINIMAL_FIXTURE),
        "--db",
        str(db_path),
        "--delivery-mode",
        "disabled",
        "--evidence-dir",
        str(evidence_dir),
    )

    payload = cast(dict[str, object], json.loads((evidence_dir / "summary.json").read_text(encoding="utf-8")))

    assert result.returncode == 0
    assert payload["bridge_disabled"] is True
    assert payload["native_delivery_recorded"] is True
    assert payload["card_create_count"] == 0
    assert payload["card_send_count"] == 0


def test_reversibility_disabled_check(tmp_path: Path) -> None:
    """
    Proves that the bridge can be disabled and results in zero card operations.
    Evidence: .sisyphus/evidence/plan-7/task-6-reversibility-disabled.json
    """
    db_path = tmp_path / "bridge.sqlite"
    evidence_dir = tmp_path / "harness"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    result = _run(
        "runtime-bridge",
        "harness",
        "--fixture",
        str(MINIMAL_FIXTURE),
        "--db",
        str(db_path),
        "--delivery-mode",
        "disabled",
        "--evidence-dir",
        str(evidence_dir),
    )

    summary_file = evidence_dir / "summary.json"
    payload = cast(dict[str, object], json.loads(summary_file.read_text(encoding="utf-8")))

    # Save evidence to specified location
    evidence_path = ROOT / ".sisyphus" / "evidence" / "plan-7" / "task-6-reversibility-disabled.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    _ = evidence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    assert result.returncode == 0
    assert payload["bridge_disabled"] is True
    assert payload["native_delivery_recorded"] is True
    assert payload["card_create_count"] == 0
    assert payload["card_send_count"] == 0
    assert payload["card_update_count"] == 0


def test_forbidden_install_surfaces_absent() -> None:
    """
    Proves that no forbidden install/patch surfaces exist in the repo root.
    Evidence: .sisyphus/evidence/plan-7/task-6-forbidden-surfaces.txt
    """
    forbidden_files = [
        "install.sh",
        "check.sh",
        "update.sh",
        "uninstall.sh",
        "run.py.patch",
    ]
    forbidden_dirs = [
        "feishu_card_build",
    ]

    found: list[str] = []
    for f in forbidden_files:
        if (ROOT / f).exists():
            found.append(f)
    for d in forbidden_dirs:
        if (ROOT / d).exists():
            found.append(f"{d}/")

    # Save evidence
    evidence_path = ROOT / ".sisyphus" / "evidence" / "plan-7" / "task-6-forbidden-surfaces.txt"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    _ = evidence_path.write_text(f"forbidden_surfaces={json.dumps(found)}", encoding="utf-8")

    assert found == [], f"Forbidden surfaces found: {found}"



def test_runtime_bridge_harness_requires_live_env_guard(tmp_path: Path) -> None:
    db_path = tmp_path / "bridge.sqlite"
    evidence_dir = tmp_path / "harness"
    command = [
        str(PYTHON),
        "-m",
        "feishu_messaging_card_builder.cli",
        "runtime-bridge",
        "harness",
        "--fixture",
        str(MINIMAL_FIXTURE),
        "--db",
        str(db_path),
        "--delivery-mode",
        "controlled-dual",
        "--require-live-env",
        "--evidence-dir",
        str(evidence_dir),
    ]
    env = dict(os.environ)
    _ = env.pop("FEISHU_APP_ID", None)
    _ = env.pop("FEISHU_APP_SECRET", None)

    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=env)
    payload = cast(dict[str, object], json.loads((evidence_dir / "summary.json").read_text(encoding="utf-8")))

    assert result.returncode == 1
    assert "FEISHU_APP_ID" in result.stderr
    assert "FEISHU_APP_SECRET" in result.stderr
    assert payload["credential_check"] == "missing"
    assert payload["live"] is False
    assert payload["card_create_count"] == 0
    assert payload["card_send_count"] == 0
