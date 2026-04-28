from __future__ import annotations

import subprocess
import sys

import feishu_messaging_card_builder


def test_package_imports() -> None:
    assert feishu_messaging_card_builder.__version__ == "0.1.0"


def test_cli_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "feishu_messaging_card_builder.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "process-fixture" in result.stdout
    assert "update-card" in result.stdout
    assert "inspect-state" in result.stdout
