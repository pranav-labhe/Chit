"""Small external-material extraction and chunking utility.

This module does not create a new teaching path. It only turns external text
into the same ``text`` knowledge items accepted by POST /knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ExtractedPage:
    source: str
    text: str


def extract_file(path: str | Path) -> list[ExtractedPage]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("PDF input requires the 'pypdf' package") from e
        reader = PdfReader(str(path))
        return [
            ExtractedPage(f"{path}#page={n}", page.extract_text() or "")
            for n, page in enumerate(reader.pages, 1)
        ]

    text = path.read_text(encoding="utf-8")
    return [ExtractedPage(str(path), text)]


def chunk_text(text: str, chunk_chars: int = 4000, overlap: int = 400) -> list[str]:
    """Split text into deterministic, whitespace-aware overlapping chunks."""
    if chunk_chars < 256:
        raise ValueError("chunk_chars must be >= 256")
    if overlap < 0 or overlap >= chunk_chars:
        raise ValueError("overlap must be >= 0 and smaller than chunk_chars")

    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        if end < len(text):
            floor = start + max(1, int(chunk_chars * 0.55))
            cut = text.rfind("\n", floor, end)
            if cut <= start:
                cut = text.rfind(" ", floor, end)
            if cut > start:
                end = cut

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def knowledge_items(
    path: str | Path,
    *,
    chunk_chars: int = 4000,
    overlap: int = 400,
    tags: list[str] | None = None,
) -> list[dict]:
    """Return items ready for the existing Teach API's ``POST /knowledge``."""
    tags = sorted({t.strip() for t in tags or [] if t and t.strip()})
    items: list[dict] = []
    for page in extract_file(path):
        chunks = chunk_text(page.text, chunk_chars, overlap)
        for n, chunk in enumerate(chunks, 1):
            source = f"{page.source}#chunk={n}"
            items.append({
                "kind": "text",
                "text": chunk,
                "tags": tags,
                "source": source[:200],
            })
    return items
