from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import cast, final
import uuid as uuid_module

from .feishu_client import FeishuApiError, FeishuCardClient, JSONDict
from .parser import ParsedFinalReply, parse_final_reply
from .renderer import render_card_json
from .state import BridgeRecord, BridgeStateError, BridgeStateManager, DeliveryFixture, Status

UPDATE_MARKER = "\n\n> Updated by Phase 1 prototype"


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
        record, is_new = self._state.get_or_create(self._delivery_fixture(parsed), content_hash)
        bridge_message_id = record["bridge_message_id"]
        self._parsed_cache[bridge_message_id] = parsed

        if not is_new:
            if record["status"] in {Status.SENT.value, Status.UPDATED.value}:
                return self._duplicate_result(record)
            if record["card_id"] and record["status"] in {
                Status.CARD_CREATED.value,
                Status.SEND_FAILED.value,
                Status.SEND_PENDING.value,
            }:
                return self._send_existing_card(record, recipient)

        return self._create_and_send_card(record, parsed, recipient)

    def update_card(self, bridge_message_id: str) -> UpdateResult:
        record = self._state.get_record(bridge_message_id)
        if record is None:
            raise BridgeOrchestrationError(
                f"No bridge record found for {bridge_message_id}",
                bridge_message_id=bridge_message_id,
            )

        if record["status"] not in {Status.SENT.value, Status.UPDATED.value}:
            raise BridgeOrchestrationError(
                "Only sent or updated records can be updated",
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

        parsed = self._parsed_cache.get(bridge_message_id)
        if parsed is None:
            raise BridgeOrchestrationError(
                f"Original parsed payload is unavailable for {bridge_message_id}",
                bridge_message_id=bridge_message_id,
                card_id=card_id,
                status=record["status"],
            )

        updated_parsed = self._updated_parsed_reply(parsed)
        updated_card_json = self._render_transport_card_json(updated_parsed)
        previous_sequence = int(record["sequence"])
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
                sequence=new_sequence,
                failure_reason=str(exc),
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
        return [dict(record) for record in self._state.list_records()]

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
                failure_reason=str(exc),
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
