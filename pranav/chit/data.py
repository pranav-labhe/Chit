"""Datasets and batching for next-token prediction."""
from __future__ import annotations

from pathlib import Path

import torch
from torch.utils.data import Dataset


class TextDataset(Dataset):
    """All windows of ``block_size + 1`` tokens over one text, for next-token prediction."""

    def __init__(self, source: str | Path | None, tokenizer, block_size: int, *, text: str | None = None):
        if (source is None) == (text is None):
            raise ValueError("pass exactly one of a file path or text=")
        if text is None:
            text = Path(source).read_text(encoding="utf-8")
        ids = tokenizer.encode(text)
        if len(ids) <= block_size:
            raise ValueError(f"dataset has {len(ids)} tokens; it must be larger than block_size ({block_size})")
        self.data = torch.tensor(ids, dtype=torch.long)
        self.block_size = block_size

    @classmethod
    def from_text(cls, text: str, tokenizer, block_size: int) -> "TextDataset":
        return cls(None, tokenizer, block_size, text=text)

    def __len__(self) -> int:
        return len(self.data) - self.block_size

    def __getitem__(self, i: int):
        chunk = self.data[i:i + self.block_size + 1]
        return chunk[:-1], chunk[1:]


def random_batch(ds: TextDataset, batch_size: int, device, generator: torch.Generator | None = None):
    """Sample ``batch_size`` random windows as ``(x, y)`` tensors on ``device``."""
    starts = torch.randint(0, len(ds), (batch_size, 1), generator=generator)
    idx = starts + torch.arange(ds.block_size + 1)  # (batch, block+1), gathered in one op
    chunk = ds.data[idx]
    return chunk[:, :-1].to(device, non_blocking=True), chunk[:, 1:].to(device, non_blocking=True)
