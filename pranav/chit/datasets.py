"""Helpers for preparing and checking the training text (``train.txt`` / ``eval.txt``).

The files usually arrive from outside the API, for example a mounted folder in a
container, so the API checks what is actually there instead of assuming.
Used by ``GET /data``, ``POST /data/split`` and ``python -m pranav.chit.tools.split``.
"""
from __future__ import annotations

import errno
import hashlib
import os
import random
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MIN_USEFUL_EVAL_BYTES = 1024   # smaller than this gives a noisy eval loss
OVERLAP_WARN_FRACTION = 0.2    # warn when this share of distinct eval lines also appear in train
SOURCE_SUFFIXES = (".txt", ".md")


# --------------------------------------------------------------------------- splitting


@dataclass
class SplitResult:
    train: list[str]
    eval: list[str]
    duplicates_removed: int


def split_corpus(text: str, by: str = "line", eval_fraction: float = 0.1, seed: int = 42) -> SplitResult:
    """Drop blanks and duplicates, shuffle, and hold out ``eval_fraction`` of the items.

    The two sides never share an item. ``by="paragraph"`` treats blocks separated by
    blank lines as one item, so a ``User:`` / ``Chit:`` pair stays together.
    """
    if by == "paragraph":
        items = [b.strip() for b in re.split(r"\n\s*\n", text)]
    elif by == "line":
        items = [ln.strip() for ln in text.splitlines()]
    else:
        raise ValueError("by must be 'line' or 'paragraph'")
    seen: set[str] = set()
    unique: list[str] = []
    duplicates = 0
    for item in items:
        if not item:
            continue
        key = " ".join(item.lower().split())
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(item)
    if len(unique) < 2:
        raise ValueError("need at least 2 distinct items to make both a train and an eval file")
    random.Random(seed).shuffle(unique)
    n_eval = min(len(unique) - 1, max(1, round(len(unique) * eval_fraction)))
    return SplitResult(train=unique[n_eval:], eval=unique[:n_eval], duplicates_removed=duplicates)


def join_items(items: list[str], by: str = "line") -> str:
    return ("\n\n" if by == "paragraph" else "\n").join(items) + "\n"


# --------------------------------------------------------------------------- inspecting


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def file_info(path: str | Path) -> dict | None:
    """Size, line count, SHA-256 and modification time, or ``None`` if the file is missing."""
    p = Path(path)
    if not p.is_file():
        return None
    digest, lines, last = hashlib.sha256(), 0, b""
    with p.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
            lines += chunk.count(b"\n")
            last = chunk
    if last and not last.endswith(b"\n"):
        lines += 1
    st = p.stat()
    return {"path": str(p), "bytes": st.st_size, "lines": lines,
            "sha256": digest.hexdigest(), "modified_at": _iso(st.st_mtime)}


def _norm_lines(path: Path) -> list[str]:
    out = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for ln in f:
            key = " ".join(ln.lower().split())
            if key:
                out.append(key)
    return out


def analyze(train_path: str | Path, eval_path: str | Path, block_size: int, max_bytes: int) -> dict:
    """Check the two files against each other and against the model's context size."""
    train, held = file_info(train_path), file_info(eval_path)
    warnings: list[str] = []
    checks: dict = {}
    for name, info, path in (("train", train, train_path), ("eval", held, eval_path)):
        if info is None:
            warnings.append(f"{name} file not found: {path}")
            checks[f"{name}_larger_than_block_size"] = False
        else:
            ok = info["bytes"] > block_size
            checks[f"{name}_larger_than_block_size"] = ok
            if not ok:
                warnings.append(f"{name} file is {info['bytes']} bytes; it must be larger than "
                                f"model.block_size ({block_size})")
    if train and held:
        if held["bytes"] < MIN_USEFUL_EVAL_BYTES:
            warnings.append(f"eval file is under {MIN_USEFUL_EVAL_BYTES} bytes, so the eval loss will be noisy")
        if train["bytes"] and held["bytes"] < 0.02 * train["bytes"]:
            warnings.append("eval file is under 2% of the train file; the eval loss may not be representative")
        if train["bytes"] <= max_bytes and held["bytes"] <= max_bytes:
            t_lines = _norm_lines(Path(train_path))
            e_distinct = set(_norm_lines(Path(eval_path)))
            shared = len(e_distinct & set(t_lines))
            checks["eval_distinct_lines"] = len(e_distinct)
            checks["eval_lines_also_in_train"] = shared
            checks["train_repeated_lines"] = len(t_lines) - len(set(t_lines))
            if e_distinct and shared / len(e_distinct) >= OVERLAP_WARN_FRACTION:
                warnings.append(f"{shared} of {len(e_distinct)} distinct eval lines also appear in train; "
                                "the eval loss will look better than the model really is "
                                "(repeated answers such as 'Chit: I do not know.' are fine)")
        else:
            warnings.append("files are too large for the overlap check; it was skipped")
    return {"train": train, "eval": held, "checks": checks, "warnings": warnings,
            "ready_to_train": bool(checks["train_larger_than_block_size"] and checks["eval_larger_than_block_size"])}


def list_sources(data_dir: str | Path, limit: int = 100) -> list[dict]:
    """Text files in the data folder that POST /data/split can read."""
    d = Path(data_dir)
    if not d.is_dir():
        return []
    files = sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES)
    return [{"name": p.name, "bytes": p.stat().st_size} for p in files[:limit]]


# --------------------------------------------------------------------------- writing


def backup(path: str | Path) -> str | None:
    """Copy ``path`` to ``path.bak`` (replacing an older backup); return the backup's path."""
    p = Path(path)
    if not p.is_file():
        return None
    bak = p.with_name(p.name + ".bak")
    shutil.copyfile(p, bak)
    return str(bak)


def write_text(path: str | Path, text: str) -> None:
    """Write atomically (temp file + rename) so readers never see half a file.

    A single file mounted into a container cannot be renamed over; in that case, or
    when the folder is on another device, fall back to writing in place.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        try:
            os.replace(tmp, p)
        except OSError as e:
            if e.errno not in (errno.EBUSY, errno.EXDEV, errno.EPERM, errno.EACCES):
                raise
            p.write_text(text, encoding="utf-8", newline="")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
