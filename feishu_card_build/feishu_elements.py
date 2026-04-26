from __future__ import annotations

import re
from typing import Any

from .content import balance_code_fence


def build_markdown(content: str, *, text_size: str = "normal") -> dict[str, Any]:
    element: dict[str, Any] = {"tag": "markdown", "content": content}
    if text_size != "normal":
        element["text_size"] = text_size
    return element


def build_hr() -> dict[str, Any]:
    return {"tag": "hr"}


def build_lark_md_block(content: str) -> dict[str, Any]:
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": content,
        },
    }


def _split_panel_blocks(content: str, max_length: int) -> list[str]:
    text = str(content or "").strip()
    if not text:
        return [""]

    logical_blocks = [block.strip() for block in re.split(r"\n\n---\n\n", text) if block and block.strip()]
    if not logical_blocks:
        logical_blocks = [text]

    raw_blocks: list[str] = []
    for index, block in enumerate(logical_blocks):
        if index < len(logical_blocks) - 1:
            raw_blocks.append(f"{block}\n\n---")
        else:
            raw_blocks.append(block)

    blocks: list[str] = []
    for block in raw_blocks:
        if max_length <= 0 or len(block) <= max_length:
            blocks.append(block)
            continue

        lines = block.splitlines()
        current: list[str] = []
        current_len = 0
        fence_open = False
        for line in lines:
            line_len = len(line) + (1 if current else 0)
            if current and current_len + line_len > max_length:
                chunk = "\n".join(current)
                if fence_open:
                    chunk += "\n```"
                blocks.append(balance_code_fence(chunk))
                current = ["```" if fence_open else "", line] if fence_open else [line]
                current = [entry for entry in current if entry != ""]
                current_len = sum(len(entry) for entry in current) + max(0, len(current) - 1)
                continue

            current.append(line)
            current_len += line_len
            if line.strip().startswith("```"):
                fence_open = not fence_open

        if current:
            blocks.append(balance_code_fence("\n".join(current)))

    return blocks or [text]


def build_collapsible_panel(content: str, *, title: str, max_length: int) -> dict[str, Any]:
    blocks = _split_panel_blocks(content, max_length)
    return {
        "tag": "collapsible_panel",
        "expanded": False,
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title,
                "text_color": "grey",
                "text_size": "notation",
            },
            "vertical_align": "center",
            "icon": {
                "tag": "standard_icon",
                "token": "down-small-outlined",
                "color": "grey",
                "size": "16px 16px",
            },
            "icon_position": "right",
            "icon_expanded_angle": -180,
        },
        "border": {
            "color": "grey",
            "corner_radius": "5px",
        },
        "vertical_spacing": "4px",
        "padding": "8px 8px 8px 8px",
        "elements": [build_markdown(balance_code_fence(block), text_size="notation") for block in blocks],
    }


def build_thinking_panel(content: str, *, max_length: int = 3500) -> dict[str, Any]:
    return build_collapsible_panel(content, title="💭 思考过程", max_length=max_length)


def build_tools_panel(content: str, *, max_length: int = 3500) -> dict[str, Any]:
    return build_collapsible_panel(content, title="🛠️ 工具调用", max_length=max_length)


def parse_markdown_table(md_text: str) -> tuple[list[str], list[list[str]]] | None:
    lines = [line.strip() for line in md_text.strip().split("\n") if "|" in line and not line.strip().startswith("```")]
    if len(lines) < 2:
        return None

    headers = [cell.strip() for cell in lines[0].split("|") if cell.strip()]
    rows: list[list[str]] = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if len(cells) == len(headers):
            rows.append(cells)
    if not headers or not rows:
        return None
    return headers, rows


def build_table_from_markdown(md_text: str) -> dict[str, Any] | None:
    parsed = parse_markdown_table(md_text)
    if not parsed:
        return None
    headers, rows = parsed
    columns = [{"name": f"c{i}", "display_name": header} for i, header in enumerate(headers)]
    table_rows = []
    for row in rows:
        table_rows.append({f"c{i}": value for i, value in enumerate(row)})
    return {"tag": "table", "columns": columns, "rows": table_rows}
