"""External memory: facts Chit can recall at inference time without retraining.

Stored as a JSON list. Writes are atomic (temp file + rename) and serialised by
a lock, so concurrent API requests cannot corrupt the file or lose updates.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_WORD = re.compile(r"\w+", re.UNICODE)
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from has have how i in is it of on or "
    "should the to was what when where which who why will with you".split())


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS}


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

    def add(self, content: str, memory_type: str = "experience", importance: float = 0.5,
            tags: list[str] | None = None, source: str | None = None) -> dict:
        content = content.strip()
        if not content:
            raise ValueError("memory content must not be empty")
        if not 0.0 <= float(importance) <= 1.0:
            raise ValueError("importance must be in [0, 1]")
        item = {
            "id": str(uuid.uuid4()),
            "type": memory_type,
            "content": content,
            "importance": float(importance),
            "tags": sorted(set(tags or [])),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if source:
            item["source"] = source
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
