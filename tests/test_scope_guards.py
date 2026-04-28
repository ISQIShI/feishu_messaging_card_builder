from __future__ import annotations

import re
from pathlib import Path

from feishu_messaging_card_builder.feishu_client import FeishuCardClient, MockFeishuTransport

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src" / "feishu_messaging_card_builder"


def _source_files() -> list[Path]:
    return sorted(
        path
        for path in PACKAGE_DIR.rglob("*")
        if path.is_file() and path.suffix in {".py", ".pyi"}
    )


def _collect_pattern_hits(patterns: tuple[str, ...]) -> list[tuple[str, str, int, str]]:
    hits: list[tuple[str, str, int, str]] = []
    compiled_patterns = [re.compile(pattern) for pattern in patterns]

    for path in _source_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            for compiled_pattern in compiled_patterns:
                if compiled_pattern.search(line):
                    hits.append(
                        (
                            str(path.relative_to(ROOT)),
                            compiled_pattern.pattern,
                            line_number,
                            line.strip(),
                        )
                    )
    return hits


def test_no_webhook_surface_exists() -> None:
    forbidden_patterns = (
        r"\bwebhook\b",
        r"/webhooks?\b",
        r"@app\.(?:get|post|put|patch|delete)\(",
        r"\bFastAPI\(",
        r"\bFlask\(",
        r"\bAPIRouter\(",
        r"\bBlueprint\(",
        r"\badd_api_route\(",
    )

    assert _collect_pattern_hits(forbidden_patterns) == []


def test_no_old_removed_files_exist() -> None:
    removed_paths = [
        ROOT / "install.sh",
        ROOT / "check.sh",
        ROOT / "update.sh",
        ROOT / "uninstall.sh",
        ROOT / "run.py.patch",
        ROOT / "feishu_card_build",
    ]

    assert all(not path.exists() for path in removed_paths)


def test_no_hermes_source_modification() -> None:
    forbidden_patterns = (
        r"Hermes/",
        r"gateway/run\.py",
        r"run\.py\.patch",
    )

    assert not (ROOT / "Hermes").exists()
    assert _collect_pattern_hits(forbidden_patterns) == []


def test_no_raw_card_json_send_exposed() -> None:
    client = FeishuCardClient(MockFeishuTransport())

    assert hasattr(client, "create_card")
    assert hasattr(client, "send_card")
    assert hasattr(client, "update_card")
    assert not any(
        hasattr(client, candidate)
        for candidate in ("send_raw", "send_raw_card_json", "send_card_json", "send_message_card")
    )


def test_websocket_only_no_webhook_config() -> None:
    forbidden_patterns = (
        r"--webhook\b",
        r"WEBHOOK(?:_URL|_SECRET|_TOKEN)?",
        r"webhook_url",
        r"callback_url",
        r"request_url",
        r"signing_secret",
        r"verification_token",
        r"x-lark-signature",
        r"/callback\b",
        r"https?://[^\s\"']*webhook",
    )

    assert _collect_pattern_hits(forbidden_patterns) == []
