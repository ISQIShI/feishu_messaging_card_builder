# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path
import tempfile
from typing import cast

import pytest

from feishu_messaging_card_builder import state
from feishu_messaging_card_builder.state import (
    BridgeStateError,
    BridgeStateManager,
    DeliveryFixture,
    Status,
)


def build_fixture(**overrides: object) -> DeliveryFixture:
    fixture: dict[str, object] = {
        "source_platform": "feishu",
        "session_key": "session-1",
        "hermes_message_id": "hermes-1",
        "final_reply_index": 1,
        "content_markdown": "Hello, card.",
    }
    fixture.update(overrides)
    return cast(DeliveryFixture, cast(object, fixture))


def content_hash(content_markdown: str) -> str:
    return hashlib.sha256(content_markdown.encode("utf-8")).hexdigest()


def manager_for_temp_db() -> tuple[BridgeStateManager, tempfile.TemporaryDirectory[str]]:
    temp_dir = tempfile.TemporaryDirectory()
    manager = BridgeStateManager(str(Path(temp_dir.name) / "bridge.sqlite"))
    return manager, temp_dir


def test_bridge_message_id_deterministic() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture()
        assert manager.bridge_message_id(fixture) == manager.bridge_message_id(fixture)
    finally:
        temp_dir.cleanup()


def test_bridge_message_id_with_hermes_id() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture(
            source_platform="feishu",
            session_key="session-42",
            hermes_message_id="reply-99",
            final_reply_index=7,
        )
        assert manager.bridge_message_id(fixture) == "feishu:session-42:reply-99:7"
    finally:
        temp_dir.cleanup()


def test_bridge_message_id_without_hermes_id() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture(
            session_key="session-42",
            hermes_message_id=None,
            final_reply_index=7,
            content_markdown="markdown fallback",
        )
        expected_hash = content_hash("markdown fallback")
        assert manager.bridge_message_id(fixture) == f"feishu:session-42:7:{expected_hash}"
    finally:
        temp_dir.cleanup()


def test_duplicate_bridge_message_id_reuses_record() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture()
        hash_value = content_hash(fixture["content_markdown"])

        first_row, first_is_new = manager.get_or_create(fixture, hash_value)
        second_row, second_is_new = manager.get_or_create(fixture, hash_value)

        assert first_is_new is True
        assert second_is_new is False
        assert first_row["bridge_message_id"] == second_row["bridge_message_id"]
        assert first_row["created_at"] == second_row["created_at"]
    finally:
        temp_dir.cleanup()


def test_duplicate_creates_no_second_row() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture()
        hash_value = content_hash(fixture["content_markdown"])

        _ = manager.get_or_create(fixture, hash_value)
        _ = manager.get_or_create(fixture, hash_value)

        assert len(manager.list_records()) == 1
    finally:
        temp_dir.cleanup()


def test_failure_statuses_are_representable() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        for index, status in enumerate(Status, start=1):
            fixture = build_fixture(
                hermes_message_id=f"hermes-{index}",
                final_reply_index=index,
                content_markdown=f"content-{index}",
            )
            hash_value = content_hash(fixture["content_markdown"])
            record, _ = manager.get_or_create(fixture, hash_value)
            manager.update_status(record["bridge_message_id"], status, failure_reason=f"state={status.value}")
            reloaded = manager.get_record(record["bridge_message_id"])
            assert reloaded is not None
            assert reloaded["status"] == status.value
        assert len(manager.list_records()) == len(list(Status))
    finally:
        temp_dir.cleanup()


def test_card_created_to_sent_transition() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture()
        hash_value = content_hash(fixture["content_markdown"])
        record, _ = manager.get_or_create(fixture, hash_value)

        manager.update_status(record["bridge_message_id"], Status.CARD_CREATED, card_id="card_123")
        manager.update_status(
            record["bridge_message_id"],
            Status.SENT,
            feishu_message_id="om_123",
            sequence=2,
        )

        reloaded = manager.get_record(record["bridge_message_id"])
        assert reloaded is not None
        assert reloaded["status"] == Status.SENT.value
        assert reloaded["card_id"] == "card_123"
        assert reloaded["feishu_message_id"] == "om_123"
        assert reloaded["sequence"] == 2
    finally:
        temp_dir.cleanup()


def test_reconciliation_required_status() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture(hermes_message_id="hermes-reconcile")
        hash_value = content_hash(fixture["content_markdown"])
        record, _ = manager.get_or_create(fixture, hash_value)

        manager.update_status(
            record["bridge_message_id"],
            Status.RECONCILIATION_REQUIRED,
            failure_reason="send succeeded but local update failed",
        )

        reloaded = manager.get_record(record["bridge_message_id"])
        assert reloaded is not None
        assert reloaded["status"] == Status.RECONCILIATION_REQUIRED.value
        assert reloaded["failure_reason"] == "send succeeded but local update failed"
    finally:
        temp_dir.cleanup()


def test_bridge_state_error_on_bad_db(tmp_path: Path) -> None:
    bad_db_path = tmp_path / "corrupt.sqlite"
    _ = bad_db_path.write_bytes(b"this is not sqlite")

    with pytest.raises(BridgeStateError):
        _ = BridgeStateManager(str(bad_db_path))


def test_no_stdlib_db_dependency() -> None:
    source = inspect.getsource(state)
    parsed = ast.parse(source)
    imported_modules: set[str] = set()

    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])

    assert "sqlite3" in source
    assert {"sqlalchemy", "alembic", "aiosqlite", "peewee"}.isdisjoint(imported_modules)
