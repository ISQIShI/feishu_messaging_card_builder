from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, final

from .bridge import BridgeOrchestrator, ProcessResult
from .runtime_event import EventClassification, NormalizedRuntimeEvent, parse_runtime_event
from .state import Status


class DeliveryMode(StrEnum):
    DISABLED = "disabled"
    DEFAULT = "default"
    CONTROLLED_DUAL = "controlled-dual"


LIVE_CREDENTIAL_ENV_KEYS: Final[tuple[str, str]] = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
)
_SUPPORTED_RECIPIENT_TYPE: Final[str] = "open_id"
_RECORDED_NATIVE_ONLY_STATUS: Final[str] = "native_delivery_recorded"


@dataclass(frozen=True, slots=True)
class RuntimeBridgeResult:
    normalized_event_count: int
    native_delivery_recorded: bool
    card_create_count: int
    card_send_count: int
    card_update_count: int
    entity_first: bool
    classification: str
    status: str
    live: bool
    bridge_message_id_sha256: str | None
    card_id_sha256: str | None
    feishu_message_id_sha256: str | None
    hermes_message_id_sha256: str | None
    recipient_id_sha256: str | None
    sequence: int | None
    is_duplicate: bool
    recovery_instruction: str | None


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


@final
class RuntimeBridge:
    _orchestrator: BridgeOrchestrator
    _delivery_mode: DeliveryMode

    def __init__(self, orchestrator: BridgeOrchestrator, delivery_mode: str | DeliveryMode) -> None:
        self._orchestrator = orchestrator
        self._delivery_mode = normalize_delivery_mode(
            delivery_mode.value if isinstance(delivery_mode, DeliveryMode) else delivery_mode
        )

    def process_event(self, event: NormalizedRuntimeEvent) -> RuntimeBridgeResult:
        if event.recipient_type.strip().lower() != _SUPPORTED_RECIPIENT_TYPE:
            return self._result_for_classification(
                classification=EventClassification.UNSUPPORTED,
                event=event,
                status=Status.UNSUPPORTED.value,
                native_delivery_recorded=False,
            )

        if not should_create_or_send_cards(self._delivery_mode.value):
            return self._result_for_classification(
                classification=EventClassification.SUPPORTED,
                event=event,
                status=_RECORDED_NATIVE_ONLY_STATUS,
                native_delivery_recorded=should_record_native_delivery(self._delivery_mode.value),
            )

        process_result = self._orchestrator.process_delivery(event.to_delivery_fixture(), event.recipient_id)
        return self._result_from_process_result(event, process_result)

    def process_payload(self, payload: Mapping[str, object]) -> RuntimeBridgeResult:
        classification, event = parse_runtime_event(dict(payload))
        if classification is EventClassification.SUPPORTED and event is not None:
            return self.process_event(event)
        return self._result_for_payload(classification, payload)

    def _result_from_process_result(
        self,
        event: NormalizedRuntimeEvent,
        process_result: ProcessResult,
    ) -> RuntimeBridgeResult:
        return RuntimeBridgeResult(
            normalized_event_count=1,
            native_delivery_recorded=True,
            card_create_count=self._count_mock_calls(process_result.mock_calls, method="POST", path="/open-apis/cardkit/v1/cards"),
            card_send_count=self._count_mock_calls(process_result.mock_calls, method="POST", path="/open-apis/im/v1/messages"),
            card_update_count=self._count_update_calls(process_result.mock_calls),
            entity_first=True,
            classification=EventClassification.SUPPORTED.value,
            status=process_result.status,
            live=False,
            bridge_message_id_sha256=_sha256_token(process_result.bridge_message_id),
            card_id_sha256=_hash_optional(process_result.card_id),
            feishu_message_id_sha256=_hash_optional(process_result.feishu_message_id),
            hermes_message_id_sha256=_sha256_token(event.hermes_message_id),
            recipient_id_sha256=_sha256_token(event.recipient_id),
            sequence=process_result.sequence,
            is_duplicate=process_result.is_duplicate,
            recovery_instruction=process_result.recovery_instruction,
        )

    def _result_for_payload(
        self,
        classification: EventClassification,
        payload: Mapping[str, object],
    ) -> RuntimeBridgeResult:
        status = (
            Status.UNSUPPORTED.value
            if classification is EventClassification.UNSUPPORTED
            else classification.value
        )
        return RuntimeBridgeResult(
            normalized_event_count=0,
            native_delivery_recorded=False,
            card_create_count=0,
            card_send_count=0,
            card_update_count=0,
            entity_first=True,
            classification=classification.value,
            status=status,
            live=False,
            bridge_message_id_sha256=None,
            card_id_sha256=None,
            feishu_message_id_sha256=None,
            hermes_message_id_sha256=_hash_mapping_string(payload, "hermes_message_id"),
            recipient_id_sha256=_hash_mapping_string(payload, "recipient_id"),
            sequence=None,
            is_duplicate=False,
            recovery_instruction=None,
        )

    def _result_for_classification(
        self,
        *,
        classification: EventClassification,
        event: NormalizedRuntimeEvent,
        status: str,
        native_delivery_recorded: bool,
    ) -> RuntimeBridgeResult:
        return RuntimeBridgeResult(
            normalized_event_count=1,
            native_delivery_recorded=native_delivery_recorded,
            card_create_count=0,
            card_send_count=0,
            card_update_count=0,
            entity_first=True,
            classification=classification.value,
            status=status,
            live=False,
            bridge_message_id_sha256=None,
            card_id_sha256=None,
            feishu_message_id_sha256=None,
            hermes_message_id_sha256=_sha256_token(event.hermes_message_id),
            recipient_id_sha256=_sha256_token(event.recipient_id),
            sequence=None,
            is_duplicate=False,
            recovery_instruction=None,
        )

    @staticmethod
    def _count_mock_calls(mock_calls: list[dict[str, object]], *, method: str, path: str) -> int:
        return sum(
            1
            for call in mock_calls
            if str(call.get("method")) == method and str(call.get("path")) == path
        )

    @staticmethod
    def _count_update_calls(mock_calls: list[dict[str, object]]) -> int:
        return sum(
            1
            for call in mock_calls
            if str(call.get("method")) == "PUT"
            and str(call.get("path", "")).startswith("/open-apis/cardkit/v1/cards/")
        )


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


def _sha256_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_optional(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    return _sha256_token(value)


def _hash_mapping_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return _sha256_token(value)


__all__ = [
    "CredentialGuard",
    "DeliveryMode",
    "LIVE_CREDENTIAL_ENV_KEYS",
    "RuntimeBridge",
    "RuntimeBridgeResult",
    "check_live_credentials",
    "normalize_delivery_mode",
    "should_create_or_send_cards",
    "should_record_native_delivery",
]
