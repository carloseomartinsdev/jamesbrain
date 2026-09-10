from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class ConversationRecord:
    id: str
    principal_sub: str
    title: str
    pke_conversation_id: str | None
    created_at: str
    updated_at: str


class ConversationStore:
    """James conversation authority. PKE conversation_id is an internal binding."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    principal_sub TEXT NOT NULL,
                    title TEXT NOT NULL,
                    pke_conversation_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    type TEXT,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    extra_json TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                """
            )

    def create(self, principal_sub: str, title: str | None = None) -> ConversationRecord:
        rec = ConversationRecord(
            id=str(uuid.uuid4()),
            principal_sub=principal_sub,
            title=(title or "Nova conversa").strip() or "Nova conversa",
            pke_conversation_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        with self._connect() as con:
            con.execute(
                "INSERT INTO conversations (id, principal_sub, title, pke_conversation_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (rec.id, rec.principal_sub, rec.title, rec.pke_conversation_id, rec.created_at, rec.updated_at),
            )
        return rec

    def get(self, conversation_id: str, principal_sub: str) -> ConversationRecord | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM conversations WHERE id = ? AND principal_sub = ?",
                (conversation_id, principal_sub),
            ).fetchone()
        if row is None:
            return None
        return ConversationRecord(
            id=row["id"],
            principal_sub=row["principal_sub"],
            title=row["title"],
            pke_conversation_id=row["pke_conversation_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def bind_pke(self, conversation_id: str, pke_conversation_id: str) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE conversations SET pke_conversation_id = ?, updated_at = ? WHERE id = ?",
                (pke_conversation_id, _now(), conversation_id),
            )

    def append_message(
        self,
        conversation_id: str,
        role: str,
        text: str,
        type_: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        mid = str(uuid.uuid4())
        with self._connect() as con:
            con.execute(
                "INSERT INTO messages (id, conversation_id, role, type, text, created_at, extra_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    mid,
                    conversation_id,
                    role,
                    type_,
                    text,
                    _now(),
                    json.dumps(extra, ensure_ascii=False) if extra else None,
                ),
            )
            con.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (_now(), conversation_id),
            )
        return mid

    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC",
                (conversation_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            extra = json.loads(row["extra_json"]) if row["extra_json"] else {}
            item = {
                "id": row["id"],
                "role": row["role"],
                "type": row["type"],
                "text": row["text"],
                "created_at": row["created_at"],
            }
            item.update(extra)
            out.append(item)
        return out
