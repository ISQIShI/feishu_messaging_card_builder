"""CLI 入口实现。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .builder import CardBuilder, build_streaming_card_payload
from .config import resolve_builder_kwargs, resolve_context_window


def load_payload(path: str) -> dict[str, Any]:
    payload_path = Path(path)
    if not payload_path.exists():
        raise FileNotFoundError(f"输入文件不存在：{payload_path}")
    return json.loads(payload_path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON 载荷文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅构建卡片，不实际发送")
    args = parser.parse_args(argv)

    try:
        payload = load_payload(args.input)
        chat_id = str(payload.get("chat_id") or "").strip()
        if not chat_id:
            raise RuntimeError("缺少 chat_id")

        builder = CardBuilder(**resolve_builder_kwargs(payload))
        cards = builder.build_cards(payload, context_window=resolve_context_window(payload))
        if not args.dry_run:
            raise RuntimeError("该脚本只负责构建卡片 JSON；实际发送由 Hermes 的 FeishuAdapter 完成")
        result = {"cards": cards}
        if payload.get("enable_streaming"):
            streaming_payload = build_streaming_card_payload(cards)
            if streaming_payload:
                result["streaming"] = streaming_payload
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
