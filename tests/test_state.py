# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
from pathlib import Path
import sqlite3
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


def create_legacy_state_db(db_path: Path) -> None:
    created_at = "2026-04-01T12:34:56+00:00"
    updated_at = "2026-04-01T12:35:56+00:00"
    with sqlite3.connect(db_path) as connection:
        _ = connection.execute(
            (
                "CREATE TABLE card_deliveries ("
                "bridge_message_id TEXT PRIMARY KEY, "
                "source_platform TEXT NOT NULL, "
                "session_key TEXT NOT NULL, "
                "hermes_message_id TEXT, "
                "final_reply_index INTEGER NOT NULL, "
                "content_markdown TEXT NOT NULL, "
                "content_hash TEXT NOT NULL, "
                "card_id TEXT, "
                "feishu_message_id TEXT, "
                "sequence INTEGER DEFAULT 1, "
                "status TEXT NOT NULL, "
                "failure_reason TEXT, "
                "created_at TEXT NOT NULL, "
                "updated_at TEXT NOT NULL"
                ")"
            )
        )
        _ = connection.execute(
            (
                "INSERT INTO card_deliveries ("
                "bridge_message_id, source_platform, session_key, hermes_message_id, "
                "final_reply_index, content_markdown, content_hash, card_id, feishu_message_id, "
                "sequence, status, failure_reason, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                "feishu:legacy-session:legacy-hermes:3",
                "feishu",
                "legacy-session",
                "legacy-hermes",
                3,
                "legacy markdown",
                content_hash("legacy markdown"),
                "card_legacy",
                "om_legacy",
                7,
                Status.SENT.value,
                None,
                created_at,
                updated_at,
            ),
        )


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

        first_result = manager.get_or_create(fixture, hash_value)
        second_result = manager.get_or_create(fixture, hash_value)
        first_row = first_result.record
        second_row = second_result.record

        assert first_result.is_new is True
        assert first_result.content_changed is False
        assert second_result.is_new is False
        assert second_result.content_changed is False
        assert first_row["bridge_message_id"] == second_row["bridge_message_id"]
        assert first_row["idempotency_key"] == first_row["bridge_message_id"]
        assert first_row["version"] == 1
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
            record = manager.get_or_create(fixture, hash_value).record
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
        record = manager.get_or_create(fixture, hash_value).record

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
        assert reloaded["version"] == 1
    finally:
        temp_dir.cleanup()


def test_update_status_can_mutate_version() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture(hermes_message_id="hermes-version")
        hash_value = content_hash(fixture["content_markdown"])
        record = manager.get_or_create(fixture, hash_value).record

        manager.update_status(record["bridge_message_id"], Status.UPDATED, sequence=3, version=2)

        reloaded = manager.get_record(record["bridge_message_id"])
        assert reloaded is not None
        assert reloaded["sequence"] == 3
        assert reloaded["version"] == 2
    finally:
        temp_dir.cleanup()


def test_migrates_legacy_schema_in_place(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    create_legacy_state_db(db_path)

    manager = BridgeStateManager(str(db_path))
    records = manager.list_records()
    assert len(records) == 1

    with sqlite3.connect(db_path) as connection:
        column_names = {
            cast(str, row[1])
            for row in cast(
                list[tuple[object, ...]],
                connection.execute("PRAGMA table_info(card_deliveries)").fetchall(),
            )
        }
        row_count = cast(
            int,
            connection.execute("SELECT COUNT(*) FROM card_deliveries").fetchone()[0],
        )

    record = records[0]
    expected_updatable_until = (
        datetime.fromisoformat(record["created_at"]) + timedelta(days=14)
    ).isoformat(timespec="seconds")
    assert {"idempotency_key", "updatable_until", "version"}.issubset(column_names)
    assert row_count == 1
    assert record["bridge_message_id"] == "feishu:legacy-session:legacy-hermes:3"
    assert record["idempotency_key"] == record["bridge_message_id"]
    assert record["version"] == 7
    assert record["sequence"] == 7
    assert record["updatable_until"] == expected_updatable_until


def test_updatable_window_helpers_reflect_expiry() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture(hermes_message_id="hermes-expiry")
        hash_value = content_hash(fixture["content_markdown"])
        record = manager.get_or_create(fixture, hash_value).record
        bridge_message_id = record["bridge_message_id"]

        assert manager.is_updatable(bridge_message_id) is True
        assert manager.is_expired(bridge_message_id) is False

        expired_timestamp = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        manager.update_status(bridge_message_id, Status.UPDATE_FAILED)
        with sqlite3.connect(Path(temp_dir.name) / "bridge.sqlite") as connection:
            _ = connection.execute(
                "UPDATE card_deliveries SET updatable_until = ? WHERE bridge_message_id = ?",
                (expired_timestamp, bridge_message_id),
            )

        assert manager.is_updatable(bridge_message_id) is False
        assert manager.is_expired(bridge_message_id) is True
    finally:
        temp_dir.cleanup()


def test_reconciliation_required_status() -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture(hermes_message_id="hermes-reconcile")
        hash_value = content_hash(fixture["content_markdown"])
        record = manager.get_or_create(fixture, hash_value).record

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


@pytest.mark.parametrize(
    ("starting_status", "expected_status", "expire_record"),
    [
        (Status.NEW, Status.NEW, False),
        (Status.CARD_CREATED, Status.CARD_CREATED, False),
        (Status.SEND_PENDING, Status.SEND_PENDING, False),
        (Status.SEND_FAILED, Status.SEND_FAILED, False),
        (Status.SENT, Status.SENT, False),
        (Status.UPDATED, Status.UPDATED, False),
        (Status.UPDATE_FAILED, Status.UPDATE_FAILED, False),
        (Status.RECONCILIATION_REQUIRED, Status.RECONCILIATION_REQUIRED, False),
        (Status.EXPIRED, Status.EXPIRED, False),
        (Status.SENT, Status.EXPIRED, True),
        (Status.UPDATE_FAILED, Status.EXPIRED, True),
    ],
)
def test_get_or_create_returns_changed_content_flag_by_lifecycle_state(
    starting_status: Status,
    expected_status: Status,
    expire_record: bool,
) -> None:
    manager, temp_dir = manager_for_temp_db()
    try:
        fixture = build_fixture(hermes_message_id=f"hermes-{starting_status.value}")
        initial_result = manager.get_or_create(fixture, content_hash(fixture["content_markdown"]))
        record = initial_result.record
        manager.update_status(
            record["bridge_message_id"],
            starting_status,
            card_id="card_123" if starting_status is not Status.NEW else None,
            feishu_message_id="om_123" if starting_status in {Status.SENT, Status.UPDATED, Status.EXPIRED} else None,
            sequence=2 if starting_status in {Status.SENT, Status.UPDATED, Status.UPDATE_FAILED, Status.EXPIRED} else 1,
            version=2 if starting_status in {Status.UPDATED, Status.UPDATE_FAILED, Status.EXPIRED} else 1,
            failure_reason="existing failure" if starting_status in {Status.SEND_FAILED, Status.UPDATE_FAILED, Status.RECONCILIATION_REQUIRED} else None,
        )

        if expire_record:
            expired_timestamp = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
            with sqlite3.connect(Path(temp_dir.name) / "bridge.sqlite") as connection:
                _ = connection.execute(
                    "UPDATE card_deliveries SET updatable_until = ? WHERE bridge_message_id = ?",
                    (expired_timestamp, record["bridge_message_id"]),
                )

        changed_fixture = build_fixture(
            hermes_message_id=fixture["hermes_message_id"],
            content_markdown=f"{fixture['content_markdown']}\nChanged content.",
        )
        changed_result = manager.get_or_create(
            changed_fixture,
            content_hash(changed_fixture["content_markdown"]),
        )

        assert changed_result.is_new is False
        assert changed_result.content_changed is True
        assert changed_result.record["status"] == expected_status.value
        assert changed_result.record["content_markdown"] == fixture["content_markdown"]
        assert changed_result.record["content_hash"] == content_hash(fixture["content_markdown"])
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
