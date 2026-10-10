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
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .facts import extract_explicit_facts
from .summarization import summarize_history

ROLES = ("user", "assistant")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    summary_through_seq INTEGER NOT NULL DEFAULT 0,
    summary_enabled INTEGER NOT NULL DEFAULT 1,
    summary_status TEXT NOT NULL DEFAULT 'empty',
    summary_error TEXT,
    facts_json TEXT NOT NULL DEFAULT '[]',
    facts_enabled INTEGER NOT NULL DEFAULT 1,
    facts_through_seq INTEGER NOT NULL DEFAULT 0,
    context_version INTEGER NOT NULL DEFAULT 1,
    context_updated_at TEXT
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
            columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            migrations = {
                "summary": "TEXT NOT NULL DEFAULT ''",
                "summary_through_seq": "INTEGER NOT NULL DEFAULT 0",
                "summary_enabled": "INTEGER NOT NULL DEFAULT 1",
                "summary_status": "TEXT NOT NULL DEFAULT 'empty'",
                "summary_error": "TEXT",
                "facts_json": "TEXT NOT NULL DEFAULT '[]'",
                "facts_enabled": "INTEGER NOT NULL DEFAULT 1",
                "facts_through_seq": "INTEGER NOT NULL DEFAULT 0",
                "context_version": "INTEGER NOT NULL DEFAULT 1",
                "context_updated_at": "TEXT",
            }
            for name, declaration in migrations.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE sessions ADD COLUMN {name} {declaration}")

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
            session = db.execute("SELECT facts_json,facts_enabled FROM sessions WHERE id = ?",
                                 (session_id,)).fetchone()
            if not session:
                raise SessionNotFound(session_id)
            inserted = []
            for role, content in rows:
                cursor = db.execute("INSERT INTO turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                                    (session_id, role, content, now))
                inserted.append((cursor.lastrowid, role, content))
            facts = {fact["key"]: fact for fact in json.loads(session["facts_json"])}
            if session["facts_enabled"]:
                for seq, role, content in inserted:
                    if role != "user":
                        continue
                    for fact in extract_explicit_facts(content):
                        previous = facts.get(fact["key"])
                        if previous and previous["value"].casefold() == fact["value"].casefold():
                            continue
                        facts[fact["key"]] = {**fact, "source_turn_seq": seq,
                                               "origin": "explicit_user_statement",
                                               "confidence": 1.0, "updated_at": now,
                                               "supersedes_turn_seq": previous.get("source_turn_seq")
                                               if previous else None}
                if any(role == "user" for _, role, _ in inserted):
                    db.execute("UPDATE sessions SET facts_json=?,facts_through_seq=?,context_updated_at=? "
                               "WHERE id=?", (json.dumps(list(facts.values()), ensure_ascii=False),
                                               max(seq for seq, _, _ in inserted), now, session_id))
            db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            total = db.execute("SELECT COUNT(*) FROM turns WHERE session_id=?", (session_id,)).fetchone()[0]
            if total > self.max_turns:
                db.execute("UPDATE sessions SET summary_status=CASE WHEN summary_enabled=1 "
                           "THEN 'pending' ELSE summary_status END WHERE id=?", (session_id,))
                if not db.execute("SELECT summary_enabled FROM sessions WHERE id=?", (session_id,)).fetchone()[0]:
                    db.execute("DELETE FROM turns WHERE session_id=? AND seq NOT IN "
                               "(SELECT seq FROM turns WHERE session_id=? ORDER BY seq DESC LIMIT ?)",
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
            r = db.execute("SELECT s.*, "
                           "(SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) AS turns "
                           "FROM sessions s WHERE s.id = ?", (session_id,)).fetchone()
        if r is None:
            raise SessionNotFound(session_id)
        session = dict(r)
        session["facts"] = json.loads(session.pop("facts_json"))
        session["facts_enabled"] = bool(session["facts_enabled"])
        return session

    def facts(self, session_id: str) -> dict:
        session = self.get(session_id)
        return {"session_id": session_id, "enabled": session["facts_enabled"],
                "facts": session["facts"], "through_turn_seq": session["facts_through_seq"],
                "context_version": session["context_version"],
                "updated_at": session["context_updated_at"]}

    def set_facts_enabled(self, session_id: str, enabled: bool) -> dict:
        with self._conn() as db:
            cursor = db.execute("UPDATE sessions SET facts_enabled=?,context_updated_at=? WHERE id=?",
                                (int(enabled), _now(), session_id))
            if not cursor.rowcount:
                raise SessionNotFound(session_id)
        return self.facts(session_id)

    def clear_facts(self, session_id: str) -> dict:
        with self._conn() as db:
            cursor = db.execute("UPDATE sessions SET facts_json='[]',context_updated_at=? WHERE id=?",
                                (_now(), session_id))
            if not cursor.rowcount:
                raise SessionNotFound(session_id)
        return self.facts(session_id)

    def summary_needed(self, session_id: str) -> bool:
        with self._conn() as db:
            row = db.execute("SELECT s.summary_enabled,s.summary_through_seq,"
                              "(SELECT COUNT(*) FROM turns t WHERE t.session_id=s.id) AS n "
                              "FROM sessions s WHERE s.id=?", (session_id,)).fetchone()
        if row is None:
            raise SessionNotFound(session_id)
        return bool(row["summary_enabled"] and row["n"] > self.max_turns)

    def pending_summary_sessions(self) -> list[str]:
        with self._conn() as db:
            rows = db.execute("""SELECT s.id FROM sessions s
                WHERE s.summary_enabled=1 AND
                (SELECT COUNT(*) FROM turns t WHERE t.session_id=s.id)>? ORDER BY s.updated_at""",
                              (self.max_turns,)).fetchall()
        return [row["id"] for row in rows]

    def summarize_overflow(self, session_id: str) -> dict:
        """Summarize a stable old prefix; only prune it after the summary commits."""
        with self._conn() as db:
            session = db.execute("SELECT summary,summary_through_seq,summary_enabled FROM sessions WHERE id=?",
                                 (session_id,)).fetchone()
            if session is None:
                raise SessionNotFound(session_id)
            if session["summary_enabled"]:
                rows = db.execute("SELECT seq,role,content FROM turns WHERE session_id=? ORDER BY seq",
                                  (session_id,)).fetchall()
                overflow = len(rows) - self.max_turns
                overflow -= overflow % 2  # keep complete user/assistant exchanges
                if overflow >= 2:
                    prefix = rows[:overflow]
                    covered = int(prefix[-1]["seq"])
                    turns = [dict(row) for row in prefix if int(row["seq"]) > int(session["summary_through_seq"])]
                    if turns:
                        summary = summarize_history(turns, session["summary"])
                        now = _now()
                        db.execute("UPDATE sessions SET summary=?,summary_through_seq=?,summary_status='ready',"
                                   "summary_error=NULL,context_updated_at=? WHERE id=?",
                                   (summary, covered, now, session_id))
                        db.execute("DELETE FROM turns WHERE session_id=? AND seq<=?", (session_id, covered))
        return self.get(session_id)

    def set_summary_error(self, session_id: str, error: str) -> None:
        with self._conn() as db:
            db.execute("UPDATE sessions SET summary_status='error',summary_error=? WHERE id=?",
                       (error[:500], session_id))

    def set_summary_enabled(self, session_id: str, enabled: bool) -> dict:
        with self._conn() as db:
            cursor = db.execute("UPDATE sessions SET summary_enabled=?,summary_status=CASE "
                                "WHEN ?=0 THEN 'disabled' WHEN summary<>'' THEN 'ready' ELSE 'empty' END,"
                                "summary_error=NULL,context_updated_at=? WHERE id=?",
                                (int(enabled), int(enabled), _now(), session_id))
            if not cursor.rowcount:
                raise SessionNotFound(session_id)
            if not enabled:
                db.execute("DELETE FROM turns WHERE session_id=? AND seq NOT IN "
                           "(SELECT seq FROM turns WHERE session_id=? ORDER BY seq DESC LIMIT ?)",
                           (session_id, session_id, self.max_turns))
        return self.get(session_id)

    def clear_summary(self, session_id: str) -> dict:
        with self._conn() as db:
            cursor = db.execute("UPDATE sessions SET summary='',summary_through_seq=0,"
                                "summary_status=CASE WHEN summary_enabled=1 THEN 'empty' ELSE 'disabled' END,"
                                "summary_error=NULL,context_updated_at=? WHERE id=?", (_now(), session_id))
            if not cursor.rowcount:
                raise SessionNotFound(session_id)
        return self.get(session_id)

    def refresh_facts(self, session_id: str) -> dict:
        """Rebuild active facts from retained user turns; no model inference is used."""
        with self._conn() as db:
            session = db.execute("SELECT facts_enabled FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not session:
                raise SessionNotFound(session_id)
            if not session["facts_enabled"]:
                raise ValueError("session fact extraction is disabled")
            rows = db.execute("SELECT seq,content FROM turns WHERE session_id=? AND role='user' ORDER BY seq",
                              (session_id,)).fetchall()
            active = {}
            for row in rows:
                for fact in extract_explicit_facts(row["content"]):
                    previous = active.get(fact["key"])
                    if previous and previous["value"].casefold() == fact["value"].casefold():
                        continue
                    active[fact["key"]] = {**fact, "source_turn_seq": row["seq"],
                                             "origin": "explicit_user_statement", "confidence": 1.0,
                                             "updated_at": _now(),
                                             "supersedes_turn_seq": previous.get("source_turn_seq")
                                             if previous else None}
            latest = int(rows[-1]["seq"]) if rows else 0
            db.execute("UPDATE sessions SET facts_json=?,facts_through_seq=?,context_updated_at=? WHERE id=?",
                       (json.dumps(list(active.values()), ensure_ascii=False), latest, _now(), session_id))
        return self.facts(session_id)

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
