# pyright: reportMissingTypeStubs=false
"""Test-only runtime bridge policy checks."""

from __future__ import annotations

import pytest

from feishu_messaging_card_builder.runtime_bridge import (
    CredentialGuard,
    DeliveryMode,
    check_live_credentials,
    normalize_delivery_mode,
    should_create_or_send_cards,
    should_record_native_delivery,
)


def test_controlled_dual_requires_explicit_mode() -> None:
    assert normalize_delivery_mode(None) is DeliveryMode.DEFAULT
    assert should_record_native_delivery(None) is True
    assert should_create_or_send_cards(None) is False
    assert should_create_or_send_cards("default") is False
    assert should_create_or_send_cards("controlled-dual") is True


def test_missing_credentials_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)

    ok, missing_keys = check_live_credentials()
    message = CredentialGuard.diagnostic_message()

    assert ok is False
    assert missing_keys == ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]
    assert "FEISHU_APP_ID" in message
    assert "FEISHU_APP_SECRET" in message
    assert "app-id" not in message
    assert "app-secret" not in message


def test_disabled_mode_zero_operations() -> None:
    assert normalize_delivery_mode("disabled") is DeliveryMode.DISABLED
    assert should_record_native_delivery("disabled") is True
    assert should_create_or_send_cards("disabled") is False
