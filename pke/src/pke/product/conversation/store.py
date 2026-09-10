"""Persistência de produto: Conversation / Message / Clarification.

Isolada do Knowledge Core schema v10. Arquivo SQLite separado.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pke.application.session import SessionContext
from pke.product.api.v1.dtos import (
    ApiClarification,
    ApiClarificationMode,
    ApiClarificationOption,
    ApiErrorBody,
    ApiMessage,
    ApiMessageRole,
    ApiMessageStatus,
    ApiOperation,
    ApiOperationKind,
    ApiOperationOutcome,
)
from pke.product.conversation.idempotency import (
    IdempotencyClaimResult,
    IdempotencyRecord,
    IdempotencyStatus,
)
from pke.product.ids import (
    clarification_id,
    conversation_id,
    message_id,
    session_id as new_session_id,
    user_id as new_user_id,
)
from pke.resolution import PersonalContext

PRODUCT_SCHEMA_VERSION = "1.4"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
CREATE TABLE IF NOT EXISTS auth_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    event TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    engine_session_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
    ON conversations (user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT,
    text TEXT NOT NULL,
    payload_json TEXT,
    client_request_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_client_request
    ON messages (user_id, client_request_id);
CREATE TABLE IF NOT EXISTS clarifications (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    options_json TEXT,
    original_text TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    pending_operation_json TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE TABLE IF NOT EXISTS idempotency (
    user_id TEXT NOT NULL,
    client_request_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL DEFAULT '',
    conversation_id TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    response_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, client_request_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ConversationRecord:
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class UserRecord:
    id: str
    username: str
    password_hash: str
    display_name: str
    created_at: str


@dataclass(frozen=True)
class SessionRecord:
    id: str
    user_id: str
    token_hash: str
    created_at: str
    expires_at: str
    revoked_at: str | None


@dataclass
class PendingClarification:
    id: str
    conversation_id: str
    user_id: str
    message_id: str
    mode: str
    options: list[dict[str, str]]
    original_text: str
    status: str
    pending_operation_json: str | None = None


class ProductStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if str(path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._memory = str(path) == ":memory:"
        self._conn: sqlite3.Connection | None = None
        self._init()

    def _connect(self) -> sqlite3.Connection:
        if self._memory:
            if self._conn is None:
                self._conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
            return self._conn
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            # Product-store only migration (not Knowledge Core).
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(clarifications)").fetchall()
            }
            if "pending_operation_json" not in cols:
                conn.execute(
                    "ALTER TABLE clarifications ADD COLUMN pending_operation_json TEXT"
                )
            self._migrate_idempotency(conn)
            conv_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
            }
            if "status" not in conv_cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
                )
            conn.execute(
                "INSERT OR IGNORE INTO product_schema_meta(key, value) VALUES (?, ?)",
                ("schema_version", PRODUCT_SCHEMA_VERSION),
            )
            conn.execute(
                "UPDATE product_schema_meta SET value = ? WHERE key = ?",
                (PRODUCT_SCHEMA_VERSION, "schema_version"),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def _migrate_idempotency(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(idempotency)").fetchall()}
        if not cols:
            return
        if "request_fingerprint" not in cols:
            conn.execute(
                "ALTER TABLE idempotency ADD COLUMN request_fingerprint TEXT NOT NULL DEFAULT ''"
            )
        if "conversation_id" not in cols:
            conn.execute("ALTER TABLE idempotency ADD COLUMN conversation_id TEXT")
        if "status" not in cols:
            conn.execute(
                "ALTER TABLE idempotency ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'"
            )
        if "updated_at" not in cols:
            conn.execute(
                "ALTER TABLE idempotency ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "UPDATE idempotency SET updated_at = created_at WHERE updated_at = '' OR updated_at IS NULL"
            )

    def create_user(self, username: str, password_hash: str, display_name: str) -> UserRecord:
        uid = new_user_id()
        stamp = _now()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO users (id, username, password_hash, display_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (uid, username, password_hash, display_name, stamp),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()
        return UserRecord(uid, username, password_hash, display_name, stamp)

    def get_user_by_username(self, username: str) -> UserRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return None
        return UserRecord(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            display_name=row["display_name"],
            created_at=row["created_at"],
        )

    def get_user_by_id(self, user_id_value: str) -> UserRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id_value,)
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return None
        return UserRecord(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            display_name=row["display_name"],
            created_at=row["created_at"],
        )

    def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        created_at: str,
        expires_at: str,
    ) -> SessionRecord:
        sid = new_session_id()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO sessions
                    (id, user_id, token_hash, created_at, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (sid, user_id, token_hash, created_at, expires_at),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()
        return SessionRecord(sid, user_id, token_hash, created_at, expires_at, None)

    def get_session_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return None
        return SessionRecord(
            id=row["id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )

    def revoke_session(self, session_id_value: str) -> None:
        stamp = _now()
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (stamp, session_id_value),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def record_auth_event(
        self, user_id_value: str | None, event: str, outcome: str
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO auth_events (user_id, event, outcome, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id_value, event, outcome, _now()),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def create_conversation(self, user_id: str, title: str = "Nova conversa") -> ConversationRecord:
        cid = conversation_id()
        stamp = _now()
        session = SessionContext(personal=PersonalContext(user_id=user_id))
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO conversations
                    (id, user_id, title, created_at, updated_at, engine_session_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cid, user_id, title, stamp, stamp, session.model_dump_json()),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()
        return ConversationRecord(cid, user_id, title, stamp, stamp)

    def get_conversation(self, user_id: str, conversation_id_value: str) -> ConversationRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id_value, user_id),
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return None
        return ConversationRecord(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_conversations(self, user_id: str) -> list[ConversationRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        finally:
            if not self._memory:
                conn.close()
        return [
            ConversationRecord(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def touch_conversation(self, user_id: str, conversation_id_value: str, title: str | None = None) -> None:
        conn = self._connect()
        try:
            if title:
                conn.execute(
                    "UPDATE conversations SET updated_at = ?, title = ? WHERE id = ? AND user_id = ?",
                    (_now(), title, conversation_id_value, user_id),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
                    (_now(), conversation_id_value, user_id),
                )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def load_engine_session(self, user_id: str, conversation_id_value: str) -> SessionContext:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT engine_session_json FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id_value, user_id),
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return SessionContext(personal=PersonalContext(user_id=user_id))
        data = json.loads(row["engine_session_json"] or "{}")
        if not data:
            return SessionContext(personal=PersonalContext(user_id=user_id))
        return SessionContext.model_validate(data)

    def save_engine_session(
        self, user_id: str, conversation_id_value: str, session: SessionContext
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE conversations SET engine_session_json = ? WHERE id = ? AND user_id = ?",
                (session.model_dump_json(), conversation_id_value, user_id),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def add_message(
        self,
        *,
        user_id: str,
        conversation_id_value: str,
        role: str,
        type_: str,
        text: str,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
        client_request_id: str | None = None,
        message_id_value: str | None = None,
    ) -> ApiMessage:
        mid = message_id_value or message_id()
        stamp = _now()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, user_id, role, type, status, text,
                    payload_json, client_request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    conversation_id_value,
                    user_id,
                    role,
                    type_,
                    status,
                    text,
                    json.dumps(payload) if payload else None,
                    client_request_id,
                    stamp,
                ),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()
        return self._message_from_parts(
            mid, conversation_id_value, role, type_, text, status, stamp, payload
        )

    def list_messages(self, user_id: str, conversation_id_value: str) -> list[ApiMessage]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id_value, user_id),
            ).fetchall()
        finally:
            if not self._memory:
                conn.close()
        return [self._row_to_message(row) for row in rows]

    def add_clarification(
        self,
        *,
        user_id: str,
        conversation_id_value: str,
        message_id_value: str,
        mode: str,
        options: list[dict[str, str]],
        original_text: str,
        clarification_id_value: str | None = None,
        pending_operation_json: str | None = None,
    ) -> str:
        cid = clarification_id_value or clarification_id()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO clarifications (
                    id, conversation_id, user_id, message_id, mode, options_json,
                    original_text, status, created_at, pending_operation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    conversation_id_value,
                    user_id,
                    message_id_value,
                    mode,
                    json.dumps(options),
                    original_text,
                    "pending",
                    _now(),
                    pending_operation_json,
                ),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()
        return cid

    def get_clarification(self, user_id: str, clarification_id_value: str) -> PendingClarification | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM clarifications WHERE id = ? AND user_id = ?",
                (clarification_id_value, user_id),
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return None
        keys = row.keys()
        return PendingClarification(
            id=row["id"],
            conversation_id=row["conversation_id"],
            user_id=row["user_id"],
            message_id=row["message_id"],
            mode=row["mode"],
            options=json.loads(row["options_json"] or "[]"),
            original_text=row["original_text"],
            status=row["status"],
            pending_operation_json=row["pending_operation_json"]
            if "pending_operation_json" in keys
            else None,
        )

    def mark_clarification_answered(self, user_id: str, clarification_id_value: str) -> None:
        self._set_clarification_status(user_id, clarification_id_value, "answered")

    def mark_clarification_resolved(
        self,
        user_id: str,
        clarification_id_value: str,
        *,
        pending_operation_json: str | None = None,
    ) -> None:
        conn = self._connect()
        try:
            if pending_operation_json is not None:
                conn.execute(
                    """
                    UPDATE clarifications
                    SET status = ?, pending_operation_json = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    ("resolved", pending_operation_json, clarification_id_value, user_id),
                )
            else:
                conn.execute(
                    "UPDATE clarifications SET status = ? WHERE id = ? AND user_id = ?",
                    ("resolved", clarification_id_value, user_id),
                )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def _set_clarification_status(
        self, user_id: str, clarification_id_value: str, status: str
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE clarifications SET status = ? WHERE id = ? AND user_id = ?",
                (status, clarification_id_value, user_id),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def get_pending_clarification(
        self, user_id: str, conversation_id_value: str
    ) -> PendingClarification | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM clarifications
                WHERE conversation_id = ? AND user_id = ? AND status = 'pending'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (conversation_id_value, user_id),
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return None
        keys = row.keys()
        return PendingClarification(
            id=row["id"],
            conversation_id=row["conversation_id"],
            user_id=row["user_id"],
            message_id=row["message_id"],
            mode=row["mode"],
            options=json.loads(row["options_json"] or "[]"),
            original_text=row["original_text"],
            status=row["status"],
            pending_operation_json=row["pending_operation_json"]
            if "pending_operation_json" in keys
            else None,
        )

    def last_message_preview(self, user_id: str, conversation_id_value: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT text FROM messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (conversation_id_value, user_id),
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return None
        text = " ".join((row["text"] or "").split())
        if len(text) <= 80:
            return text or None
        return text[:77].rstrip() + "…"

    def find_messages_by_client_request(
        self, user_id: str, client_request_id: str
    ) -> list[ApiMessage]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE user_id = ? AND client_request_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (user_id, client_request_id),
            ).fetchall()
        finally:
            if not self._memory:
                conn.close()
        return [self._row_to_message(row) for row in rows]

    def ping(self) -> None:
        """Verify Product persistence is reachable (fail-closed guard)."""
        conn = self._connect()
        try:
            conn.execute("SELECT 1 FROM product_schema_meta LIMIT 1").fetchone()
        finally:
            if not self._memory:
                conn.close()

    def get_idempotent(self, user_id: str, client_request_id: str) -> dict[str, Any] | None:
        record = self.get_idempotency_record(user_id, client_request_id)
        if record is None or record.status != IdempotencyStatus.COMPLETED.value:
            return None
        return record.response_json

    def get_idempotency_record(
        self, user_id: str, client_request_id: str
    ) -> IdempotencyRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM idempotency
                WHERE user_id = ? AND client_request_id = ?
                """,
                (user_id, client_request_id),
            ).fetchone()
        finally:
            if not self._memory:
                conn.close()
        if row is None:
            return None
        keys = row.keys()
        response = None
        if row["response_json"]:
            response = json.loads(row["response_json"])
        return IdempotencyRecord(
            user_id=row["user_id"],
            client_request_id=row["client_request_id"],
            request_fingerprint=row["request_fingerprint"]
            if "request_fingerprint" in keys
            else "",
            conversation_id=row["conversation_id"] if "conversation_id" in keys else None,
            status=row["status"] if "status" in keys and row["status"] else "completed",
            response_json=response,
            created_at=row["created_at"],
            updated_at=(row["updated_at"] if "updated_at" in keys else "") or row["created_at"],
        )

    def claim_idempotent(
        self,
        user_id: str,
        client_request_id: str,
        *,
        request_fingerprint: str,
        conversation_id: str | None = None,
    ) -> tuple[IdempotencyClaimResult, IdempotencyRecord | None]:
        """Atomically claim or classify an idempotency key (BEGIN IMMEDIATE)."""
        conn = self._connect()
        stamp = _now()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM idempotency
                WHERE user_id = ? AND client_request_id = ?
                """,
                (user_id, client_request_id),
            ).fetchone()
            if row is not None:
                keys = row.keys()
                stored_fp = (
                    row["request_fingerprint"] if "request_fingerprint" in keys else ""
                ) or ""
                status = (
                    row["status"] if "status" in keys and row["status"] else "completed"
                )
                response = json.loads(row["response_json"]) if row["response_json"] else None
                record = IdempotencyRecord(
                    user_id=row["user_id"],
                    client_request_id=row["client_request_id"],
                    request_fingerprint=stored_fp,
                    conversation_id=row["conversation_id"]
                    if "conversation_id" in keys
                    else None,
                    status=status,
                    response_json=response,
                    created_at=row["created_at"],
                    updated_at=(row["updated_at"] if "updated_at" in keys else "")
                    or row["created_at"],
                )
                if stored_fp and stored_fp != request_fingerprint:
                    conn.execute("COMMIT")
                    return IdempotencyClaimResult.CONFLICT, record
                if status == IdempotencyStatus.COMPLETED.value and response is not None:
                    conn.execute("COMMIT")
                    return IdempotencyClaimResult.REPLAY, record
                if status == IdempotencyStatus.RECOVERY_REQUIRED.value:
                    conn.execute("COMMIT")
                    return IdempotencyClaimResult.RECOVERY_REQUIRED, record
                if status == IdempotencyStatus.IN_PROGRESS.value:
                    # Same fingerprint already running — do not start a second Engine call.
                    conn.execute("COMMIT")
                    return IdempotencyClaimResult.IN_PROGRESS, record
                if status != IdempotencyStatus.FAILED.value:
                    # Unknown status — do not reclaim for Engine retry.
                    conn.execute("COMMIT")
                    return IdempotencyClaimResult.RECOVERY_REQUIRED, record
                # Explicit failed (fail_idempotent before complete): safe Engine retry.
                conn.execute(
                    """
                    UPDATE idempotency
                    SET request_fingerprint = ?, conversation_id = ?, status = ?,
                        response_json = NULL, updated_at = ?
                    WHERE user_id = ? AND client_request_id = ?
                    """,
                    (
                        request_fingerprint,
                        conversation_id,
                        IdempotencyStatus.IN_PROGRESS.value,
                        stamp,
                        user_id,
                        client_request_id,
                    ),
                )
                conn.execute("COMMIT")
                return IdempotencyClaimResult.PROCEED, None

            conn.execute(
                """
                INSERT INTO idempotency (
                    user_id, client_request_id, request_fingerprint, conversation_id,
                    status, response_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    user_id,
                    client_request_id,
                    request_fingerprint,
                    conversation_id,
                    IdempotencyStatus.IN_PROGRESS.value,
                    stamp,
                    stamp,
                ),
            )
            conn.execute("COMMIT")
            return IdempotencyClaimResult.PROCEED, None
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            if not self._memory:
                conn.close()

    def complete_idempotent(
        self,
        user_id: str,
        client_request_id: str,
        payload: dict[str, Any],
        *,
        request_fingerprint: str,
        conversation_id: str | None = None,
    ) -> None:
        stamp = _now()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO idempotency (
                    user_id, client_request_id, request_fingerprint, conversation_id,
                    status, response_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, client_request_id) DO UPDATE SET
                    request_fingerprint = excluded.request_fingerprint,
                    conversation_id = excluded.conversation_id,
                    status = excluded.status,
                    response_json = excluded.response_json,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    client_request_id,
                    request_fingerprint,
                    conversation_id,
                    IdempotencyStatus.COMPLETED.value,
                    json.dumps(payload),
                    stamp,
                    stamp,
                ),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def fail_idempotent(self, user_id: str, client_request_id: str) -> None:
        stamp = _now()
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE idempotency
                SET status = ?, updated_at = ?
                WHERE user_id = ? AND client_request_id = ?
                """,
                (IdempotencyStatus.FAILED.value, stamp, user_id, client_request_id),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def mark_recovery_required(self, user_id: str, client_request_id: str) -> None:
        stamp = _now()
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE idempotency
                SET status = ?, updated_at = ?
                WHERE user_id = ? AND client_request_id = ?
                """,
                (
                    IdempotencyStatus.RECOVERY_REQUIRED.value,
                    stamp,
                    user_id,
                    client_request_id,
                ),
            )
            conn.commit()
        finally:
            if not self._memory:
                conn.close()

    def put_idempotent(self, user_id: str, client_request_id: str, payload: dict[str, Any]) -> None:
        """Backward-compatible completed write (fingerprint unknown → empty)."""
        self.complete_idempotent(
            user_id,
            client_request_id,
            payload,
            request_fingerprint="",
            conversation_id=payload.get("conversation_id"),
        )

    def _row_to_message(self, row: sqlite3.Row) -> ApiMessage:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        return self._message_from_parts(
            row["id"],
            row["conversation_id"],
            row["role"],
            row["type"],
            row["text"],
            row["status"],
            row["created_at"],
            payload,
        )

    def _message_from_parts(
        self,
        mid: str,
        conversation_id_value: str,
        role: str,
        type_: str,
        text: str,
        status: str | None,
        created_at: str,
        payload: dict[str, Any] | None,
    ) -> ApiMessage:
        payload = payload or {}
        clarification = None
        if payload.get("clarification"):
            raw = payload["clarification"]
            clarification = ApiClarification(
                id=raw["id"],
                mode=ApiClarificationMode(raw["mode"]),
                options=[ApiClarificationOption(**opt) for opt in raw.get("options", [])],
            )
        error = None
        if payload.get("error"):
            error = ApiErrorBody(**payload["error"])
        operation = None
        if payload.get("operation"):
            operation = ApiOperation(
                kind=ApiOperationKind(payload["operation"]["kind"]),
                outcome=ApiOperationOutcome(payload["operation"]["outcome"]),
            )
        return ApiMessage(
            id=mid,
            conversation_id=conversation_id_value,
            role=ApiMessageRole(role),
            type=type_,
            text=text,
            status=ApiMessageStatus(status) if status else None,
            created_at=created_at,
            clarification=clarification,
            error=error,
            data=payload.get("data"),
            operation=operation,
        )
