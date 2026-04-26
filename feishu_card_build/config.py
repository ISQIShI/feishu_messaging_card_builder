from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

DEFAULT_MAX_CARD_TEXT_LENGTH = 6000
DEFAULT_OVERFLOW_MODE = "truncate"
DEFAULT_BODY_CHUNK_LIMIT = 3200
DEFAULT_REASONING_MAX_LENGTH = 1800
DEFAULT_TOOLS_MAX_LENGTH = 1800
DEFAULT_TOOL_DISPLAY_MODE = "card_panel"


def load_gateway_config() -> dict[str, Any]:
    cfg_path = Path.home() / ".hermes" / "config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _resolve_positive_int(value: Any, default: int) -> int:
    try:
        ivalue = int(value)
        return ivalue if ivalue > 0 else default
    except Exception:
        return default


def _builder_config_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = payload.get("builder_config")
    return cfg if isinstance(cfg, dict) else {}


def _builder_config_from_gateway() -> dict[str, Any]:
    cfg = load_gateway_config().get("feishu_messaging_card_builder")
    return cfg if isinstance(cfg, dict) else {}


def resolve_builder_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    gateway_cfg = _builder_config_from_gateway()
    payload_cfg = _builder_config_from_payload(payload)

    gateway_length_cfg = gateway_cfg.get("length_protection") if isinstance(gateway_cfg.get("length_protection"), dict) else {}
    payload_length_cfg = payload_cfg.get("length_protection") if isinstance(payload_cfg.get("length_protection"), dict) else {}

    body_chunk_limit = _resolve_positive_int(payload_cfg.get("body_chunk_limit"), _resolve_positive_int(gateway_cfg.get("body_chunk_limit"), DEFAULT_BODY_CHUNK_LIMIT))
    reasoning_max_length = _resolve_positive_int(payload_cfg.get("reasoning_max_length"), _resolve_positive_int(gateway_cfg.get("reasoning_max_length"), DEFAULT_REASONING_MAX_LENGTH))
    tools_max_length = _resolve_positive_int(payload_cfg.get("tools_max_length"), _resolve_positive_int(gateway_cfg.get("tools_max_length"), DEFAULT_TOOLS_MAX_LENGTH))
    max_card_text_length = _resolve_positive_int(payload_length_cfg.get("max_card_text_length"), _resolve_positive_int(gateway_length_cfg.get("max_card_text_length"), DEFAULT_MAX_CARD_TEXT_LENGTH))

    overflow_mode = str(payload_length_cfg.get("overflow_mode") or gateway_length_cfg.get("overflow_mode") or DEFAULT_OVERFLOW_MODE).strip().lower()
    if overflow_mode not in {"truncate", "split_cards"}:
        overflow_mode = DEFAULT_OVERFLOW_MODE

    tool_display_mode = str(payload_cfg.get("tool_display_mode") or gateway_cfg.get("tool_display_mode") or DEFAULT_TOOL_DISPLAY_MODE).strip().lower()
    if tool_display_mode not in {"card_panel", "native"}:
        tool_display_mode = DEFAULT_TOOL_DISPLAY_MODE

    return {
        "body_chunk_limit": body_chunk_limit,
        "reasoning_max_length": reasoning_max_length,
        "tools_max_length": tools_max_length,
        "max_card_text_length": max_card_text_length,
        "overflow_mode": overflow_mode,
        "tool_display_mode": tool_display_mode,
    }


def resolve_context_window(payload: dict[str, Any]) -> int:
    explicit = payload.get("config_context_length")
    try:
        if explicit is not None and int(explicit) > 0:
            return int(explicit)
    except Exception:
        pass

    model = str(payload.get("model") or "").strip()
    cfg = load_gateway_config()

    model_cfg = cfg.get("model", {})
    if isinstance(model_cfg, dict):
        try:
            context_length = int(model_cfg.get("context_length") or 0)
            if context_length > 0:
                return context_length
        except Exception:
            pass

    custom_providers = cfg.get("custom_providers", [])
    if isinstance(custom_providers, list) and model:
        for provider_cfg in custom_providers:
            if not isinstance(provider_cfg, dict):
                continue
            models = provider_cfg.get("models", {})
            if not isinstance(models, dict):
                continue
            model_meta = models.get(model, {})
            if isinstance(model_meta, dict):
                try:
                    context_length = int(model_meta.get("context_length") or 0)
                    if context_length > 0:
                        return context_length
                except Exception:
                    pass

    try:
        repo = Path.home() / ".hermes" / "hermes-agent"
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from agent.model_metadata import get_model_context_length

        return int(get_model_context_length(model) or 0)
    except Exception:
        return 0
