from __future__ import annotations

import os
from enum import StrEnum
from typing import Final


class DeliveryMode(StrEnum):
    DISABLED = "disabled"
    DEFAULT = "default"
    CONTROLLED_DUAL = "controlled-dual"


LIVE_CREDENTIAL_ENV_KEYS: Final[tuple[str, str]] = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
)


def normalize_delivery_mode(mode: str | None) -> DeliveryMode:
    if mode is None or not mode.strip():
        return DeliveryMode.DEFAULT

    normalized = mode.strip().lower().replace("_", "-")
    try:
        return DeliveryMode(normalized)
    except ValueError as exc:  # pragma: no cover - defensive guard
        valid_modes = ", ".join(item.value for item in DeliveryMode)
        raise ValueError(f"Unsupported delivery mode: {mode!r}. Expected one of: {valid_modes}") from exc


def should_record_native_delivery(mode: str | None) -> bool:
    _ = normalize_delivery_mode(mode)
    return True


def should_create_or_send_cards(mode: str | None) -> bool:
    return normalize_delivery_mode(mode) is DeliveryMode.CONTROLLED_DUAL


def _missing_live_credential_keys() -> list[str]:
    missing: list[str] = []
    for key in LIVE_CREDENTIAL_ENV_KEYS:
        value = os.environ.get(key)
        if value is None or not value.strip():
            missing.append(key)
    return missing


def _redacted_credential_diagnostic(missing_keys: list[str]) -> str:
    if not missing_keys:
        return ""
    keys = ", ".join(missing_keys)
    return f"Missing Feishu live credentials in environment: {keys}"


def check_live_credentials() -> tuple[bool, list[str]]:
    missing_keys = _missing_live_credential_keys()
    return not missing_keys, missing_keys


class CredentialGuard:
    @staticmethod
    def check_live_credentials() -> tuple[bool, list[str]]:
        return check_live_credentials()

    @staticmethod
    def diagnostic_message() -> str:
        ok, missing_keys = check_live_credentials()
        if ok:
            return ""
        return _redacted_credential_diagnostic(missing_keys)
