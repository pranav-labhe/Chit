"""Optional rebuildable FAISS HNSW index for SQLite-owned memory vectors."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import tempfile


class FaissMemoryIndex:
    def __init__(self, path: str | Path, dimension: int, version: str):
        import faiss
        self.faiss, self.path = faiss, Path(path)
        self.meta_path = self.path.with_suffix(self.path.suffix + ".json")
        self.dimension, self.version = int(dimension), str(version)
        self.index = None
        self.ids: list[str] = []
        self.fingerprint: str | None = None
        self._load()

    def _load(self):
        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            index = self.faiss.read_index(str(self.path))
            if (meta.get("version") == self.version and meta.get("dimension") == self.dimension and
                    index.d == self.dimension and index.ntotal == len(meta["ids"])):
                self.index, self.ids = index, list(meta["ids"])
                self.fingerprint = meta.get("fingerprint")
        except (OSError, ValueError, KeyError, RuntimeError):
            self.index, self.ids = None, []

    def rebuild(self, ids: list[str], vectors) -> None:
        import numpy as np
        index = self.faiss.IndexHNSWFlat(self.dimension, 32, self.faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = 80
        index.hnsw.efSearch = 64
        matrix = np.asarray(vectors, dtype=np.float32).reshape(-1, self.dimension)
        digest = hashlib.sha256()
        for memory_id in ids:
            digest.update(memory_id.encode("utf-8"))
            digest.update(b"\0")
        digest.update(matrix.tobytes())
        fingerprint = digest.hexdigest()
        if self.index is not None and self.fingerprint == fingerprint:
            return
        if len(ids):
            index.add(matrix)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        os.close(fd)
        tmp = Path(name)
        try:
            self.faiss.write_index(index, str(tmp))
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        meta = {"version": self.version, "dimension": self.dimension, "ids": list(ids),
                "fingerprint": fingerprint}
        meta_tmp = self.meta_path.with_suffix(self.meta_path.suffix + ".tmp")
        meta_tmp.write_text(json.dumps(meta), encoding="utf-8")
        os.replace(meta_tmp, self.meta_path)
        self.index, self.ids = index, list(ids)
        self.fingerprint = fingerprint

    def search(self, vector, k: int) -> dict[str, float]:
        import numpy as np
        if self.index is None or self.index.ntotal == 0:
            return {}
        scores, positions = self.index.search(np.asarray(vector, dtype=np.float32).reshape(1, -1),
                                              min(max(1, k), self.index.ntotal))
        return {self.ids[int(i)]: float(score) for score, i in zip(scores[0], positions[0])
                if 0 <= int(i) < len(self.ids)}
