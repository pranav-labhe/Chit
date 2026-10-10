"""Measure actual SQLite hybrid-search latency over a synthetic corpus."""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np

from ..memory import SQLiteMemoryStore


class _FixedQueryProvider:
    model_version = "synthetic-random-v1"

    def __init__(self, dimension: int):
        self.dimension = dimension

    def encode(self, texts):
        result = np.zeros((len(texts), self.dimension), dtype=np.float32)
        result[:, 0] = 1.0
        return result


def _percentiles(samples: list[float]) -> dict:
    p50, p95, p99 = np.percentile(samples, [50, 95, 99])
    return {"p50_ms": float(p50), "p95_ms": float(p95), "p99_ms": float(p99),
            "mean_ms": statistics.fmean(samples)}


def _populate(store: SQLiteMemoryStore, size: int, dimension: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    version = store.embedding_provider.model_version
    now = "2026-01-01T00:00:00+00:00"
    with store._conn() as db:
        for start in range(0, size, 2_000):
            end = min(size, start + 2_000)
            records, embeddings = [], []
            vectors = rng.standard_normal((end - start, dimension), dtype=np.float32)
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
            for offset, vector in enumerate(vectors):
                index = start + offset
                memory_id = f"synthetic-{index:08d}"
                content = f"Synthetic test memory record {index:08d} contains ordinary benchmark text."
                records.append((memory_id, "benchmark", content, 0.5, "[]", now, None))
                embeddings.append((memory_id, version, dimension, vector.tobytes(),
                                   store._content_hash(content), "ready", now))
            db.executemany("INSERT INTO memory VALUES(?,?,?,?,?,?,?)", records)
            db.executemany("""INSERT INTO memory_embeddings
                (memory_id,model_version,dimension,vector,content_hash,status,updated_at)
                VALUES(?,?,?,?,?,?,?)""", embeddings)


def _measure(size: int, dimension: int, repeats: int, seed: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="chit-memory-bench-") as temp:
        path = Path(temp) / "memory.db"
        provider = _FixedQueryProvider(dimension)
        store = SQLiteMemoryStore(path, seed_path=None, embedding_provider=provider)
        _populate(store, size, dimension, seed)
        query = "semantic-query-unique"
        for _ in range(3):
            store.search(query, limit=5)
        samples = []
        for _ in range(repeats):
            start = time.perf_counter()
            results = store.search(query, limit=5)
            samples.append((time.perf_counter() - start) * 1000)
        db_bytes = sum(p.stat().st_size for p in Path(temp).glob("memory.db*"))
        return {"records": size, "dimension": dimension, "repeats": repeats,
                "latency": _percentiles(samples), "result_count": len(results),
                "database_bytes": db_bytes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1_000, 5_000, 10_000, 50_000])
    parser.add_argument("--dimension", type=int, default=384)
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if any(size < 1 for size in args.sizes) or args.dimension < 1 or args.repeats < 3:
        parser.error("sizes/dimension must be positive and repeats must be at least 3")
    print(json.dumps({"benchmark": "SQLiteMemoryStore.search synthetic hybrid exact scan",
                      "python": platform.python_version(), "platform": platform.platform(),
                      "numpy": np.__version__, "seed": args.seed,
                      "query_embedding": "fixed unit vector; memory vectors seeded random unit vectors",
                      "results": [_measure(n, args.dimension, args.repeats, args.seed)
                                  for n in args.sizes]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
