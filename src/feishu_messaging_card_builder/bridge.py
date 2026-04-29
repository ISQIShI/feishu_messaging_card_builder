from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import cast, final
import uuid as uuid_module

from .feishu_client import FeishuApiError, FeishuCardClient, JSONDict
from .parser import ParsedFinalReply, parse_final_reply
from .renderer import render_card_json
from .state import (
    BridgeRecord,
    BridgeStateError,
    BridgeStateManager,
    DeliveryFixture,
    Status,
)

UPDATE_MARKER = "\n\n> Updated by Phase 1 prototype"
_EXPLICIT_REJECTION_PATTERNS = (
    "invalid receive_id",
    "receive_id is invalid",
    "invalid recipient",
    "invalid user",
    "user not found",
    "invalid open_id",
    "open_id is invalid",
    "invalid chat_id",
)
_SENSITIVE_FAILURE_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:[a-z0-9]+_id|tenant_key|app_secret|token|troubleshooter)\b\s*[:=]\s*[^;,\s]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+-]+")
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_LONG_TOKEN_PATTERN = re.compile(r"\b[A-Za-z0-9._~+-]{16,}\b")


@dataclass(slots=True)
class ProcessResult:
    bridge_message_id: str
    card_id: str | None
    feishu_message_id: str | None
    sequence: int
    status: str
    is_duplicate: bool
    mock_calls: list[dict[str, object]]
    recovery_instruction: str | None


@dataclass(slots=True)
class UpdateResult:
    bridge_message_id: str
    previous_sequence: int
    new_sequence: int
    status: str
    mock_calls: list[dict[str, object]]


@final
class BridgeOrchestrationError(RuntimeError):
    """Raised when bridge orchestration cannot safely complete."""

    bridge_message_id: str | None
    card_id: str | None
    status: str | None
    mock_calls: list[dict[str, object]]

    def __init__(
        self,
        message: str,
        *,
        bridge_message_id: str | None = None,
        card_id: str | None = None,
        status: str | None = None,
        mock_calls: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.bridge_message_id = bridge_message_id
        self.card_id = card_id
        self.status = status
        self.mock_calls = mock_calls or []


@final
class BridgeOrchestrator:
    """Coordinate parser, renderer, Feishu transport, and SQLite bridge state."""

    _state: BridgeStateManager
    _client: FeishuCardClient
    _parsed_cache: dict[str, ParsedFinalReply]

    def __init__(self, state: BridgeStateManager, client: FeishuCardClient) -> None:
        self._state = state
        self._client = client
        self._parsed_cache = {}

    def process_fixture(self, fixture_path: str | Path, recipient: str) -> ProcessResult:
        parsed = parse_final_reply(self._load_fixture(fixture_path))
        content_hash = self._content_hash(parsed.content_markdown)
        get_or_create_result = self._state.get_or_create(self._delivery_fixture(parsed), content_hash)
        record = get_or_create_result.record
        is_new = get_or_create_result.is_new
        bridge_message_id = record["bridge_message_id"]
        self._parsed_cache[bridge_message_id] = parsed

        if not is_new:
            if get_or_create_result.content_changed:
                return self._process_changed_content(record, parsed, recipient)
            if record["status"] in {Status.SENT.value, Status.UPDATED.value}:
                return self._duplicate_result(record)
            if record["status"] == Status.RECONCILIATION_REQUIRED.value:
                return self._reconciliation_result(record)
            if record["card_id"] and record["status"] in {
                Status.CARD_CREATED.value,
                Status.SEND_PENDING.value,
            }:
                return self._send_existing_card(record, recipient)
            if record["card_id"] and record["status"] == Status.SEND_FAILED.value:
                if self.is_explicit_pre_acceptance_rejection(record["failure_reason"]):
                    return self._send_existing_card(record, recipient)
                return self._reconciliation_required_for_ambiguous_send(record)

        return self._create_and_send_card(record, parsed, recipient)

    def update_card(self, bridge_message_id: str) -> UpdateResult:
        record = self._state.materialize_expired(bridge_message_id)
        if record is None:
            raise BridgeOrchestrationError(
                f"No bridge record found for {bridge_message_id}",
                bridge_message_id=bridge_message_id,
            )

        previous_sequence = int(record["version"])
        if record["status"] == Status.EXPIRED.value:
            return UpdateResult(
                bridge_message_id=bridge_message_id,
                previous_sequence=previous_sequence,
                new_sequence=previous_sequence,
                status=Status.EXPIRED.value,
                mock_calls=[],
            )

        if record["status"] not in {
            Status.SENT.value,
            Status.UPDATED.value,
            Status.UPDATE_FAILED.value,
        }:
            raise BridgeOrchestrationError(
                "Only sent, updated, or update_failed records can be updated",
                bridge_message_id=bridge_message_id,
                card_id=record["card_id"],
                status=record["status"],
            )

        card_id = record["card_id"]
        if not card_id:
            raise BridgeOrchestrationError(
                f"Record {bridge_message_id} is missing card_id",
                bridge_message_id=bridge_message_id,
                status=record["status"],
            )

        parsed = self._rebuild_parsed_reply_from_record(record)
        updated_parsed = self._updated_parsed_reply(parsed)
        updated_card_json = self._render_transport_card_json(updated_parsed)
        new_sequence = previous_sequence + 1
        request_uuid = uuid_module.uuid4().hex
        call_count_before = self._mock_call_count()

        try:
            self._client.update_card(card_id, updated_card_json, new_sequence, request_uuid)
            self._state.update_status(
                bridge_message_id,
                Status.UPDATED,
                sequence=new_sequence,
                version=new_sequence,
                failure_reason=None,
            )
        except FeishuApiError as exc:
            self._state.update_status(
                bridge_message_id,
                Status.UPDATE_FAILED,
                failure_reason=self._format_feishu_error_reason(exc),
            )
            raise BridgeOrchestrationError(
                f"Feishu update failed for {bridge_message_id}",
                bridge_message_id=bridge_message_id,
                card_id=card_id,
                status=Status.UPDATE_FAILED.value,
                mock_calls=self._mock_calls_since(call_count_before),
            ) from exc

        self._parsed_cache[bridge_message_id] = parsed
        return UpdateResult(
            bridge_message_id=bridge_message_id,
            previous_sequence=previous_sequence,
            new_sequence=new_sequence,
            status=Status.UPDATED.value,
            mock_calls=self._mock_calls_since(call_count_before),
        )

    def cache_parsed_reply(self, bridge_message_id: str, parsed: ParsedFinalReply) -> None:
        self._parsed_cache[bridge_message_id] = parsed

    def has_cached_parsed_reply(self, bridge_message_id: str) -> bool:
        return bridge_message_id in self._parsed_cache

    def get_bridge_messages(self) -> list[dict[str, object]]:
        return [dict(record) for record in self._state.list_records(include_sensitive=True)]

    def _create_and_send_card(
        self,
        record: BridgeRecord,
        parsed: ParsedFinalReply,
        recipient: str,
    ) -> ProcessResult:
        bridge_message_id = record["bridge_message_id"]
        call_count_before = self._mock_call_count()

        card_json = self._render_transport_card_json(parsed)
        card_id = record["card_id"]
        if card_id is None:
            card_id = self._client.create_card(card_json)
            self._state.update_status(
                bridge_message_id,
                Status.CARD_CREATED,
                card_id=card_id,
                sequence=1,
                failure_reason=None,
            )

        return self._send_card_and_finalize(
            bridge_message_id=bridge_message_id,
            card_id=card_id,
            sequence=max(int(record["sequence"]), 1),
            recipient=recipient,
            call_count_before=call_count_before,
        )

    def _send_existing_card(self, record: BridgeRecord, recipient: str) -> ProcessResult:
        card_id = record["card_id"]
        if card_id is None:
            raise BridgeOrchestrationError(
                f"Record {record['bridge_message_id']} is missing card_id for retry",
                bridge_message_id=record["bridge_message_id"],
                status=record["status"],
            )

        return self._send_card_and_finalize(
            bridge_message_id=record["bridge_message_id"],
            card_id=card_id,
            sequence=max(int(record["sequence"]), 1),
            recipient=recipient,
            call_count_before=self._mock_call_count(),
        )

    def _send_card_and_finalize(
        self,
        *,
        bridge_message_id: str,
        card_id: str,
        sequence: int,
        recipient: str,
        call_count_before: int,
    ) -> ProcessResult:
        self._state.update_status(
            bridge_message_id,
            Status.SEND_PENDING,
            card_id=card_id,
            sequence=sequence,
            failure_reason=None,
        )

        try:
            feishu_message_id = self._client.send_card(card_id, recipient)
        except FeishuApiError as exc:
            self._state.update_status(
                bridge_message_id,
                Status.SEND_FAILED,
                card_id=card_id,
                sequence=sequence,
                failure_reason=self._format_feishu_error_reason(exc),
            )
            raise BridgeOrchestrationError(
                f"Feishu send failed for {bridge_message_id}; retry with the preserved card_id",
                bridge_message_id=bridge_message_id,
                card_id=card_id,
                status=Status.SEND_FAILED.value,
                mock_calls=self._mock_calls_since(call_count_before),
            ) from exc

        try:
            self._state.update_status(
                bridge_message_id,
                Status.SENT,
                card_id=card_id,
                feishu_message_id=feishu_message_id,
                sequence=sequence,
                version=sequence,
                failure_reason=None,
            )
        except BridgeStateError:
            recovery_instruction = (
                "Card send succeeded but local persistence failed. Mark this bridge_message_id as "
                "reconciliation_required and backfill the Feishu message mapping before retrying updates."
            )
            try:
                self._state.update_status(
                    bridge_message_id,
                    Status.RECONCILIATION_REQUIRED,
                    card_id=card_id,
                    feishu_message_id=feishu_message_id,
                    sequence=sequence,
                    version=sequence,
                    failure_reason=recovery_instruction,
                )
            except BridgeStateError as exc:
                raise BridgeOrchestrationError(
                    recovery_instruction,
                    bridge_message_id=bridge_message_id,
                    card_id=card_id,
                    status=Status.RECONCILIATION_REQUIRED.value,
                    mock_calls=self._mock_calls_since(call_count_before),
                ) from exc

            return ProcessResult(
                bridge_message_id=bridge_message_id,
                card_id=card_id,
                feishu_message_id=feishu_message_id,
                sequence=sequence,
                status=Status.RECONCILIATION_REQUIRED.value,
                is_duplicate=False,
                mock_calls=self._mock_calls_since(call_count_before),
                recovery_instruction=recovery_instruction,
            )

        return ProcessResult(
            bridge_message_id=bridge_message_id,
            card_id=card_id,
            feishu_message_id=feishu_message_id,
            sequence=sequence,
            status=Status.SENT.value,
            is_duplicate=False,
            mock_calls=self._mock_calls_since(call_count_before),
            recovery_instruction=None,
        )

    def _duplicate_result(self, record: BridgeRecord) -> ProcessResult:
        return ProcessResult(
            bridge_message_id=record["bridge_message_id"],
            card_id=record["card_id"],
            feishu_message_id=record["feishu_message_id"],
            sequence=int(record["sequence"]),
            status=record["status"],
            is_duplicate=True,
            mock_calls=[],
            recovery_instruction=None,
        )

    def _process_changed_content(
        self,
        record: BridgeRecord,
        parsed: ParsedFinalReply,
        recipient: str,
    ) -> ProcessResult:
        status = record["status"]
        if status == Status.RECONCILIATION_REQUIRED.value:
            return self._reconciliation_result(record)
        if status == Status.EXPIRED.value:
            return self._expired_result(record)
        if status == Status.SEND_FAILED.value:
            if not self.is_explicit_pre_acceptance_rejection(record["failure_reason"]):
                return self._reconciliation_required_for_ambiguous_send(record)
            updated_record = self._update_record_content(record, parsed)
            return self._send_existing_card(updated_record, recipient)
        if status in {
            Status.NEW.value,
            Status.CARD_CREATED.value,
            Status.SEND_PENDING.value,
        }:
            updated_record = self._update_record_content(record, parsed)
            if updated_record["card_id"] and updated_record["status"] in {
                Status.CARD_CREATED.value,
                Status.SEND_PENDING.value,
            }:
                return self._send_existing_card(updated_record, recipient)
            return self._create_and_send_card(updated_record, parsed, recipient)
        if status in {
            Status.SENT.value,
            Status.UPDATED.value,
            Status.UPDATE_FAILED.value,
        }:
            updated_record = self._update_record_content(record, parsed)
            update_result = self.update_card(updated_record["bridge_message_id"])
            return ProcessResult(
                bridge_message_id=update_result.bridge_message_id,
                card_id=updated_record["card_id"],
                feishu_message_id=updated_record["feishu_message_id"],
                sequence=update_result.new_sequence,
                status=update_result.status,
                is_duplicate=False,
                mock_calls=update_result.mock_calls,
                recovery_instruction=None,
            )
        return self._terminal_result(record)

    def _update_record_content(self, record: BridgeRecord, parsed: ParsedFinalReply) -> BridgeRecord:
        self._state.update_status(
            record["bridge_message_id"],
            Status(record["status"]),
            content_markdown=parsed.content_markdown,
            content_hash=self._content_hash(parsed.content_markdown),
            failure_reason=None,
        )
        refreshed = self._state.get_record(record["bridge_message_id"], include_sensitive=True)
        if refreshed is None:
            raise BridgeOrchestrationError(
                f"Record {record['bridge_message_id']} disappeared after content update",
                bridge_message_id=record["bridge_message_id"],
                card_id=record["card_id"],
                status=record["status"],
            )
        return refreshed

    def _expired_result(self, record: BridgeRecord) -> ProcessResult:
        return ProcessResult(
            bridge_message_id=record["bridge_message_id"],
            card_id=record["card_id"],
            feishu_message_id=record["feishu_message_id"],
            sequence=int(record["sequence"]),
            status=Status.EXPIRED.value,
            is_duplicate=False,
            mock_calls=[],
            recovery_instruction="Card update window expired; create a new card for changed content.",
        )

    def _terminal_result(self, record: BridgeRecord) -> ProcessResult:
        return ProcessResult(
            bridge_message_id=record["bridge_message_id"],
            card_id=record["card_id"],
            feishu_message_id=record["feishu_message_id"],
            sequence=int(record["sequence"]),
            status=record["status"],
            is_duplicate=False,
            mock_calls=[],
            recovery_instruction=record["failure_reason"],
        )

    def _reconciliation_required_for_ambiguous_send(self, record: BridgeRecord) -> ProcessResult:
        recovery_instruction = (
            "Previous send attempt failed after card creation, but the failure was not an explicit "
            "pre-acceptance rejection. Do not resend this card_id blindly; reconcile remote delivery "
            "state before retrying."
        )
        self._state.update_status(
            record["bridge_message_id"],
            Status.RECONCILIATION_REQUIRED,
            card_id=record["card_id"],
            sequence=int(record["sequence"]),
            failure_reason=recovery_instruction,
        )
        return ProcessResult(
            bridge_message_id=record["bridge_message_id"],
            card_id=record["card_id"],
            feishu_message_id=record["feishu_message_id"],
            sequence=int(record["sequence"]),
            status=Status.RECONCILIATION_REQUIRED.value,
            is_duplicate=False,
            mock_calls=[],
            recovery_instruction=recovery_instruction,
        )

    def _reconciliation_result(self, record: BridgeRecord) -> ProcessResult:
        return ProcessResult(
            bridge_message_id=record["bridge_message_id"],
            card_id=record["card_id"],
            feishu_message_id=record["feishu_message_id"],
            sequence=int(record["sequence"]),
            status=Status.RECONCILIATION_REQUIRED.value,
            is_duplicate=False,
            mock_calls=[],
            recovery_instruction=record["failure_reason"],
        )

    @staticmethod
    def _content_hash(content_markdown: str) -> str:
        return hashlib.sha256(content_markdown.encode("utf-8")).hexdigest()

    @staticmethod
    def _delivery_fixture(parsed: ParsedFinalReply) -> DeliveryFixture:
        return cast(
            DeliveryFixture,
            cast(
                object,
                {
                    "source_platform": parsed.source_platform,
                    "session_key": parsed.session_key,
                    "hermes_message_id": parsed.hermes_message_id,
                    "final_reply_index": parsed.final_reply_index,
                    "content_markdown": parsed.content_markdown,
                },
            ),
        )

    @staticmethod
    def _load_fixture(fixture_path: str | Path) -> dict[str, object]:
        path = Path(fixture_path)
        return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def is_explicit_pre_acceptance_rejection(cls, failure_reason: str | None) -> bool:
        if not failure_reason:
            return False

        lowered = failure_reason.lower()
        if "code=0" in lowered or '"code": 0' in lowered:
            return False

        has_non_zero_code = re.search(r"\bcode\s*[:=]\s*(?!0\b)\d+", lowered) is not None
        has_validation_pattern = any(pattern in lowered for pattern in _EXPLICIT_REJECTION_PATTERNS)
        return has_validation_pattern and has_non_zero_code

    def _mock_call_count(self) -> int:
        transport = getattr(self._client, "_transport", None)
        maybe_calls = getattr(transport, "calls", None)
        if not isinstance(maybe_calls, list):
            return 0
        calls = cast(list[dict[str, object]], maybe_calls)
        return len(calls)

    def _mock_calls_since(self, call_count_before: int) -> list[dict[str, object]]:
        transport = getattr(self._client, "_transport", None)
        maybe_calls = getattr(transport, "calls", None)
        if not isinstance(maybe_calls, list):
            return []
        calls = cast(list[dict[str, object]], maybe_calls)
        return copy.deepcopy(calls[call_count_before:])

    @staticmethod
    def _render_transport_card_json(parsed: ParsedFinalReply) -> JSONDict:
        return cast(JSONDict, cast(object, render_card_json(parsed)))

    @staticmethod
    def _format_feishu_error_reason(exc: FeishuApiError) -> str:
        summary_parts: list[str] = []
        for key in ("code", "msg", "message", "error", "error_message", "error_msg"):
            value = exc.response.get(key)
            if value in (None, ""):
                continue
            summary_parts.append(f"{key}={BridgeOrchestrator._redact_failure_text(str(value))}")

        summary = "; ".join(summary_parts) if summary_parts else "redacted Feishu API error"
        return (
            f"{exc.__class__.__name__}; status_code={exc.status_code}; summary="
            f"{BridgeOrchestrator._redact_failure_text(summary)}"
        )

    @staticmethod
    def _redact_failure_text(text: str) -> str:
        redacted = _SENSITIVE_FAILURE_VALUE_PATTERN.sub(lambda match: f"{match.group(0).split('=')[0].strip()}=[REDACTED]", text)
        redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
        redacted = _URL_PATTERN.sub("[REDACTED_URL]", redacted)
        redacted = _LONG_TOKEN_PATTERN.sub("[REDACTED]", redacted)
        return redacted

    @staticmethod
    def _rebuild_parsed_reply_from_record(record: BridgeRecord) -> ParsedFinalReply:
        return parse_final_reply(
            {
                "source_platform": record["source_platform"],
                "session_key": record["session_key"],
                "hermes_message_id": record["hermes_message_id"],
                "final_reply_index": record["final_reply_index"],
                "content_markdown": record["content_markdown"],
            }
        )

    @staticmethod
    def _updated_parsed_reply(parsed: ParsedFinalReply) -> ParsedFinalReply:
        content_markdown = parsed.content_markdown
        while content_markdown.endswith(UPDATE_MARKER):
            content_markdown = content_markdown.removesuffix(UPDATE_MARKER)

        return parse_final_reply(
            {
                "source_platform": parsed.source_platform,
                "session_key": parsed.session_key,
                "hermes_message_id": parsed.hermes_message_id,
                "final_reply_index": parsed.final_reply_index,
                "content_markdown": f"{content_markdown}{UPDATE_MARKER}",
                "created_at": parsed.created_at,
                "attachments": list(parsed.attachments),
                "tool_payloads": list(parsed.tool_payloads),
            }
        )


__all__ = [
    "BridgeOrchestrationError",
    "BridgeOrchestrator",
    "ProcessResult",
    "UpdateResult",
]
