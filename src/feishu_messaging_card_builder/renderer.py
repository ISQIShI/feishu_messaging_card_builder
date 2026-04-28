"""Card JSON v2 renderer for Phase 1 Hermes final replies."""

from __future__ import annotations

import hashlib
import json
import re

from .parser import ParsedFinalReply

MAX_CARD_BYTES = 30 * 1024
SESSION_PREVIEW_LENGTH = 12

_MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^\)]+\)|<img\b", re.IGNORECASE)
_MARKDOWN_TABLE_SEPARATOR_PATTERN = re.compile(
    r"(?m)^\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$"
)
_TOOL_MARKDOWN_PATTERN = re.compile(
    r"<tool[_-]?(?:call|payload)\b|```(?:json|tool)[^\n]*\n[\s\S]*?\b(?:tool_name|tool_call_id|tool_args)\b",
    re.IGNORECASE,
)


class CardBuildError(Exception):
    """Base class for typed card-rendering failures."""


class UnsupportedContentError(CardBuildError):
    """Raised when the payload contains unsupported Phase 1 content."""


class OversizeCardError(CardBuildError):
    """Raised when the rendered Card JSON exceeds the size limit."""


def render_card_json(parsed: ParsedFinalReply) -> dict[str, object]:
    """Render a validated final reply to a single-element Card JSON v2 payload."""

    _reject_unsupported_content(parsed)

    card: dict[str, object] = {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": _build_title(parsed),
            }
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "element_id": _stable_element_id(parsed.content_markdown),
                    "content": parsed.content_markdown,
                }
            ]
        },
    }

    rendered_bytes = len(
        json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if rendered_bytes > MAX_CARD_BYTES:
        raise OversizeCardError(
            f"rendered card JSON is {rendered_bytes} bytes, exceeding the {MAX_CARD_BYTES}-byte limit"
        )

    return card


def _reject_unsupported_content(parsed: ParsedFinalReply) -> None:
    if parsed.attachments:
        raise UnsupportedContentError("attachments are not supported in Phase 1 final replies")
    if parsed.tool_payloads:
        raise UnsupportedContentError("tool payloads are not supported in Phase 1 final replies")
    if _MARKDOWN_IMAGE_PATTERN.search(parsed.content_markdown):
        raise UnsupportedContentError("markdown images are not supported in Phase 1 final replies")
    if _MARKDOWN_TABLE_SEPARATOR_PATTERN.search(parsed.content_markdown):
        raise UnsupportedContentError("markdown tables are not supported in Phase 1 final replies")
    if _TOOL_MARKDOWN_PATTERN.search(parsed.content_markdown):
        raise UnsupportedContentError("tool payload markdown is not supported in Phase 1 final replies")


def _build_title(parsed: ParsedFinalReply) -> str:
    session_display = parsed.session_key[:SESSION_PREVIEW_LENGTH]
    return f"Reply from {parsed.source_platform} session {session_display}"


def _stable_element_id(content_markdown: str) -> str:
    digest = hashlib.sha256(content_markdown.encode("utf-8")).hexdigest()[:15]
    return f"e{digest}"
