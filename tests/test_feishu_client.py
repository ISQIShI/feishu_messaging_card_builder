from __future__ import annotations

import json

import pytest

from src.feishu_messaging_card_builder.feishu_client import FeishuApiError
from src.feishu_messaging_card_builder.feishu_client import FeishuCardClient
from src.feishu_messaging_card_builder.feishu_client import JSONDict
from src.feishu_messaging_card_builder.feishu_client import MockFeishuTransport


def _card_json(title: str = "Build status") -> JSONDict:
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "body": {
            "title": title,
            "status": "ok",
        },
    }


def _stringify(card_json: JSONDict) -> str:
    return json.dumps(card_json, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _send_content(card_id: str) -> str:
    return json.dumps(
        {"type": "card", "data": {"card_id": card_id}},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_mock_transport_records_create_send_update() -> None:
    transport = MockFeishuTransport()
    client = FeishuCardClient(transport)
    initial_card_json = _card_json()
    updated_card_json = _card_json(title="Build complete")

    card_id = client.create_card(initial_card_json)
    message_id = client.send_card(card_id, "open_id:alice")
    client.update_card(card_id, updated_card_json, sequence=7, uuid="update-7")

    assert transport.calls == [
        {
            "method": "POST",
            "path": "/open-apis/cardkit/v1/cards",
            "body": {
                "type": "card_json",
                "data": _stringify(initial_card_json),
            },
            "response": {"card_id": card_id},
        },
        {
            "method": "POST",
            "path": "/open-apis/im/v1/messages",
            "params": {"receive_id_type": "open_id"},
            "body": {
                "receive_id": "open_id:alice",
                "msg_type": "interactive",
                "content": _send_content(card_id),
            },
            "response": {"message_id": message_id},
        },
        {
            "method": "PUT",
            "path": f"/open-apis/cardkit/v1/cards/{card_id}",
            "body": {
                "card": {
                    "type": "card_json",
                    "data": _stringify(updated_card_json),
                },
                "sequence": 7,
                "uuid": "update-7",
            },
            "response": {"success": True},
        },
    ]


def test_create_request_uses_card_json_type() -> None:
    transport = MockFeishuTransport()
    client = FeishuCardClient(transport)

    _ = client.create_card(_card_json())

    assert transport.calls[0]["body"]["type"] == "card_json"


def test_update_request_includes_sequence_and_uuid() -> None:
    transport = MockFeishuTransport()
    client = FeishuCardClient(transport)
    card_id = client.create_card(_card_json())

    client.update_card(card_id, _card_json(title="Updated"), sequence=5, uuid="uuid-5")

    assert transport.calls[-1]["body"]["sequence"] == 5
    assert transport.calls[-1]["body"]["uuid"] == "uuid-5"


def test_raw_card_json_send_not_exposed() -> None:
    client = FeishuCardClient(MockFeishuTransport())

    assert not any(
        hasattr(client, candidate)
        for candidate in ("send_raw", "send_raw_card_json", "send_card_json")
    )


def test_send_request_uses_official_im_message_endpoint() -> None:
    transport = MockFeishuTransport()
    client = FeishuCardClient(transport)

    _ = client.send_card("card-123", "open_id:bob")

    assert transport.calls[0] == {
        "method": "POST",
        "path": "/open-apis/im/v1/messages",
        "params": {"receive_id_type": "open_id"},
        "body": {
            "receive_id": "open_id:bob",
            "msg_type": "interactive",
            "content": _send_content("card-123"),
        },
        "response": transport.calls[0]["response"],
    }


def test_mock_transport_error_raises_feishu_api_error() -> None:
    transport = MockFeishuTransport(failure_status_codes={"create": 503})
    client = FeishuCardClient(transport)

    with pytest.raises(FeishuApiError) as exc_info:
        _ = client.create_card(_card_json())

    assert exc_info.value.status_code == 503
