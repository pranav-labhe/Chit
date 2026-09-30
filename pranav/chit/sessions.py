"""Chat sessions: the turn-by-turn history of one conversation, kept under a session id.

Sessions are different from memory (``memory.py``): memory holds durable facts recalled
by keyword across every conversation, while a session holds the ordered messages of a
single conversation. Neither changes the model's weights.

Storage is SQLite (stdlib, transactional, safe across threads), like the knowledge
store. A session keeps at most ``max_turns`` messages (the oldest are dropped), and
sessions idle for longer than a chosen number of days can be pruned.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

ROLES = ("user", "assistant")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, seq);
"""


class SessionNotFound(KeyError):
    """No session has this id (it never existed, was deleted, or was pruned)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, path: str | Path = "data/sessions.db", max_turns: int = 200):
        if max_turns < 2:
            raise ValueError("max_turns must be at least 2 (one user message and one reply)")
        self.path = Path(path)
        self.max_turns = max_turns
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # One short-lived connection per operation: safe from any thread; ``with db:``
        # commits on success and rolls back on error.
        db = sqlite3.connect(self.path, timeout=30, isolation_level="DEFERRED")
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    # ---------------------------------------------------------------- writes

    def create(self) -> dict:
        sid, now = uuid.uuid4().hex, _now()
        with self._conn() as db:
            db.execute("INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)", (sid, now, now))
        return {"id": sid, "created_at": now, "updated_at": now, "turns": 0}

    def append(self, session_id: str, turns: Iterable[tuple[str, str]]) -> int:
        """Add ``(role, content)`` messages atomically; return how many were added."""
        rows = []
        for role, content in turns:
            if role not in ROLES:
                raise ValueError(f"role must be one of {ROLES}, got {role!r}")
            rows.append((role, content))
        now = _now()
        with self._conn() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone():
                raise SessionNotFound(session_id)
            db.executemany("INSERT INTO turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                           [(session_id, role, content, now) for role, content in rows])
            db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            db.execute("DELETE FROM turns WHERE session_id = ? AND seq NOT IN "
                       "(SELECT seq FROM turns WHERE session_id = ? ORDER BY seq DESC LIMIT ?)",
                       (session_id, session_id, self.max_turns))
        return len(rows)

    def delete(self, session_id: str) -> bool:
        with self._conn() as db:
            return db.execute("DELETE FROM sessions WHERE id = ?", (session_id,)).rowcount > 0

    def prune(self, older_than_days: float) -> int:
        """Delete sessions not updated for ``older_than_days``; return how many were removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        with self._conn() as db:
            return db.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,)).rowcount

    # ---------------------------------------------------------------- reads

    def get(self, session_id: str) -> dict:
        with self._conn() as db:
            r = db.execute("SELECT s.id, s.created_at, s.updated_at, "
                           "(SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) AS turns "
                           "FROM sessions s WHERE s.id = ?", (session_id,)).fetchone()
        if r is None:
            raise SessionNotFound(session_id)
        return dict(r)

    def history(self, session_id: str, limit: int | None = None) -> list[dict]:
        """Messages oldest-first; with ``limit``, only the most recent ones."""
        with self._conn() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone():
                raise SessionNotFound(session_id)
            if limit is None:
                rows = db.execute("SELECT role, content, created_at FROM turns WHERE session_id = ? "
                                  "ORDER BY seq", (session_id,)).fetchall()
            else:
                rows = db.execute("SELECT role, content, created_at FROM (SELECT * FROM turns WHERE session_id = ? "
                                  "ORDER BY seq DESC LIMIT ?) ORDER BY seq", (session_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def list(self, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        with self._conn() as db:
            total = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            rows = db.execute("SELECT s.id, s.created_at, s.updated_at, "
                              "(SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) AS turns "
                              "FROM sessions s ORDER BY s.updated_at DESC, s.id LIMIT ? OFFSET ?",
                              (limit, offset)).fetchall()
        return [dict(r) for r in rows], total
