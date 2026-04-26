from __future__ import annotations

import re

MEDIA_DIRECTIVE_RE = re.compile(r"^\s*(\[\[audio_as_voice\]\]\s*)?MEDIA:\S+\s*$", re.MULTILINE)
CODE_FENCE_RE = re.compile(r"```")


def clean_response(text: str) -> str:
    cleaned = MEDIA_DIRECTIVE_RE.sub("", text or "").strip()
    return cleaned or "（空内容）"


def balance_code_fence(text: str) -> str:
    return text + "\n```" if len(CODE_FENCE_RE.findall(text)) % 2 else text


def compact_blank_lines(text: str) -> str:
    lines = text.splitlines()
    compact: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip():
            compact.append(line.rstrip())
            blank_count = 0
        else:
            blank_count += 1
            if blank_count <= 1:
                compact.append("")
    return "\n".join(compact).strip()
