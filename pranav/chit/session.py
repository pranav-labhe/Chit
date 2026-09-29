"""Persistent conversational sessions, separate from long-term MemoryStore.

A session contains only turn-by-turn conversation history. It is context for the
current conversation, not learned knowledge and not long-term memory.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK(role IN ('user', 'chit')),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    """SQLite-backed conversation history with a bounded turn count per session."""

    def __init__(self, path: str | Path = "data/sessions.db", max_turns: int = 20):
        if max_turns < 2:
            raise ValueError("max_turns must be >= 2")
        self.path = Path(path)
        self.max_turns = max_turns
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30, isolation_level="DEFERRED")
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def create(self) -> dict:
        session_id = uuid.uuid4().hex
        now = _now()
        with self._lock, self._conn() as db:
            db.execute(
                "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
        return {"id": session_id, "created_at": now, "updated_at": now, "turns": []}

    def get(self, session_id: str) -> dict | None:
        with self._lock, self._conn() as db:
            row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            turns = db.execute(
                "SELECT role, content, created_at FROM turns WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "turns": [dict(t) for t in turns],
        }

    def turns(self, session_id: str) -> list[dict]:
        session = self.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session["turns"]

    def append_exchange(self, session_id: str, user_text: str, chit_text: str) -> None:
        user_text = user_text.strip()
        chit_text = chit_text.strip()
        if not user_text or not chit_text:
            raise ValueError("session turn content must not be empty")

        now = _now()
        with self._lock, self._conn() as db:
            if db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is None:
                raise KeyError(session_id)
            db.executemany(
                "INSERT INTO turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                ((session_id, "user", user_text, now), (session_id, "chit", chit_text, now)),
            )
            excess = db.execute(
                "SELECT COUNT(*) - ? FROM turns WHERE session_id = ?",
                (self.max_turns, session_id),
            ).fetchone()[0]
            if excess > 0:
                db.execute(
                    "DELETE FROM turns WHERE id IN ("
                    "SELECT id FROM turns WHERE session_id = ? ORDER BY id LIMIT ?"
                    ")",
                    (session_id, excess),
                )
            db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))

    def clear(self, session_id: str) -> bool:
        with self._lock, self._conn() as db:
            if db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is None:
                return False
            db.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))
            return True

    def delete(self, session_id: str) -> bool:
        with self._lock, self._conn() as db:
            return db.execute("DELETE FROM sessions WHERE id = ?", (session_id,)).rowcount > 0
