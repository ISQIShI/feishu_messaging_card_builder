# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import pytest

from feishu_messaging_card_builder.parser import InvalidFinalReplyError, parse_final_reply
from feishu_messaging_card_builder.renderer import (
    OversizeCardError,
    UnsupportedContentError,
    render_card_json,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8")))


def get_element_id(card: dict[str, object]) -> str:
    body = cast(dict[str, object], card["body"])
    elements = cast(list[dict[str, object]], body["elements"])
    element_id = elements[0]["element_id"]
    assert isinstance(element_id, str)
    return element_id


def test_render_card_json_happy_path_matches_expected_structure() -> None:
    parsed = parse_final_reply(load_fixture("hermes_final_reply.json"))

    assert render_card_json(parsed) == {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "Reply from feishu session sess-001",
            }
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "element_id": "e8a02edcf6c4d19a",
                    "content": (
                        "Hermes completed the request and prepared the final reply.\n\n"
                        "Highlights:\n"
                        "- Confirmed websocket-only delivery scope\n"
                        "- Kept the card entity lifecycle intact\n"
                        "- Preserved deterministic update behavior\n\n"
                        "```python\n"
                        "def summarize(items: list[str]) -> str:\n"
                        "    return ' / '.join(items)\n"
                        "```"
                    ),
                }
            ]
        },
    }


def test_render_card_json_rejects_unsupported_attachment_fixture() -> None:
    parsed = parse_final_reply(load_fixture("hermes_unsupported_attachment.json"))

    with pytest.raises(UnsupportedContentError, match="attachments"):
        _ = render_card_json(parsed)


def test_render_card_json_rejects_oversize_fixture() -> None:
    parsed = parse_final_reply(load_fixture("hermes_oversize_reply.json"))

    with pytest.raises(OversizeCardError, match="exceeding"):
        _ = render_card_json(parsed)


def test_element_ids_are_stable_for_same_input() -> None:
    parsed = parse_final_reply(load_fixture("hermes_final_reply.json"))
    duplicate = parse_final_reply(load_fixture("hermes_final_reply_duplicate.json"))

    first_card = render_card_json(parsed)
    second_card = render_card_json(parsed)
    duplicate_card = render_card_json(duplicate)

    first_id = get_element_id(first_card)
    second_id = get_element_id(second_card)
    duplicate_id = get_element_id(duplicate_card)

    assert first_id == second_id == duplicate_id
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,19}", first_id)


def test_rendered_card_uses_v2_schema_and_update_multi() -> None:
    parsed = parse_final_reply(load_fixture("hermes_final_reply.json"))
    card = render_card_json(parsed)
    config = cast(dict[str, object], card["config"])

    assert card["schema"] == "2.0"
    assert config["update_multi"] is True


def test_parse_final_reply_rejects_missing_required_fields() -> None:
    fixture = load_fixture("hermes_final_reply.json")
    _ = fixture.pop("content_markdown")

    with pytest.raises(InvalidFinalReplyError, match="content_markdown"):
        _ = parse_final_reply(fixture)
