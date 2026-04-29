from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import sqlite3
from typing import ClassVar, TypeAlias, TypedDict, cast
from urllib.parse import quote


class BridgeStateError(Exception):
    """Raised when bridge state persistence fails."""


class Status(StrEnum):
    NEW = "new"
    CARD_CREATED = "card_created"
    SEND_PENDING = "send_pending"
    SEND_FAILED = "send_failed"
    SENT = "sent"
    UPDATE_FAILED = "update_failed"
    UPDATED = "updated"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    UNSUPPORTED = "unsupported"


class DeliveryFixture(TypedDict):
    source_platform: str
    session_key: str
    hermes_message_id: str | None
    final_reply_index: int
    content_markdown: str


SQLiteValue: TypeAlias = str | int | None


class BridgeRecord(TypedDict):
    bridge_message_id: str
    idempotency_key: str
    source_platform: str
    session_key: str
    hermes_message_id: str | None
    final_reply_index: int
    content_markdown: str
    content_hash: str
    card_id: str | None
    feishu_message_id: str | None
    sequence: int
    version: int
    status: str
    failure_reason: str | None
    created_at: str
    updatable_until: str
    updated_at: str


class BridgeStateManager:
    """SQLite-backed state store for bridge message deliveries."""

    _MUTABLE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"card_id", "feishu_message_id", "sequence", "version", "failure_reason"}
    )

    def __init__(self, db_path: str) -> None:
        self._db_path: str = db_path
        self._initialize()

    def bridge_message_id(self, fixture: DeliveryFixture) -> str:
        source_platform = self._url_safe_component(fixture["source_platform"])
        session_key = self._url_safe_component(fixture["session_key"])
        final_reply_index = str(int(fixture["final_reply_index"]))
        hermes_message_id = fixture.get("hermes_message_id")

        if hermes_message_id not in (None, ""):
            hermes_component = self._url_safe_component(hermes_message_id)
            return ":".join((source_platform, session_key, hermes_component, final_reply_index))

        content_hash = self._content_hash(fixture["content_markdown"])
        return ":".join((source_platform, session_key, final_reply_index, content_hash))

    def get_or_create(self, fixture: DeliveryFixture, content_hash: str) -> tuple[BridgeRecord, bool]:
        bridge_message_id = self.bridge_message_id(fixture)
        idempotency_key = bridge_message_id
        now = self._timestamp()
        updatable_until = self._derive_updatable_until(now)

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    (
                        "INSERT OR IGNORE INTO card_deliveries ("
                        "bridge_message_id, idempotency_key, source_platform, session_key, "
                        "hermes_message_id, final_reply_index, content_markdown, content_hash, "
                        "status, created_at, updatable_until, updated_at, version"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        bridge_message_id,
                        idempotency_key,
                        fixture["source_platform"],
                        fixture["session_key"],
                        fixture.get("hermes_message_id"),
                        int(fixture["final_reply_index"]),
                        fixture["content_markdown"],
                        content_hash,
                        Status.NEW.value,
                        now,
                        updatable_until,
                        now,
                        1,
                    ),
                )
                row = cast(
                    sqlite3.Row | None,
                    connection.execute(
                        "SELECT * FROM card_deliveries WHERE bridge_message_id = ?",
                        (bridge_message_id,),
                    ).fetchone(),
                )

            if row is None:
                raise BridgeStateError(f"Unable to load record for {bridge_message_id} after insert")

            row_dict = self._row_to_dict(row)
            if row_dict["content_hash"] != content_hash:
                raise BridgeStateError(
                    f"Existing record for {bridge_message_id} has mismatched content_hash"
                )

            return row_dict, cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise BridgeStateError("Failed to read or create bridge state record") from exc

    def update_status(self, bridge_message_id: str, status: Status, **extra_fields: object) -> None:
        unexpected_fields = set(extra_fields) - self._MUTABLE_FIELDS
        if unexpected_fields:
            invalid = ", ".join(sorted(unexpected_fields))
            raise BridgeStateError(f"Unsupported update fields: {invalid}")

        parameters = (
            status.value,
            self._timestamp(),
            "card_id" in extra_fields,
            extra_fields.get("card_id"),
            "feishu_message_id" in extra_fields,
            extra_fields.get("feishu_message_id"),
            "sequence" in extra_fields,
            extra_fields.get("sequence"),
            "version" in extra_fields,
            extra_fields.get("version"),
            "failure_reason" in extra_fields,
            extra_fields.get("failure_reason"),
            bridge_message_id,
        )

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    (
                        "UPDATE card_deliveries SET "
                        "status = ?, "
                        "updated_at = ?, "
                        "card_id = CASE WHEN ? THEN ? ELSE card_id END, "
                        "feishu_message_id = CASE WHEN ? THEN ? ELSE feishu_message_id END, "
                        "sequence = CASE WHEN ? THEN ? ELSE sequence END, "
                        "version = CASE WHEN ? THEN ? ELSE version END, "
                        "failure_reason = CASE WHEN ? THEN ? ELSE failure_reason END "
                        "WHERE bridge_message_id = ?"
                    ),
                    parameters,
                )

            if cursor.rowcount != 1:
                raise BridgeStateError(f"No record found for bridge_message_id={bridge_message_id}")
        except sqlite3.Error as exc:
            raise BridgeStateError(f"Failed to update state for {bridge_message_id}") from exc

    def get_record(self, bridge_message_id: str) -> BridgeRecord | None:
        try:
            with self._connect() as connection:
                row = cast(
                    sqlite3.Row | None,
                    connection.execute(
                        "SELECT * FROM card_deliveries WHERE bridge_message_id = ?",
                        (bridge_message_id,),
                    ).fetchone(),
                )
        except sqlite3.Error as exc:
            raise BridgeStateError(f"Failed to fetch state for {bridge_message_id}") from exc

        return None if row is None else self._row_to_dict(row)

    def is_updatable(self, bridge_message_id: str) -> bool:
        record = self.get_record(bridge_message_id)
        if record is None:
            raise BridgeStateError(f"No record found for bridge_message_id={bridge_message_id}")

        return not self._is_timestamp_expired(record["updatable_until"])

    def is_expired(self, bridge_message_id: str) -> bool:
        record = self.get_record(bridge_message_id)
        if record is None:
            raise BridgeStateError(f"No record found for bridge_message_id={bridge_message_id}")

        return self._is_timestamp_expired(record["updatable_until"])

    def list_records(self) -> list[BridgeRecord]:
        try:
            with self._connect() as connection:
                rows = cast(
                    list[sqlite3.Row],
                    connection.execute(
                        "SELECT * FROM card_deliveries ORDER BY created_at DESC",
                    ).fetchall(),
                )
        except sqlite3.Error as exc:
            raise BridgeStateError("Failed to list bridge state records") from exc

        return [self._row_to_dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self._db_path)
            connection.row_factory = sqlite3.Row
            _ = connection.execute("PRAGMA journal_mode=WAL")
            return connection
        except sqlite3.Error as exc:
            raise BridgeStateError(f"Failed to open SQLite database at {self._db_path}") from exc

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                _ = connection.execute(
                    (
                        "CREATE TABLE IF NOT EXISTS card_deliveries ("
                        "bridge_message_id TEXT PRIMARY KEY, "
                        "idempotency_key TEXT, "
                        "source_platform TEXT NOT NULL, "
                        "session_key TEXT NOT NULL, "
                        "hermes_message_id TEXT, "
                        "final_reply_index INTEGER NOT NULL, "
                        "content_markdown TEXT NOT NULL, "
                        "content_hash TEXT NOT NULL, "
                        "card_id TEXT, "
                        "feishu_message_id TEXT, "
                        "sequence INTEGER DEFAULT 1, "
                        "version INTEGER DEFAULT 1, "
                        "status TEXT NOT NULL, "
                        "failure_reason TEXT, "
                        "created_at TEXT NOT NULL, "
                        "updatable_until TEXT, "
                        "updated_at TEXT NOT NULL"
                        ")"
                    ),
                )
                self._migrate_schema(connection)
        except sqlite3.Error as exc:
            raise BridgeStateError("Failed to initialize bridge state database") from exc

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            cast(str, row["name"])
            for row in cast(
                list[sqlite3.Row],
                connection.execute("PRAGMA table_info(card_deliveries)").fetchall(),
            )
        }

        column_definitions = {
            "idempotency_key": "TEXT",
            "updatable_until": "TEXT",
            "version": "INTEGER DEFAULT 1",
        }
        added_columns: set[str] = set()

        for column_name, definition in column_definitions.items():
            if column_name in existing_columns:
                continue
            _ = connection.execute(
                f"ALTER TABLE card_deliveries ADD COLUMN {column_name} {definition}"
            )
            added_columns.add(column_name)

        self._backfill_legacy_rows(connection, added_columns)

    def _backfill_legacy_rows(
        self,
        connection: sqlite3.Connection,
        added_columns: set[str],
    ) -> None:
        _ = connection.execute(
            (
                "UPDATE card_deliveries SET idempotency_key = bridge_message_id "
                "WHERE idempotency_key IS NULL OR idempotency_key = ''"
            )
        )
        if "version" in added_columns:
            _ = connection.execute("UPDATE card_deliveries SET version = sequence")
        else:
            _ = connection.execute(
                "UPDATE card_deliveries SET version = sequence WHERE version IS NULL"
            )

        legacy_rows = cast(
            list[sqlite3.Row],
            connection.execute(
                (
                    "SELECT bridge_message_id, created_at FROM card_deliveries "
                    "WHERE updatable_until IS NULL OR updatable_until = ''"
                )
            ).fetchall(),
        )
        for row in legacy_rows:
            _ = connection.execute(
                "UPDATE card_deliveries SET updatable_until = ? WHERE bridge_message_id = ?",
                (
                    self._derive_updatable_until(cast(str, row["created_at"])),
                    cast(str, row["bridge_message_id"]),
                ),
            )

    @staticmethod
    def _content_hash(content_markdown: str) -> str:
        return hashlib.sha256(content_markdown.encode("utf-8")).hexdigest()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _derive_updatable_until(created_at: str) -> str:
        return (datetime.fromisoformat(created_at) + timedelta(days=14)).isoformat(timespec="seconds")

    @staticmethod
    def _is_timestamp_expired(timestamp: str) -> bool:
        return datetime.now(timezone.utc) > datetime.fromisoformat(timestamp)

    @staticmethod
    def _url_safe_component(value: object) -> str:
        return quote(str(value), safe="-._~")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> BridgeRecord:
        return cast(
            BridgeRecord,
            cast(
                object,
            {
                "bridge_message_id": cast(str, row["bridge_message_id"]),
                "idempotency_key": cast(str, row["idempotency_key"]),
                "source_platform": cast(str, row["source_platform"]),
                "session_key": cast(str, row["session_key"]),
                "hermes_message_id": cast(str | None, row["hermes_message_id"]),
                "final_reply_index": cast(int, row["final_reply_index"]),
                "content_markdown": cast(str, row["content_markdown"]),
                "content_hash": cast(str, row["content_hash"]),
                "card_id": cast(str | None, row["card_id"]),
                "feishu_message_id": cast(str | None, row["feishu_message_id"]),
                "sequence": cast(int, row["sequence"]),
                "version": cast(int, row["version"]),
                "status": cast(str, row["status"]),
                "failure_reason": cast(str | None, row["failure_reason"]),
                "created_at": cast(str, row["created_at"]),
                "updatable_until": cast(str, row["updatable_until"]),
                "updated_at": cast(str, row["updated_at"]),
            },
            ),
        )


__all__ = [
    "BridgeRecord",
    "BridgeStateError",
    "BridgeStateManager",
    "DeliveryFixture",
    "SQLiteValue",
    "Status",
]
