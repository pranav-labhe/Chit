"""Knowledge store: material taught to Chit that becomes training data on request.

Knowledge is different from memory. Memory (``memory.py``) is recalled at
inference time and never changes the weights. Knowledge is queued here and
only reaches the weights when a training run is started with it. Every entry
starts ``pending`` and becomes ``trained`` once a run that included it has
succeeded *and* been promoted to the served model.

Kinds and their payloads::

    text       {"text": ...}                                  free text
    qa         {"question": ..., "answer": ...}               rendered in the chat format
    reasoning  {"input": ..., "reasoning": ..., "answer": ...}

Storage is SQLite (stdlib, transactional, safe across threads). Identical
content is stored once: re-teaching it returns the existing entry.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .formats import render_qa, render_reasoning, render_text

KINDS: dict[str, tuple[str, ...]] = {
    "text": ("text",),
    "qa": ("question", "answer"),
    "reasoning": ("input", "reasoning", "answer"),
}
STATUSES = ("pending", "trained")
MAX_FIELD_CHARS = 20_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    payload         TEXT NOT NULL,
    content_hash    TEXT NOT NULL UNIQUE,
    tags            TEXT NOT NULL DEFAULT '[]',
    source          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    trained_at      TEXT,
    trained_job_id  TEXT
);
CREATE INDEX IF NOT EXISTS knowledge_status ON knowledge(status, created_at);
"""


class KnowledgeError(ValueError):
    """Invalid knowledge entry."""


@dataclass(frozen=True)
class AddResult:
    entry: dict
    created: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def validate(kind: str, payload: dict) -> dict:
    """Return the payload restricted to the kind's fields, stripped; raise KnowledgeError."""
    if kind not in KINDS:
        raise KnowledgeError(f"unknown kind {kind!r}; expected one of {', '.join(KINDS)}")
    if not isinstance(payload, dict):
        raise KnowledgeError("payload must be an object")
    extra = set(payload) - set(KINDS[kind])
    if extra:
        raise KnowledgeError(f"unexpected field(s) for {kind}: {', '.join(sorted(extra))}")
    clean = {}
    for f in KINDS[kind]:
        v = payload.get(f)
        if not isinstance(v, str) or not v.strip():
            raise KnowledgeError(f"{kind}.{f} must be a non-empty string")
        if len(v) > MAX_FIELD_CHARS:
            raise KnowledgeError(f"{kind}.{f} exceeds {MAX_FIELD_CHARS} characters")
        clean[f] = v.strip()
    return clean


def content_hash(kind: str, payload: dict) -> str:
    norm = {k: _normalise(v) for k, v in payload.items()}
    return hashlib.sha256(json.dumps([kind, norm], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def render(entry: dict) -> str:
    """Training text for one entry."""
    p = entry["payload"]
    if entry["kind"] == "qa":
        return render_qa(p["question"], p["answer"])
    if entry["kind"] == "reasoning":
        return render_reasoning(p["input"], p["reasoning"], p["answer"])
    return render_text(p["text"])


class KnowledgeStore:
    def __init__(self, path: str | Path = "data/knowledge.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # One short-lived connection per operation: safe from any thread, and the
        # `with db:` block commits on success or rolls back on error.
        db = sqlite3.connect(self.path, timeout=30, isolation_level="DEFERRED")
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        return {
            "id": r["id"], "kind": r["kind"], "payload": json.loads(r["payload"]),
            "tags": json.loads(r["tags"]), "source": r["source"], "status": r["status"],
            "created_at": r["created_at"], "trained_at": r["trained_at"], "trained_job_id": r["trained_job_id"],
        }

    # ---------------------------------------------------------------- writes

    def add_many(self, items: Iterable[dict]) -> list[AddResult]:
        """Add entries atomically: all are stored, or none (on a validation error).

        Each item is ``{"kind", "payload", "tags"?, "source"?}``.
        """
        prepared = []
        for n, it in enumerate(items):
            try:
                kind = it.get("kind")
                payload = validate(kind, it.get("payload"))
            except KnowledgeError as e:
                raise KnowledgeError(f"item {n}: {e}") from None
            tags = sorted({t.strip() for t in it.get("tags") or [] if t and t.strip()})
            prepared.append((kind, payload, tags, it.get("source"), content_hash(kind, payload)))

        results: list[AddResult] = []
        with self._conn() as db:
            for kind, payload, tags, source, h in prepared:
                existing = db.execute("SELECT * FROM knowledge WHERE content_hash = ?", (h,)).fetchone()
                if existing:
                    results.append(AddResult(self._row(existing), created=False))
                    continue
                row = (uuid.uuid4().hex, kind, json.dumps(payload, ensure_ascii=False), h,
                       json.dumps(tags, ensure_ascii=False), source, "pending", _now())
                db.execute("INSERT INTO knowledge (id, kind, payload, content_hash, tags, source, status, created_at)"
                           " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", row)
                results.append(AddResult(self._row(db.execute(
                    "SELECT * FROM knowledge WHERE id = ?", (row[0],)).fetchone()), created=True))
        return results

    def add(self, kind: str, payload: dict, tags: list[str] | None = None, source: str | None = None) -> AddResult:
        return self.add_many([{"kind": kind, "payload": payload, "tags": tags, "source": source}])[0]

    def delete(self, entry_id: str) -> bool:
        with self._conn() as db:
            return db.execute("DELETE FROM knowledge WHERE id = ?", (entry_id,)).rowcount > 0

    def mark_trained(self, ids: Iterable[str], job_id: str) -> int:
        ids = list(ids)
        if not ids:
            return 0
        now, n = _now(), 0
        with self._conn() as db:
            for i in range(0, len(ids), 500):  # stay under SQLite's bound-parameter limit
                chunk = ids[i:i + 500]
                n += db.execute(
                    f"UPDATE knowledge SET status='trained', trained_at=?, trained_job_id=? "
                    f"WHERE id IN ({','.join('?' * len(chunk))})", (now, job_id, *chunk)).rowcount
        return n

    # ---------------------------------------------------------------- reads

    def get(self, entry_id: str) -> dict | None:
        with self._conn() as db:
            r = db.execute("SELECT * FROM knowledge WHERE id = ?", (entry_id,)).fetchone()
        return self._row(r) if r else None

    @staticmethod
    def _where(status: str | None, kind: str | None, tags: list[str] | None) -> tuple[str, list]:
        clauses, args = [], []
        if status:
            clauses.append("status = ?"); args.append(status)
        if kind:
            clauses.append("kind = ?"); args.append(kind)
        for t in tags or []:
            clauses.append("EXISTS (SELECT 1 FROM json_each(knowledge.tags) WHERE value = ?)"); args.append(t)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", args

    def list(self, status: str | None = None, kind: str | None = None, tags: list[str] | None = None,
             limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        where, args = self._where(status, kind, tags)
        with self._conn() as db:
            total = db.execute(f"SELECT COUNT(*) FROM knowledge{where}", args).fetchone()[0]
            rows = db.execute(f"SELECT * FROM knowledge{where} ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
                              (*args, limit, offset)).fetchall()
        return [self._row(r) for r in rows], total

    def select(self, status: str | None = None, tags: list[str] | None = None) -> list[dict]:
        """Every matching entry, oldest first (stable order for reproducible datasets)."""
        where, args = self._where(status, None, tags)
        with self._conn() as db:
            rows = db.execute(f"SELECT * FROM knowledge{where} ORDER BY created_at, id", args).fetchall()
        return [self._row(r) for r in rows]

    def stats(self) -> dict:
        with self._conn() as db:
            rows = db.execute("SELECT kind, status, COUNT(*) AS n FROM knowledge GROUP BY kind, status").fetchall()
        out = {"total": 0, "by_status": {s: 0 for s in STATUSES}, "by_kind": {k: 0 for k in KINDS}}
        for r in rows:
            out["total"] += r["n"]
            out["by_status"][r["status"]] = out["by_status"].get(r["status"], 0) + r["n"]
            out["by_kind"][r["kind"]] = out["by_kind"].get(r["kind"], 0) + r["n"]
        return out


# -------------------------------------------------------------------- datasets


@dataclass(frozen=True)
class BuiltDataset:
    train_file: Path
    manifest_file: Path
    entry_ids: list[str]
    size_bytes: int
    sha256: str


def build_dataset(entries: list[dict], out_dir: str | Path, *, base_text: str = "", repeat: int = 1,
                  max_bytes: int | None = None) -> BuiltDataset:
    """Write ``train.txt`` = base corpus + rendered knowledge (repeated), plus a manifest.

    ``repeat`` upweights knowledge against a larger base corpus: a small model
    sees each window at random, so a fact that appears once in a large file is
    rarely sampled. The manifest records exactly which entries went in, so
    every trained checkpoint can be traced back to its knowledge.
    """
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rendered = "".join(render(e) for e in entries)
    parts = [base_text.rstrip("\n") + "\n"] if base_text.strip() else []
    parts += [rendered] * repeat
    text = "".join(parts)
    data = text.encode("utf-8", errors="surrogatepass")
    if max_bytes is not None and len(data) > max_bytes:
        raise ValueError(f"training dataset would be {len(data)} bytes; the limit is {max_bytes}")
    train_file = out / "train.txt"
    train_file.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    manifest = {
        "created_at": _now(),
        "entries": len(entries),
        "entry_ids": [e["id"] for e in entries],
        "repeat": repeat,
        "base_bytes": len(base_text.encode("utf-8", errors="surrogatepass")),
        "knowledge_bytes": len(rendered.encode("utf-8", errors="surrogatepass")),
        "size_bytes": len(data),
        "sha256": digest,
    }
    manifest_file = out / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return BuiltDataset(train_file, manifest_file, manifest["entry_ids"], len(data), digest)
