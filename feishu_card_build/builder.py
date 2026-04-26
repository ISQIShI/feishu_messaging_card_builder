from __future__ import annotations

import copy
import json
import re
from typing import Any

from .content import balance_code_fence, clean_response, compact_blank_lines
from .feishu_elements import (
    build_hr,
    build_lark_md_block,
    build_markdown,
    build_table_from_markdown,
    build_thinking_panel,
    build_tools_panel,
)
from .footer import build_footer
from .parsing import parse_response, iter_markdown_blocks

STATUS_PRESENTATIONS: dict[str, tuple[str, str, str]] = {
    "thinking": ("思考中", "blue", ""),
    "completed": ("已完成", "green", "已完成"),
    "ended": ("已结束", "grey", "已结束"),
    "": ("", "blue", ""),
}


def _normalize_tool_panel_content(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    entries = [chunk.strip() for chunk in re.split(r"\n{2,}(?=- `)", raw) if chunk and chunk.strip()]
    if not entries:
        return raw

    normalized: list[str] = []
    for entry in entries:
        lines = [line.rstrip() for line in entry.splitlines()]
        if not lines:
            continue
        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if header.startswith("- `"):
            title = header[2:].strip()
            block = f"**{title}**"
            if body:
                block += f"\n\n{body}"
            normalized.append(block)
        else:
            normalized.append(entry)
    return "\n\n---\n\n".join(normalized).strip()


def _normalize_reasoning_content(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    return compact_blank_lines(raw)


def _split_compact_group(items: list[str], max_chars: int) -> list[str]:
    if not items:
        return []
    groups: list[str] = []
    current: list[str] = []
    current_len = 0
    for item in items:
        item = item.strip()
        if not item:
            continue
        item_len = len(item) + (2 if current else 0)
        if current and current_len + item_len > max_chars:
            groups.append("\n\n".join(current).strip())
            current = [item]
            current_len = len(item)
            continue
        current.append(item)
        current_len += item_len
    if current:
        groups.append("\n\n".join(current).strip())
    return groups


def _summarize_tool_payload(value: Any) -> Any:
    if isinstance(value, dict):
        preferred_keys = ["id", "command", "action", "path", "ref", "url", "query", "key", "name", "status"]
        summary: dict[str, Any] = {}
        for key in preferred_keys:
            if key in value and value[key] not in (None, "", [], {}):
                summary[key] = _summarize_tool_payload(value[key])
            if len(summary) >= 2:
                break
        if not summary:
            for key, item in value.items():
                if item in (None, "", [], {}):
                    continue
                summary[key] = _summarize_tool_payload(item)
                if len(summary) >= 2:
                    break
        return summary or {"keys": len(value)}
    if isinstance(value, list):
        items = [_summarize_tool_payload(item) for item in value[:3]]
        if len(value) > 3:
            items.append(f"…{len(value) - 3} more")
        return items
    if isinstance(value, str):
        return value if len(value) <= 48 else f"{value[:45]}…"
    return value


def _compact_tools_payload_for_feishu(text: str, max_group_chars: int = 800) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    entries = [chunk.strip() for chunk in re.split(r"\n{2,}(?=- `)", raw) if chunk and chunk.strip()]
    if not entries:
        return raw

    compact_mode = len(entries) > 20 or len(raw) > 8000
    simplified: list[str] = []
    for entry in entries:
        lines = [line.rstrip() for line in entry.splitlines() if line.strip()]
        if not lines:
            continue
        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if not header.startswith("- `"):
            simplified.append(entry)
            continue

        tool_name_match = re.match(r"-\s+(`[^`]+`)", header)
        tool_name = tool_name_match.group(1) if tool_name_match else header[2:].strip()
        compact_json = re.search(r"```json\n([\s\S]*?)\n```", body)
        if compact_json:
            payload = compact_json.group(1).strip()
            if compact_mode:
                try:
                    compact_obj = json.loads(payload)
                except Exception:
                    compact_repr = payload if len(payload) <= 80 else f"{payload[:77]}…"
                else:
                    compact_repr = json.dumps(_summarize_tool_payload(compact_obj), ensure_ascii=False)
                simplified.append(f"**{tool_name}**\n```json\n{compact_repr}\n```")
            else:
                simplified.append(f"**{tool_name}**\n```json\n{payload}\n```")
            continue

        simplified.append(f"**{tool_name}**\n{body}" if body else f"**{tool_name}**")

    groups = _split_compact_group(simplified, max_group_chars)
    return "\n\n---\n\n".join(group.strip() for group in groups if group.strip()).strip() if groups else raw


class CardBuilder:
    def __init__(
        self,
        *,
        body_chunk_limit: int = 3200,
        reasoning_max_length: int = 1800,
        tools_max_length: int = 1800,
        max_card_text_length: int = 6000,
        overflow_mode: str = "truncate",
        tool_display_mode: str = "card_panel",
    ):
        self.body_chunk_limit = body_chunk_limit
        self.reasoning_max_length = reasoning_max_length
        self.tools_max_length = tools_max_length
        self.max_card_text_length = max_card_text_length
        self.overflow_mode = overflow_mode
        self.tool_display_mode = tool_display_mode

    def build_cards(self, payload: dict[str, Any], *, context_window: int = 0) -> list[dict[str, Any]]:
        response = clean_response(str(payload.get("response") or ""))
        parsed = parse_response(response)
        payload_tools = clean_response(str(payload.get("tools") or "")).strip()
        if payload_tools and not parsed.tools:
            parsed.tools = payload_tools

        cfg = payload.get("builder_config") if isinstance(payload.get("builder_config"), dict) else {}
        length_cfg = cfg.get("length_protection") if isinstance(cfg.get("length_protection"), dict) else {}
        max_card_text_length = self._resolve_positive_int(length_cfg.get("max_card_text_length"), self.max_card_text_length)
        overflow_mode = str(length_cfg.get("overflow_mode") or self.overflow_mode).strip().lower()
        if overflow_mode not in {"truncate", "split_cards"}:
            overflow_mode = self.overflow_mode

        tool_display_mode = str(cfg.get("tool_display_mode") or self.tool_display_mode).strip().lower()
        if tool_display_mode not in {"card_panel", "native"}:
            tool_display_mode = self.tool_display_mode

        raw_tools = _compact_tools_payload_for_feishu(parsed.tools, max_group_chars=max(240, min(800, max_card_text_length // 2))) if parsed.tools else ""
        tools = _normalize_tool_panel_content(raw_tools) if raw_tools else ""
        if tool_display_mode == "native":
            tools = ""
        raw_reasoning = str(payload.get("last_reasoning") or payload.get("reasoning") or parsed.reasoning or "").strip()
        reasoning = _normalize_reasoning_content(raw_reasoning)
        footer_text = parsed.footer or build_footer(payload, context_window)
        status_line = STATUS_PRESENTATIONS.get(parsed.status, STATUS_PRESENTATIONS[""])[2]
        body_limit = min(self.body_chunk_limit, max(300, max_card_text_length - 800))
        body_chunks = self._split_body(parsed.body, chunk_limit=body_limit)

        if overflow_mode == "split_cards":
            return self._build_split_cards(
                body_chunks=body_chunks,
                tools=tools,
                reasoning=reasoning,
                footer_text=footer_text,
                status_line=status_line,
                max_card_text_length=max_card_text_length,
            )
        return self._build_truncate_cards(
            body_chunks=body_chunks,
            tools=tools,
            reasoning=reasoning,
            footer_text=footer_text,
            status_line=status_line,
            max_card_text_length=max_card_text_length,
            raw_tools=raw_tools,
        )

    def _build_truncate_cards(
        self,
        *,
        body_chunks: list[str],
        tools: str,
        reasoning: str,
        footer_text: str,
        status_line: str,
        max_card_text_length: int,
        raw_tools: str,
    ) -> list[dict[str, Any]]:
        scenarios = [
            (tools, reasoning),
            (self._limit_text(tools, self.tools_max_length // 2), self._limit_text(reasoning, self.reasoning_max_length // 2)),
        ]
        for scenario_tools, scenario_reasoning in scenarios:
            cards = self._compose_cards(
                body_chunks,
                tools=scenario_tools,
                reasoning=scenario_reasoning,
                footer_text=footer_text,
                status_line=status_line,
            )
            if self._cards_within_limit(cards, max_card_text_length):
                return cards

        panel_spill_cards = self._compose_cards_with_separate_panels(
            body_chunks=body_chunks,
            raw_tools=raw_tools,
            reasoning=self._limit_text(reasoning, self.reasoning_max_length // 2),
            footer_text=footer_text,
            status_line=status_line,
            max_card_text_length=max_card_text_length,
        )
        if panel_spill_cards:
            return panel_spill_cards

        return self._compose_cards(body_chunks, tools="", reasoning="", footer_text=footer_text, status_line=status_line)

    def _build_split_cards(
        self,
        *,
        body_chunks: list[str],
        tools: str,
        reasoning: str,
        footer_text: str,
        status_line: str,
        max_card_text_length: int,
    ) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        panel_limit = max(max_card_text_length, 4500)
        cards.extend(self._panel_cards(tools, title="🛠️ 工具调用", max_length=self.tools_max_length, per_card_limit=panel_limit))
        cards.extend(self._panel_cards(reasoning, title="💭 思考过程", max_length=self.reasoning_max_length, per_card_limit=panel_limit))
        cards.extend(self._compose_cards(body_chunks, tools="", reasoning="", footer_text=footer_text, status_line=status_line))
        return cards

    def _compose_cards_with_separate_panels(
        self,
        *,
        body_chunks: list[str],
        raw_tools: str,
        reasoning: str,
        footer_text: str,
        status_line: str,
        max_card_text_length: int,
    ) -> list[dict[str, Any]]:
        body_cards = self._compose_cards(body_chunks, tools="", reasoning="", footer_text=footer_text, status_line=status_line)
        if not self._cards_within_limit(body_cards, max_card_text_length):
            return []

        tool_limits = [self.tools_max_length // 4, self.tools_max_length // 6, self.tools_max_length // 8]
        reasoning_limits = [self.reasoning_max_length // 4, self.reasoning_max_length // 6, self.reasoning_max_length // 8]

        for tool_limit, reasoning_limit in zip(tool_limits, reasoning_limits):
            cards: list[dict[str, Any]] = []
            cards.extend(self._panel_cards(raw_tools, title="🛠️ 工具调用", max_length=max(200, tool_limit), per_card_limit=max_card_text_length))
            cards.extend(self._panel_cards(reasoning, title="💭 思考过程", max_length=max(200, reasoning_limit), per_card_limit=max_card_text_length))
            if any(self._card_text_length(card) > max_card_text_length for card in cards):
                continue
            cards.extend(body_cards)
            return cards

        return []

    def _panel_cards(self, content: str, *, title: str, max_length: int, per_card_limit: int) -> list[dict[str, Any]]:
        text = str(content or "").strip()
        if not text:
            return []
        raw_blocks = [block.strip() for block in re.split(r"\n\n---\n\n", text) if block.strip()]
        if not raw_blocks:
            raw_blocks = [text]

        content_budget = max(200, per_card_limit - 350)
        blocks: list[str] = []
        for block in raw_blocks:
            blocks.extend(self._split_panel_group_for_card(block, max_chars=min(max_length, content_budget)))

        groups: list[str] = []
        current = ""
        for block in blocks:
            candidate = f"{current}\n\n---\n\n{block}".strip() if current else block
            preview = self._make_card([self._build_panel(title=title, content=candidate, max_length=min(max_length, content_budget))])
            if current and self._card_text_length(preview) > per_card_limit:
                groups.append(current)
                current = block
            else:
                current = candidate
        if current:
            groups.append(current)

        cards: list[dict[str, Any]] = []
        for group in groups:
            limited = self._limit_text(group, content_budget)
            cards.append(self._make_card([self._build_panel(title=title, content=limited, max_length=min(max_length, content_budget))]))
        return cards

    def _split_panel_group_for_card(self, block: str, *, max_chars: int) -> list[str]:
        value = str(block or "").strip()
        if not value:
            return []
        if len(value) <= max_chars:
            return [value]

        lines = value.splitlines()
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            piece = len(line) + (1 if current else 0)
            if current and current_len + piece > max_chars:
                chunks.append("\n".join(current).strip())
                current = [line]
                current_len = len(line)
                continue
            if not current and len(line) > max_chars:
                start = 0
                while start < len(line):
                    chunks.append(line[start:start + max_chars].strip())
                    start += max_chars
                current = []
                current_len = 0
                continue
            current.append(line)
            current_len += piece
        if current:
            chunks.append("\n".join(current).strip())
        return [chunk for chunk in chunks if chunk]

    def _compose_cards(
        self,
        body_chunks: list[str],
        *,
        tools: str,
        reasoning: str,
        footer_text: str,
        status_line: str,
    ) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        total = len(body_chunks)
        for index, chunk in enumerate(body_chunks, start=1):
            elements: list[dict[str, Any]] = []
            if index == 1:
                if tools:
                    elements.append(self._build_panel(title="🛠️ 工具调用", content=tools, max_length=self.tools_max_length))
                if reasoning:
                    elements.append(self._build_panel(title="💭 思考过程", content=reasoning, max_length=self.reasoning_max_length))
            elements.extend(self._build_body_elements(chunk))
            if index == total:
                elements.extend(self._build_footer_elements(footer_text, status_line))
            cards.append(self._make_card(elements))
        return cards

    def _build_panel(self, *, title: str, content: str, max_length: int) -> dict[str, Any]:
        if title == "🛠️ 工具调用":
            return build_tools_panel(content, max_length=max_length)
        return build_thinking_panel(content, max_length=max_length)

    def _make_card(self, elements: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "schema": "2.0",
            "config": {"width_mode": "fill"},
            "body": {"elements": elements or [build_markdown(" ")]},
        }

    def _cards_within_limit(self, cards: list[dict[str, Any]], max_card_text_length: int) -> bool:
        return all(self._card_text_length(card) <= max_card_text_length for card in cards)

    def _card_text_length(self, card: dict[str, Any]) -> int:
        return len(json.dumps(card, ensure_ascii=False))

    def _limit_text(self, text: str, max_chars: int) -> str:
        value = str(text or "").strip()
        if not value or max_chars <= 0 or len(value) <= max_chars:
            return value
        truncated = value[:max_chars].rstrip()
        if "\n\n---\n\n" in truncated:
            truncated = truncated.rsplit("\n\n---\n\n", 1)[0].rstrip()
        elif "\n\n" in truncated:
            truncated = truncated.rsplit("\n\n", 1)[0].rstrip()
        return truncated or value[:max_chars].rstrip()

    @staticmethod
    def _resolve_positive_int(value: Any, default: int) -> int:
        try:
            ivalue = int(value)
            return ivalue if ivalue > 0 else default
        except Exception:
            return default

    def _build_body_elements(self, body: str) -> list[dict[str, Any]]:
        elements: list[dict[str, Any]] = []
        for block in iter_markdown_blocks(body):
            kind = block["kind"]
            content = block.get("content", "")
            if kind == "markdown":
                elements.append(build_markdown(balance_code_fence(content)))
            elif kind == "hr":
                elements.append(build_hr())
            elif kind == "table":
                table = build_table_from_markdown(content)
                if table:
                    elements.append(table)
                else:
                    elements.append(build_markdown(balance_code_fence(content)))
        if not elements:
            elements.append(build_markdown(" "))
        return elements

    def _build_footer_elements(self, footer_text: str, status_line: str) -> list[dict[str, Any]]:
        lines = [line.strip() for line in str(footer_text or "").splitlines() if line and line.strip()]
        if status_line and all(status_line not in line for line in lines):
            lines.insert(0, status_line)
        if not lines:
            return []
        footer_markdown = "\n".join(f"- {line}" for line in lines)
        return [build_hr(), build_lark_md_block(footer_markdown)]

    def _split_body(self, body: str, *, chunk_limit: int | None = None) -> list[str]:
        limit = chunk_limit or self.body_chunk_limit
        if len(body) <= limit:
            return [body]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for block in body.split("\n\n"):
            candidate = block.strip()
            if not candidate:
                continue
            block_len = len(candidate) + (2 if current else 0)
            if current and current_len + block_len > limit:
                chunks.append("\n\n".join(current).strip())
                current = []
                current_len = 0
            if len(candidate) > limit:
                for start in range(0, len(candidate), limit):
                    part = candidate[start : start + limit].strip()
                    if part:
                        chunks.append(part)
                continue
            current.append(candidate)
            current_len += block_len

        tail = "\n\n".join(current).strip()
        if tail:
            chunks.append(tail)
        return chunks or [body[:limit]]


def cards_to_json(cards: list[dict[str, Any]]) -> str:
    return json.dumps({"cards": cards}, ensure_ascii=False)


def build_streaming_card_payload(
    cards: list[dict[str, Any]],
    *,
    element_id: str = "hermes_stream_body",
    print_frequency_ms: int = 70,
    print_step: int = 1,
) -> dict[str, Any]:
    if not cards:
        return {}

    first_card = copy.deepcopy(cards[0])
    if str(first_card.get("schema") or "") != "2.0":
        return {}

    body = first_card.get("body") if isinstance(first_card.get("body"), dict) else {}
    elements = body.get("elements") if isinstance(body.get("elements"), list) else []
    if not elements:
        return {}

    streaming_index = -1
    streaming_content = ""
    for idx, element in enumerate(elements):
        if not isinstance(element, dict) or element.get("tag") != "markdown":
            continue
        content = str(element.get("content") or "")
        if not content.strip():
            continue
        streaming_index = idx
        streaming_content = content
        break

    if streaming_index < 0 or not streaming_content.strip():
        return {}

    stream_element = elements[streaming_index]
    stream_element["element_id"] = element_id
    stream_element["content"] = ""

    config = first_card.get("config") if isinstance(first_card.get("config"), dict) else {}
    config = copy.deepcopy(config)
    config["streaming_mode"] = True
    config["update_multi"] = True
    config.setdefault("width_mode", "fill")
    config["streaming_config"] = {
        "print_frequency_ms": {
            "default": int(print_frequency_ms),
            "android": int(print_frequency_ms),
            "ios": int(print_frequency_ms),
            "pc": int(print_frequency_ms),
        },
        "print_step": {
            "default": int(print_step),
            "android": int(print_step),
            "ios": int(print_step),
            "pc": int(print_step),
        },
        "print_strategy": "delay",
    }
    summary = config.get("summary") if isinstance(config.get("summary"), dict) else {}
    if not summary.get("content"):
        summary["content"] = "正在生成回答..."
    config["summary"] = summary
    first_card["config"] = config

    return {
        "initial_card": first_card,
        "streaming_element_id": element_id,
        "streaming_content": streaming_content,
    }
