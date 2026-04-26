from __future__ import annotations

from typing import Any


def format_seconds(value: Any) -> str:
    try:
        seconds = float(value or 0)
    except Exception:
        seconds = 0.0
    if seconds < 60:
        return f"{int(seconds)}s" if seconds.is_integer() else f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remain = int(round(seconds % 60))
    return f"{minutes}m {remain}s" if remain else f"{minutes}m"


def format_token_compact(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def pct_color(pct: float) -> str:
    if pct < 35:
        return "green"
    if pct < 60:
        return "yellow"
    if pct < 80:
        return "orange"
    return "red"


def extract_reasoning_effort(payload: dict[str, Any]) -> str:
    value = payload.get("reasoning_effort")
    if value is None:
        return ""
    return str(value).strip().lower()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def build_footer(payload: dict[str, Any], context_window: int) -> str:
    provider = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "unknown")
    reasoning_effort = extract_reasoning_effort(payload)
    model_part = f"{model} ({reasoning_effort})" if reasoning_effort else model
    model_part = f"{provider} · {model_part}" if provider else model_part
    api_calls = _safe_int(payload.get("api_calls"))
    line1 = f"耗时 {format_seconds(payload.get('response_time_seconds'))} · {model_part} · 调用API {api_calls} 次"

    input_tokens = _safe_int(payload.get("_feishu_turn_input_tokens") or payload.get("input_tokens"))
    output_tokens = _safe_int(payload.get("_feishu_turn_output_tokens") or payload.get("output_tokens"))
    cache_read_tokens = _safe_int(payload.get("_feishu_turn_cache_read_tokens") or payload.get("cache_read_tokens"))
    line2_parts = [
        f"输入 {format_token_compact(input_tokens)}",
        f"输出 {format_token_compact(output_tokens)}",
        f"缓存读 {format_token_compact(cache_read_tokens)}",
    ]

    used = _safe_int(payload.get("last_prompt_tokens"))

    total = int(context_window or 0)
    if used > 0 and total > 0:
        pct = max(0.0, min(100.0, used / total * 100))
        filled = max(0, min(10, round(pct / 10)))
        bar = "█" * filled + "░" * (10 - filled)
        pct_str = f"{pct:.1f}%" if not pct.is_integer() else f"{int(pct)}%"
        line2_parts.append(
            f"上下文 {format_token_compact(used)}/{format_token_compact(total)} "
            f"<text_tag color='{pct_color(pct)}'>[{bar}] {pct_str}</text_tag>"
        )
    elif used > 0:
        line2_parts.append(f"上下文 {format_token_compact(used)}")
    return line1 + "\n" + " · ".join(line2_parts)
