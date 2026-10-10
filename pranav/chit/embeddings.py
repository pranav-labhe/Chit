"""Optional local embedding providers for semantic memory search."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np


class EmbeddingProvider(Protocol):
    model_version: str
    dimension: int

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


class SentenceTransformerProvider:
    """Load a local Sentence-Transformers model without remote downloads."""

    def __init__(self, model_path: str | Path, *, model_version: str | None = None):
        path = Path(model_path)
        if not path.is_dir():
            raise ValueError(f"embedding model path must be a local directory: {path}")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("local embedding support requires the optional 'embeddings' dependencies") from exc
        self.model = SentenceTransformer(str(path), device="cpu", local_files_only=True,
                                         trust_remote_code=False)
        self.dimension = int(self.model.get_sentence_embedding_dimension())
        if self.dimension <= 0:
            raise ValueError("embedding model has an invalid output dimension")
        self.model_version = model_version or self._fingerprint(path)

    @staticmethod
    def _fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        for file in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(file.relative_to(path).as_posix().encode("utf-8"))
            with file.open("rb") as source:
                while chunk := source.read(1 << 20):
                    digest.update(chunk)
        return f"{path.name}:{digest.hexdigest()[:16]}"

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self.model.encode(list(texts), convert_to_numpy=True, normalize_embeddings=True,
                                    show_progress_bar=False)
        result = np.asarray(vectors, dtype=np.float32)
        if result.ndim == 1:
            result = result.reshape(1, -1)
        if result.shape != (len(texts), self.dimension) or not np.isfinite(result).all():
            raise ValueError("embedding provider returned invalid vectors")
        return result
