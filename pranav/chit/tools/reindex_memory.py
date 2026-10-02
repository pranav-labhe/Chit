"""Build or refresh SQLite memory vectors using a local embedding model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..embeddings import SentenceTransformerProvider
from ..memory import SQLiteMemoryStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("model", type=Path, help="local Sentence-Transformers model directory")
    parser.add_argument("--version", help="explicit immutable model/version ID")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args(argv)
    provider = SentenceTransformerProvider(args.model, model_version=args.version)
    store = SQLiteMemoryStore(args.database, seed_path=None, embedding_provider=provider)
    print(json.dumps(store.reindex_embeddings(args.batch_size), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
