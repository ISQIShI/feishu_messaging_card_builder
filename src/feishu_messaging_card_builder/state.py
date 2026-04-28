from __future__ import annotations

from datetime import datetime, timezone
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
    source_platform: str
    session_key: str
    hermes_message_id: str | None
    final_reply_index: int
    content_hash: str
    card_id: str | None
    feishu_message_id: str | None
    sequence: int
    status: str
    failure_reason: str | None
    created_at: str
    updated_at: str


class BridgeStateManager:
    """SQLite-backed state store for bridge message deliveries."""

    _MUTABLE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"card_id", "feishu_message_id", "sequence", "failure_reason"}
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
        now = self._timestamp()

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    (
                        "INSERT OR IGNORE INTO card_deliveries ("
                        "bridge_message_id, source_platform, session_key, hermes_message_id, "
                        "final_reply_index, content_hash, status, created_at, updated_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        bridge_message_id,
                        fixture["source_platform"],
                        fixture["session_key"],
                        fixture.get("hermes_message_id"),
                        int(fixture["final_reply_index"]),
                        content_hash,
                        Status.NEW.value,
                        now,
                        now,
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
                        "source_platform TEXT NOT NULL, "
                        "session_key TEXT NOT NULL, "
                        "hermes_message_id TEXT, "
                        "final_reply_index INTEGER NOT NULL, "
                        "content_hash TEXT NOT NULL, "
                        "card_id TEXT, "
                        "feishu_message_id TEXT, "
                        "sequence INTEGER DEFAULT 1, "
                        "status TEXT NOT NULL, "
                        "failure_reason TEXT, "
                        "created_at TEXT NOT NULL, "
                        "updated_at TEXT NOT NULL"
                        ")"
                    ),
                )
        except sqlite3.Error as exc:
            raise BridgeStateError("Failed to initialize bridge state database") from exc

    @staticmethod
    def _content_hash(content_markdown: str) -> str:
        return hashlib.sha256(content_markdown.encode("utf-8")).hexdigest()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

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
                "source_platform": cast(str, row["source_platform"]),
                "session_key": cast(str, row["session_key"]),
                "hermes_message_id": cast(str | None, row["hermes_message_id"]),
                "final_reply_index": cast(int, row["final_reply_index"]),
                "content_hash": cast(str, row["content_hash"]),
                "card_id": cast(str | None, row["card_id"]),
                "feishu_message_id": cast(str | None, row["feishu_message_id"]),
                "sequence": cast(int, row["sequence"]),
                "status": cast(str, row["status"]),
                "failure_reason": cast(str | None, row["failure_reason"]),
                "created_at": cast(str, row["created_at"]),
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
