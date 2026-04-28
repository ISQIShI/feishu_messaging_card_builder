from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Final, Protocol, TypeAlias, TypedDict, final

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]


class TransportRequest(TypedDict):
    method: str
    path: str
    body: JSONDict


class RecordedCall(TypedDict):
    method: str
    path: str
    body: JSONDict
    response: JSONDict


LIVE_REQUIRED_ENV: Final[list[str]] = ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]

CARDKIT_CREATE_PATH: Final[str] = "/open-apis/cardkit/v1/cards"
LEGACY_TEMPLATE_SEND_PATH: Final[str] = "legacy_template_send"


@final
class FeishuApiError(Exception):
    """Raised when a Feishu transport reports an API-style failure.

    Future live transport work must require `FEISHU_APP_ID`,
    `FEISHU_APP_SECRET`, and an explicit `--live-feishu` flag before any
    network call is allowed.
    """

    status_code: int
    response: JSONDict

    def __init__(self, message: str, status_code: int, response: Mapping[str, JSONValue] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = dict(response or {})


class FeishuTransport(Protocol):
    """Transport protocol for Feishu card entity operations.

    The default implementation is mock-only. A future live transport must be
    opt-in, gated by `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, and a
    `--live-feishu` flag.
    """

    def record_create(self, card_json: Mapping[str, JSONValue]) -> JSONDict:
        """Create a card entity and return a transport response."""
        ...

    def record_send(self, card_id: str, recipient: str) -> JSONDict:
        """Send a previously created card entity and return a response."""
        ...

    def record_update(
        self,
        card_id: str,
        card_json: Mapping[str, JSONValue],
        sequence: int,
        uuid: str,
    ) -> JSONDict:
        """Update a previously created card entity and return a response."""
        ...


def _stringify_card_json(card_json: Mapping[str, JSONValue]) -> str:
    return json.dumps(card_json, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def build_create_card_request(card_json: Mapping[str, JSONValue]) -> TransportRequest:
    """Build the official card entity create request."""

    return {
        "method": "POST",
        "path": CARDKIT_CREATE_PATH,
        "body": {
            "type": "card_json",
            "data": _stringify_card_json(card_json),
        },
    }


def build_update_card_request(
    card_id: str,
    card_json: Mapping[str, JSONValue],
    sequence: int,
    uuid: str,
) -> TransportRequest:
    """Build the official full-card update request for an existing entity."""

    return {
        "method": "PUT",
        "path": f"{CARDKIT_CREATE_PATH}/{card_id}",
        "body": {
            "type": "card_json",
            "data": _stringify_card_json(card_json),
            "sequence": sequence,
            "uuid": uuid,
        },
    }


def build_legacy_template_send_request(card_id: str, recipient: str) -> TransportRequest:
    """Build the legacy template send request for a card entity.

    This `legacy_template_send` payload is a Phase 1 payload-proof item —
    validate against live/API Explorer.
    """

    return {
        "method": "POST",
        "path": LEGACY_TEMPLATE_SEND_PATH,
        "body": {
            "recipient": recipient,
            "type": "template",
            "data": {
                "template_id": card_id,
            },
        },
    }


def _stable_suffix(*parts: JSONValue) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


@final
class MockFeishuTransport:
    """Mock-first Feishu transport that records all calls for verification.

    This transport never calls Feishu. A future live transport must require
    `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, and an explicit `--live-feishu`
    flag before leaving mock mode.
    """

    calls: list[RecordedCall]
    _failure_status_codes: dict[str, int]

    def __init__(self, failure_status_codes: Mapping[str, int] | None = None) -> None:
        self.calls = []
        self._failure_status_codes = dict(failure_status_codes or {})

    def record_create(self, card_json: Mapping[str, JSONValue]) -> JSONDict:
        request = build_create_card_request(card_json)
        suffix = _stable_suffix(request["body"])
        response = {"card_id": f"mock-card-{suffix}"}
        return self._finalize("create", request, response)

    def record_send(self, card_id: str, recipient: str) -> JSONDict:
        request = build_legacy_template_send_request(card_id, recipient)
        suffix = _stable_suffix(card_id, recipient)
        response = {"message_id": f"mock-msg-{suffix}"}
        return self._finalize("send", request, response)

    def record_update(
        self,
        card_id: str,
        card_json: Mapping[str, JSONValue],
        sequence: int,
        uuid: str,
    ) -> JSONDict:
        request = build_update_card_request(card_id, card_json, sequence, uuid)
        response = {"success": True}
        return self._finalize("update", request, response)

    def _finalize(self, operation: str, request: TransportRequest, response: Mapping[str, JSONValue]) -> JSONDict:
        status_code = self._failure_status_codes.get(operation)
        if status_code is not None:
            error_response = {
                "error": f"mock {operation} failure",
                "status_code": status_code,
            }
            self._record(request, error_response)
            raise FeishuApiError(f"Mock Feishu {operation} failed", status_code=status_code, response=error_response)

        self._record(request, response)
        return dict(response)

    def _record(self, request: TransportRequest, response: Mapping[str, JSONValue]) -> None:
        self.calls.append(
            {
                "method": request["method"],
                "path": request["path"],
                "body": request["body"],
                "response": dict(response),
            }
        )


@final
class FeishuCardClient:
    """Client for Feishu card entity lifecycle operations.

    The client is transport-agnostic and defaults to mock-first usage. Any
    future live transport must require `FEISHU_APP_ID`, `FEISHU_APP_SECRET`,
    and an explicit `--live-feishu` flag before real Feishu traffic is allowed.
    """

    _transport: FeishuTransport

    def __init__(self, transport: FeishuTransport) -> None:
        self._transport = transport

    def create_card(self, card_json: Mapping[str, JSONValue]) -> str:
        """Create a card entity and return its `card_id`."""

        response = self._transport.record_create(card_json)
        return str(response["card_id"])

    def send_card(self, card_id: str, recipient: str) -> str:
        """Send an existing card entity and return its Feishu message id.

        Payload mode: `legacy_template_send`.
        Phase 1 payload-proof item — validate against live/API Explorer.
        """

        response = self._transport.record_send(card_id, recipient)
        return str(response["message_id"])

    def update_card(self, card_id: str, card_json: Mapping[str, JSONValue], sequence: int, uuid: str) -> None:
        """Replace an existing card entity using monotonic sequencing."""

        _ = self._transport.record_update(card_id, card_json, sequence, uuid)
