"""External memory stores for facts Chit can recall without retraining.

``SQLiteMemoryStore`` is the API's canonical store and keeps legacy JSON import
support. ``MemoryStore`` remains available for callers that explicitly need the
original atomic JSON-file behavior.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_WORD = re.compile(r"\w+", re.UNICODE)
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from has have how i in is it of on or "
    "should the to was what when where which who why will with you".split())


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS}


_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL NOT NULL CHECK (importance BETWEEN 0 AND 1),
    tags TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source TEXT
);
CREATE INDEX IF NOT EXISTS memory_created ON memory(created_at);
CREATE TABLE IF NOT EXISTS memory_embeddings (
    memory_id TEXT NOT NULL REFERENCES memory(id) ON DELETE CASCADE,
    model_version TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    vector BLOB,
    content_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (memory_id, model_version)
);
CREATE INDEX IF NOT EXISTS memory_embeddings_status ON memory_embeddings(status, model_version);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
CREATE TABLE IF NOT EXISTS memory_imports (
    source TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL,
    PRIMARY KEY(source, sha256)
);
"""


class SQLiteMemoryStore:
    """SQLite source of truth for durable memories; vectors are rebuildable."""

    def __init__(self, path: str | Path, *, import_json_path: str | Path | None = None,
                 seed_path: str | Path | None = "data/memory_seed.json", embedding_provider=None,
                 semantic_threshold: float | None = None, semantic_weight: float = 0.65):
        self.path = Path(path)
        self.embedding_provider = embedding_provider
        self.semantic_threshold = semantic_threshold
        self.semantic_weight = float(semantic_weight)
        if not 0.0 <= self.semantic_weight <= 1.0:
            raise ValueError("semantic_weight must be in [0, 1]")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fts_available = False
        self._faiss_index = None
        self._ann_lock = threading.RLock()
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("PRAGMA journal_mode=WAL")
        with self._conn() as db:
            db.executescript(_MEMORY_SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(memory_embeddings)")}
            if "content_hash" not in columns:
                db.execute("ALTER TABLE memory_embeddings ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''")
            db.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
                       "VALUES(2, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
            db.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
                       "VALUES(3, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
            try:
                db.executescript("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, content, tags);
                    CREATE TRIGGER IF NOT EXISTS memory_fts_insert AFTER INSERT ON memory BEGIN
                      INSERT INTO memory_fts(rowid,id,content,tags)
                      VALUES(new.rowid,new.id,new.content,new.tags);
                    END;
                    CREATE TRIGGER IF NOT EXISTS memory_fts_delete AFTER DELETE ON memory BEGIN
                      DELETE FROM memory_fts WHERE rowid=old.rowid;
                    END;
                    CREATE TRIGGER IF NOT EXISTS memory_fts_update AFTER UPDATE ON memory BEGIN
                      DELETE FROM memory_fts WHERE rowid=old.rowid;
                      INSERT INTO memory_fts(rowid,id,content,tags)
                      VALUES(new.rowid,new.id,new.content,new.tags);
                    END;
                    INSERT INTO memory_fts(rowid,id,content,tags)
                    SELECT rowid,id,content,tags FROM memory
                    WHERE rowid NOT IN (SELECT rowid FROM memory_fts);
                """)
                self._fts_available = True
            except sqlite3.OperationalError:
                self._fts_available = False
        if self.count() == 0:
            source = Path(import_json_path) if import_json_path else None
            seed = Path(seed_path) if seed_path else None
            candidate = source if source and source.exists() else seed if seed and seed.exists() else None
            if candidate:
                self.import_json(candidate)
        self._rebuild_faiss_index()

    @contextmanager
    def _conn(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level="DEFERRED")
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def count(self) -> int:
        with self._conn() as db:
            return int(db.execute("SELECT COUNT(*) FROM memory").fetchone()[0])

    def embedding_status(self) -> dict:
        total = self.count()
        provider = self.embedding_provider
        if provider is None:
            return {"mode": "keyword", "ann_backend": "unavailable", "model_version": None,
                    "total": total, "indexed": 0}
        with self._conn() as db:
            rows = db.execute("""SELECT m.content,e.content_hash FROM memory m JOIN memory_embeddings e
                ON e.memory_id=m.id WHERE e.model_version=? AND e.status='ready' AND e.dimension=?""",
                (provider.model_version, provider.dimension)).fetchall()
        indexed = sum(1 for row in rows if row["content_hash"] == self._content_hash(row["content"]))
        mode = "hybrid" if indexed == total else "hybrid_with_keyword_fallback"
        return {"mode": mode,
                "ann_backend": "faiss_hnsw" if self._faiss_index is not None else "exact_scan",
                "model_version": provider.model_version, "total": total, "indexed": indexed,
                "pending": max(0, total - indexed)}

    @staticmethod
    def _normalize(item: dict) -> dict:
        if not isinstance(item, dict):
            raise ValueError("each memory must be a JSON object")
        if not item.get("id"):
            raise ValueError("imported memory is missing its ID")
        content = item.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("memory content must not be empty")
        importance = float(item.get("importance", 0.5))
        if not 0.0 <= importance <= 1.0:
            raise ValueError("memory importance must be in [0, 1]")
        tags = item.get("tags") or []
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("memory tags must be a list of strings")
        created_at = item.get("created_at") or datetime.now(timezone.utc).isoformat()
        source = item.get("source")
        if not isinstance(created_at, str) or (source is not None and not isinstance(source, str)):
            raise ValueError("memory timestamps and sources must be strings")
        return {"id": str(item["id"]),
                "type": str(item.get("type", "experience")), "content": content,
                "importance": importance, "tags": list(tags),
                "created_at": created_at, "source": source}

    def import_json(self, source: str | Path, *, dry_run: bool = False) -> dict:
        """Validate then idempotently import a JSON-list backup, preserving IDs."""
        source = Path(source)
        source_bytes = source.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        raw = json.loads(source_bytes.decode("utf-8"))
        if not isinstance(raw, list):
            raise ValueError("memory import source must contain a JSON list")
        records = [self._normalize(item) for item in raw]
        ids = [m["id"] for m in records]
        if len(ids) != len(set(ids)):
            raise ValueError("memory import contains duplicate IDs")
        report = {"source": str(source), "sha256": source_sha256,
                  "records": len(records), "dry_run": dry_run}
        if not dry_run:
            with self._conn() as db:
                db.executemany("""INSERT INTO memory(id,type,content,importance,tags,created_at,source)
                    VALUES(:id,:type,:content,:importance,:tags,:created_at,:source)
                    ON CONFLICT(id) DO NOTHING""",
                    [{**m, "tags": json.dumps(m["tags"], ensure_ascii=False)} for m in records])
                for item in records:
                    row = db.execute("SELECT * FROM memory WHERE id=?", (item["id"],)).fetchone()
                    actual = self._decode(row)
                    expected = {**item, "source": item.get("source")}
                    if any(actual.get(k) != expected.get(k) for k in
                           ("type", "content", "importance", "tags", "created_at", "source")):
                        raise ValueError(f"memory ID {item['id']} already exists with different data")
                db.execute("INSERT OR IGNORE INTO memory_imports(source,sha256,record_count,imported_at) "
                           "VALUES(?,?,?,?)", (str(source.resolve()), source_sha256, len(records),
                                                datetime.now(timezone.utc).isoformat()))
        report["destination_count"] = self.count() if not dry_run else None
        return report

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        item = dict(row)
        item["tags"] = json.loads(item["tags"])
        return item

    def add(self, content: str, memory_type: str = "experience", importance: float = 0.5,
            tags: list[str] | None = None, source: str | None = None) -> dict:
        item = MemoryStore._make_item(content, memory_type, importance, tags, source)
        with self._conn() as db:
            db.execute("INSERT INTO memory VALUES(?,?,?,?,?,?,?)",
                       (item["id"], item["type"], item["content"], item["importance"],
                        json.dumps(item["tags"], ensure_ascii=False), item["created_at"], item.get("source")))
        if self.embedding_provider is not None:
            self._embed_records([item])
        return item

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _embed_records(self, records: list[dict], *, refresh_index: bool = True) -> int:
        if not records or self.embedding_provider is None:
            return 0
        version = str(self.embedding_provider.model_version)
        try:
            import numpy as np
            vectors = np.asarray(self.embedding_provider.encode([m["content"] for m in records]), dtype=np.float32)
            expected = (len(records), int(self.embedding_provider.dimension))
            if vectors.shape != expected or not np.isfinite(vectors).all():
                raise ValueError(f"embedding vectors must have shape {expected} and finite values")
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            if (norms == 0).any():
                raise ValueError("embedding provider returned a zero vector")
            vectors = vectors / norms
            now = datetime.now(timezone.utc).isoformat()
            with self._conn() as db:
                db.executemany("""INSERT INTO memory_embeddings
                    (memory_id,model_version,dimension,vector,content_hash,status,updated_at)
                    VALUES(?,?,?,?,?,'ready',?)
                    ON CONFLICT(memory_id,model_version) DO UPDATE SET
                    dimension=excluded.dimension, vector=excluded.vector,
                    content_hash=excluded.content_hash, status='ready', updated_at=excluded.updated_at""",
                    [(item["id"], version, vectors[i].size, vectors[i].tobytes(),
                      self._content_hash(item["content"]), now) for i, item in enumerate(records)])
            if refresh_index:
                self._rebuild_faiss_index()
            return len(records)
        except Exception:
            with self._conn() as db:
                db.executemany("""INSERT INTO memory_embeddings
                    (memory_id,model_version,dimension,vector,content_hash,status,updated_at)
                    VALUES(?,?,?,NULL,?,'failed',?)
                    ON CONFLICT(memory_id,model_version) DO UPDATE SET status='failed', updated_at=excluded.updated_at""",
                    [(item["id"], version, int(self.embedding_provider.dimension),
                      self._content_hash(item["content"]), datetime.now(timezone.utc).isoformat())
                     for item in records])
            return 0

    def reindex_embeddings(self, batch_size: int = 64) -> dict:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.embedding_provider is None:
            raise ValueError("no embedding provider is configured")
        version = str(self.embedding_provider.model_version)
        with self._conn() as db:
            hashes = {r["memory_id"]: r["content_hash"] for r in db.execute(
                "SELECT memory_id,content_hash FROM memory_embeddings WHERE model_version=? AND status='ready'",
                (version,)).fetchall()}
            rows = db.execute("SELECT * FROM memory ORDER BY id").fetchall()
        pending = [self._decode(row) for row in rows
                   if hashes.get(row["id"]) != self._content_hash(row["content"])]
        completed = 0
        for start in range(0, len(pending), batch_size):
            completed += self._embed_records(pending[start:start + batch_size], refresh_index=False)
        self._rebuild_faiss_index()
        return {"model_version": version, "pending": len(pending), "indexed": completed,
                "failed": len(pending) - completed}

    def _rebuild_faiss_index(self) -> None:
        if (self.embedding_provider is None or
                os.environ.get("CHIT_MEMORY_ANN", "auto").lower() == "off"):
            self._faiss_index = None
            return
        with self._ann_lock:
            try:
                import numpy as np
                from .faiss_index import FaissMemoryIndex
                index = FaissMemoryIndex(self.path.with_suffix(self.path.suffix + ".faiss"),
                                         int(self.embedding_provider.dimension),
                                         str(self.embedding_provider.model_version))
                with self._conn() as db:
                    rows = db.execute("""SELECT e.memory_id,e.dimension,e.vector,e.content_hash,m.content
                        FROM memory_embeddings e JOIN memory m ON m.id=e.memory_id
                        WHERE e.model_version=? AND e.status='ready' ORDER BY e.memory_id""",
                                      (str(self.embedding_provider.model_version),)).fetchall()
                ids, vectors = [], []
                for row in rows:
                    if (row["dimension"] != self.embedding_provider.dimension or not row["vector"] or
                            row["content_hash"] != self._content_hash(row["content"])):
                        continue
                    vec = np.frombuffer(row["vector"], dtype=np.float32)
                    if vec.size == self.embedding_provider.dimension and np.isfinite(vec).all():
                        ids.append(row["memory_id"])
                        vectors.append(vec)
                index.rebuild(ids, vectors)
                self._faiss_index = index
            except ImportError:
                self._faiss_index = None
            except Exception:
                self._faiss_index = None

    def all(self) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT * FROM memory ORDER BY created_at").fetchall()
        return [self._decode(row) for row in rows]

    def get(self, memory_id: str) -> dict | None:
        with self._conn() as db:
            row = db.execute("SELECT * FROM memory WHERE id=?", (memory_id,)).fetchone()
        return self._decode(row) if row else None

    def delete(self, memory_id: str) -> bool:
        with self._conn() as db:
            deleted = db.execute("DELETE FROM memory WHERE id=?", (memory_id,)).rowcount > 0
        if deleted:
            self._rebuild_faiss_index()
        return deleted

    def _fts_search(self, terms: set[str], limit: int, want: set[str]) -> list[dict]:
        if not self._fts_available or not terms:
            return []
        query = " OR ".join('"' + term.replace('"', '""') + '"' for term in sorted(terms))
        try:
            with self._conn() as db:
                rows = db.execute("""SELECT m.* FROM memory_fts f JOIN memory m ON m.id=f.id
                    WHERE memory_fts MATCH ? ORDER BY bm25(memory_fts) LIMIT ?""",
                                  (query, max(limit * 20, 100))).fetchall()
            items = [self._decode(r) for r in rows]
            return [m for m in items if not want or want.issubset(m["tags"])]
        except sqlite3.OperationalError:
            return []

    def search(self, q: str, limit: int = 5, tags: list[str] | None = None) -> list[dict]:
        terms = _terms(q)
        if not q.strip() or limit <= 0 or (not terms and self.embedding_provider is None):
            return []
        want = set(tags or [])
        want = set(tags or [])
        lexical_items = self._fts_search(terms, limit, want)
        items_by_id = {m["id"]: m for m in lexical_items}
        scored = []
        vectors = {}
        query_vector = None
        if self.embedding_provider is not None:
            try:
                import numpy as np
                encoded = np.asarray(self.embedding_provider.encode([q]), dtype=np.float32).reshape(-1)
                norm = float(np.linalg.norm(encoded))
                if encoded.size == self.embedding_provider.dimension and norm > 0 and np.isfinite(encoded).all():
                    query_vector = encoded / norm
                    if self._faiss_index is not None:
                        vectors = self._faiss_index.search(query_vector, max(limit * 20, 100))
                        if vectors:
                            with self._conn() as db:
                                placeholders = ",".join("?" for _ in vectors)
                                rows = db.execute(f"SELECT * FROM memory WHERE id IN ({placeholders})",
                                                  tuple(vectors)).fetchall()
                            items_by_id.update({r["id"]: self._decode(r) for r in rows})
                    else:
                        items = self.all()
                        with self._conn() as db:
                            records = db.execute("""SELECT memory_id,dimension,vector,content_hash FROM memory_embeddings
                                WHERE model_version=? AND status='ready'""",
                                                 (self.embedding_provider.model_version,)).fetchall()
                        by_id = {m["id"]: m for m in items}
                        valid_ids, valid_vectors = [], []
                        for row in records:
                            item = by_id.get(row["memory_id"])
                            if (item and row["dimension"] == self.embedding_provider.dimension and row["vector"]
                                    and row["content_hash"] == self._content_hash(item["content"])):
                                vec = np.frombuffer(row["vector"], dtype=np.float32)
                                if vec.size == query_vector.size and np.isfinite(vec).all():
                                    valid_ids.append(row["memory_id"])
                                    valid_vectors.append(vec)
                        if valid_vectors:
                            similarities = np.stack(valid_vectors) @ query_vector
                            vectors = {memory_id: float(similarity)
                                       for memory_id, similarity in zip(valid_ids, similarities)}
            except Exception:
                query_vector = None
                vectors = {}
        if not self._fts_available or (self.embedding_provider is not None and self._faiss_index is None):
            items_by_id.update({m["id"]: m for m in self.all()})
        for m in items_by_id.values():
            if want and not want.issubset(m["tags"]):
                continue
            lexical = len(terms & (_terms(m["content"]) | {t.lower() for t in m["tags"]}))
            similarity = vectors.get(m["id"])
            if similarity is not None and self.semantic_threshold is not None and similarity < self.semantic_threshold:
                continue
            if lexical or similarity is not None:
                if similarity is None:
                    relevance = ((1.0 - self.semantic_weight) * lexical / max(1, len(terms))
                                 if vectors else float(lexical))
                else:
                    max_lexical = max(1, len(terms))
                    relevance = self.semantic_weight * ((similarity + 1.0) / 2.0)
                    relevance += (1.0 - self.semantic_weight) * (lexical / max_lexical)
                scored.append(((relevance, lexical, m["importance"], m["created_at"]), m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]


class MemoryStore:
    def __init__(self, path: str | Path = "data/memory.json", seed_path: str | Path | None = "data/memory_seed.json"):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            seed = Path(seed_path) if seed_path else None
            self._save(json.loads(seed.read_text(encoding="utf-8")) if seed and seed.exists() else [])

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, items: list[dict]) -> None:
        tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
        tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    def _make_item(content: str, memory_type: str = "experience", importance: float = 0.5,
                   tags: list[str] | None = None, source: str | None = None) -> dict:
        content = content.strip()
        if not content:
            raise ValueError("memory content must not be empty")
        if not 0.0 <= float(importance) <= 1.0:
            raise ValueError("memory importance must be in [0, 1]")
        item = {"id": str(uuid.uuid4()), "type": memory_type, "content": content,
                "importance": float(importance), "tags": sorted(set(tags or [])),
                "created_at": datetime.now(timezone.utc).isoformat()}
        if source:
            item["source"] = source
        return item

    def add(self, content: str, memory_type: str = "experience", importance: float = 0.5,
            tags: list[str] | None = None, source: str | None = None) -> dict:
        item = self._make_item(content, memory_type, importance, tags, source)
        with self._lock:
            items = self._load()
            items.append(item)
            self._save(items)
        return item

    def all(self) -> list[dict]:
        with self._lock:
            return self._load()

    def get(self, memory_id: str) -> dict | None:
        return next((m for m in self.all() if m.get("id") == memory_id), None)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            items = self._load()
            kept = [m for m in items if m.get("id") != memory_id]
            if len(kept) == len(items):
                return False
            self._save(kept)
            return True

    def search(self, q: str, limit: int = 5, tags: list[str] | None = None) -> list[dict]:
        """Keyword search: rank by shared terms (stopwords ignored), then importance, then recency."""
        terms = _terms(q)
        if not terms:
            return []
        want = set(tags or [])
        scored = []
        for m in self.all():
            if want and not want.issubset(m.get("tags", [])):
                continue
            score = len(terms & (_terms(m.get("content", "")) | {t.lower() for t in m.get("tags", [])}))
            if score:
                scored.append(((score, m.get("importance", 0.0), m.get("created_at", "")), m))
        scored.sort(key=lambda z: z[0], reverse=True)
        return [m for _, m in scored[:limit]]
