from __future__ import annotations

import re
from dataclasses import dataclass

from .content import compact_blank_lines

HR_RE = re.compile(r"^\s*[-*_]{3,}\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_MARKDOWN_TABLE_BLOCK_RE = re.compile(
    r"(?ms)(^ *\|.+\|\s*$\n^ *\|(?:[-: ]+\|)+\s*$\n(?:^ *\|.+\|\s*$\n?)*)"
)
_HERMES_REASONING_SECTION_RE = re.compile(
    r"\[\[HERMES_REASONING\]\]\s*([\s\S]*?)\s*\[\[/HERMES_REASONING\]\]",
    re.IGNORECASE,
)
_HERMES_TOOLS_SECTION_RE = re.compile(
    r"\[\[HERMES_TOOLS\]\]\s*([\s\S]*?)\s*\[\[/HERMES_TOOLS\]\]",
    re.IGNORECASE,
)
_HERMES_FOOTER_SECTION_RE = re.compile(
    r"\[\[HERMES_FOOTER\]\]\s*([\s\S]*?)\s*\[\[/HERMES_FOOTER\]\]",
    re.IGNORECASE,
)
_THINK_BLOCK_RE = re.compile(
    r"<(?:think|thinking|reasoning|REASONING_SCRATCHPAD)[^>]*>[\s\S]*?</(?:think|thinking|reasoning|REASONING_SCRATCHPAD)>",
    re.IGNORECASE,
)
_THINK_TAG_RE = re.compile(
    r"</?(?:think|thinking|reasoning|REASONING_SCRATCHPAD)[^>]*>",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(
    r"^\[\[HERMES_STATUS:(thinking|completed|ended)\]\]\s*",
    re.IGNORECASE | re.MULTILINE,
)
_GATEWAY_REASONING_PREFIX_RE = re.compile(
    r"^\s*💭\s*\*\*Reasoning:\*\*\s*```[\s\S]*?```\s*",
    re.IGNORECASE,
)

HEADING_PREFIXES = {
    1: "◆",
    2: "●",
    3: "▷",
    4: "▶",
    5: "○",
    6: "△",
}


@dataclass
class ParsedResponse:
    body: str
    reasoning: str
    tools: str
    footer: str
    status: str


def extract_status_marker(content: str) -> tuple[str, str]:
    text = content or ""
    match = _STATUS_RE.search(text)
    if not match:
        return "", text
    return match.group(1).lower(), text[match.end():].lstrip()


def _extract_marker_section(content: str, pattern: re.Pattern[str]) -> str:
    matches = [match.strip() for match in pattern.findall(content) if match and match.strip()]
    return "\n\n".join(matches).strip()


def _extract_reasoning(content: str) -> str:
    section = _extract_marker_section(content, _HERMES_REASONING_SECTION_RE)
    if section:
        return section
    matches = _THINK_BLOCK_RE.findall(content)
    reasoning_parts = []
    for match in matches:
        text = _THINK_TAG_RE.sub("", match).strip()
        if text:
            reasoning_parts.append(text)
    return "\n\n".join(reasoning_parts)


def _strip_all_markers(content: str) -> str:
    cleaned = content
    cleaned = _HERMES_REASONING_SECTION_RE.sub("", cleaned)
    cleaned = _HERMES_TOOLS_SECTION_RE.sub("", cleaned)
    cleaned = _HERMES_FOOTER_SECTION_RE.sub("", cleaned)
    cleaned = _THINK_BLOCK_RE.sub("", cleaned)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = _GATEWAY_REASONING_PREFIX_RE.sub("", cleaned, count=1)
    return compact_blank_lines(cleaned)


def parse_response(content: str) -> ParsedResponse:
    status, body = extract_status_marker(content)
    reasoning = _extract_reasoning(body)
    tools = _extract_marker_section(body, _HERMES_TOOLS_SECTION_RE)
    footer = _extract_marker_section(body, _HERMES_FOOTER_SECTION_RE)
    stripped_body = _strip_all_markers(body)
    return ParsedResponse(
        body=stripped_body,
        reasoning=reasoning,
        tools=tools,
        footer=footer,
        status=status,
    )


def extract_title(text: str, fallback: str = "Hermes 回复", max_length: int = 28) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        line = re.sub(r"~~([^~]+)~~", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        return line[:max_length] or fallback
    return fallback


def iter_markdown_blocks(md_text: str):
    if not md_text:
        return

    has_table = bool(_MARKDOWN_TABLE_BLOCK_RE.search(md_text))
    pending_lines: list[str] = []
    lines = md_text.splitlines()
    i = 0

    def flush_markdown():
        nonlocal pending_lines
        text = "\n".join(pending_lines).strip()
        pending_lines = []
        if text:
            text = re.sub(r"</?u[^>]*>", "", text)
            yield {"kind": "markdown", "content": text}

    while i < len(lines):
        line = lines[i]

        if HR_RE.match(line):
            yield from flush_markdown()
            yield {"kind": "hr"}
            i += 1
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            yield from flush_markdown()
            level = len(heading_match.group(1))
            content = re.sub(r"</?u[^>]*>", "", heading_match.group(2).strip())
            prefix = HEADING_PREFIXES.get(level, "●")
            yield {"kind": "markdown", "content": f"{prefix} **{content}**"}
            i += 1
            continue

        if has_table and "|" in line and not line.strip().startswith("```"):
            table_lines = []
            while i < len(lines) and ("|" in lines[i] or lines[i].strip() == ""):
                if lines[i].strip():
                    table_lines.append(lines[i])
                i += 1
            if len(table_lines) >= 2:
                yield from flush_markdown()
                yield {"kind": "table", "content": "\n".join(table_lines)}
                continue

        pending_lines.append(line)
        i += 1

    yield from flush_markdown()
