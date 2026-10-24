"""Datasets and batching for next-token prediction."""
from __future__ import annotations

import logging
from pathlib import Path

import torch
from torch.utils.data import Dataset

logger = logging.getLogger(__name__)


def _find_record_starts(raw_bytes: bytes | bytearray) -> torch.Tensor:
    starts: list[int] = []
    if raw_bytes.startswith(b"Task: "):
        starts.append(0)
    pos = 0
    while True:
        idx = raw_bytes.find(b"\nTask: ", pos)
        if idx == -1:
            break
        starts.append(idx + 1)
        pos = idx + 7
    return torch.tensor(starts, dtype=torch.long)


def _sample_starts(
    ds: "TextDataset",
    count: int,
    width: int,
    generator: torch.Generator | None = None,
) -> torch.Tensor:
    max_start = len(ds.data) - width
    if ds.record_starts.numel() > 0:
        valid_records = ds.record_starts[ds.record_starts < max_start]
        if valid_records.numel() > 0:
            n_aligned = int(round(count * 0.7))
            if count == 1:
                draw = torch.rand((1,), generator=generator).item()
                n_aligned = 1 if draw < 0.7 else 0
            n_rand = count - n_aligned
            parts = []
            if n_aligned > 0:
                rec_idx = torch.randint(0, valid_records.numel(), (n_aligned, 1), generator=generator)
                parts.append(valid_records[rec_idx])
            if n_rand > 0:
                parts.append(torch.randint(0, max_start, (n_rand, 1), generator=generator))
            return torch.cat(parts, dim=0)
    return torch.randint(0, max_start, (count, 1), generator=generator)


def _apply_answer_loss_mask(chunk: torch.Tensor, y: torch.Tensor, is_byte: bool) -> None:
    """Mask prompt tokens with -100 so cross-entropy loss focuses on answer/reasoning bytes."""
    if not is_byte:
        return
    width = y.size(1)
    min_remaining = 16 if width >= 128 else 1
    chunk_cpu = chunk.tolist()
    for r, row_tokens in enumerate(chunk_cpu):
        raw_row = bytes(row_tokens)
        mask_end = 0
        chit_idx = raw_row.find(b"\nChit: ")
        reas_idx = raw_row.find(b"\nReasoning: ")
        if chit_idx != -1 and (reas_idx == -1 or chit_idx < reas_idx):
            mask_end = chit_idx + len(b"\nChit: ") - 1
        elif reas_idx != -1:
            mask_end = reas_idx + len(b"\nReasoning: ") - 1
        elif raw_row.startswith(b"Task: prose\n"):
            mask_end = len(b"Task: prose\n") - 1
        if 0 < mask_end <= width - min_remaining:
            y[r, :mask_end] = -100


class TextDataset(Dataset):
    """All windows of ``block_size + 1`` tokens over one text, for next-token prediction."""

    def __init__(self, source: str | Path | None, tokenizer, block_size: int, *, text: str | None = None):
        if (source is None) == (text is None):
            raise ValueError("pass exactly one of a file path or text=")
        self.is_byte = getattr(tokenizer, "name", "") == "byte-utf8"
        if self.is_byte and text is None:
            # ByteTokenizer's ids are exactly the normalized UTF-8 bytes. Keep
            # them packed as uint8 instead of materializing a Python int per
            # byte and then an int64 tensor (roughly 8x the corpus size). Read
            # incrementally to avoid creating a corpus-sized Python str. The
            # text wrapper retains read_text's universal-newline behavior.
            raw = bytearray()
            with Path(source).open("r", encoding="utf-8", newline=None) as f:
                while chunk := f.read(1 << 20):
                    raw.extend(chunk.encode("utf-8"))
            token_data = torch.frombuffer(raw, dtype=torch.uint8)
            self.record_starts = _find_record_starts(raw)
        else:
            if text is None:
                text = Path(source).read_text(encoding="utf-8")
            try:
                ids = tokenizer.encode(text)
            except Exception as exc:
                src_label = str(source) if source is not None else "provided text"
                logger.error("Failed to tokenize dataset from %s: %s", src_label, exc, exc_info=True)
                raise RuntimeError(f"Failed to tokenize dataset from {src_label}: {exc}") from exc
            if len(ids) <= block_size:
                raise ValueError(f"dataset has {len(ids)} tokens; it must be larger than block_size ({block_size})")
            token_data = torch.tensor(ids, dtype=torch.int32)
            self.record_starts = _find_record_starts(text.encode("utf-8")) if self.is_byte else torch.empty(0, dtype=torch.long)
            del ids
            del text
        if len(token_data) <= block_size:
            raise ValueError(f"dataset has {len(token_data)} tokens; it must be larger than block_size ({block_size})")
        self.data = token_data
        self.block_size = block_size

    @classmethod
    def from_text(cls, text: str, tokenizer, block_size: int) -> "TextDataset":
        return cls(None, tokenizer, block_size, text=text)

    def __len__(self) -> int:
        return len(self.data) - self.block_size

    def __getitem__(self, i: int):
        chunk = self.data[i:i + self.block_size + 1]
        return chunk[:-1], chunk[1:]


def random_batch(ds: TextDataset, batch_size: int, device, generator: torch.Generator | None = None,
                 block_size: int | None = None):
    """Sample ``batch_size`` windows as ``(x, y)`` tensors on ``device``."""
    width = ds.block_size if block_size is None else block_size
    if width < 1 or width > ds.block_size:
        raise ValueError("batch block_size must be between 1 and dataset.block_size")
    starts = _sample_starts(ds, batch_size, width, generator=generator)
    idx = starts + torch.arange(width + 1)  # (batch, block+1), gathered in one op
    chunk = ds.data[idx]
    # Embedding indices must be integer tensors. Convert only the sampled batch;
    # the complete corpus stays packed in one byte per token in host memory.
    x = chunk[:, :-1].to(device=device, dtype=torch.long, non_blocking=True)
    y = chunk[:, 1:].to(device=device, dtype=torch.long, non_blocking=True)
    _apply_answer_loss_mask(chunk, y, getattr(ds, "is_byte", False))
    return x, y


def random_mixed_batch(datasets: list[TextDataset], weights: list[float], batch_size: int, device,
                       generator: torch.Generator | None = None, block_size: int | None = None,
                       source_counts: list[int] | None = None):
    """Sample each row from a weighted corpus source, then draw a window there.

    Source choice is per sequence, rather than per byte in a concatenated file. This
    prevents a large corpus from silently monopolizing training and avoids windows
    that cross unrelated source-file boundaries.
    """
    if not datasets or len(datasets) != len(weights):
        raise ValueError("datasets and weights must be non-empty and have the same length")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    width = datasets[0].block_size if block_size is None else block_size
    if width < 1 or any(width > ds.block_size for ds in datasets):
        raise ValueError("batch block_size must fit every dataset")
    weight_tensor = torch.tensor(weights, dtype=torch.double, device="cpu")
    if not torch.isfinite(weight_tensor).all() or (weight_tensor <= 0).any():
        raise ValueError("weights must be finite and greater than zero")
    choices = torch.multinomial(weight_tensor / weight_tensor.sum(), batch_size,
                                replacement=True, generator=generator)
    if source_counts is not None:
        if len(source_counts) != len(datasets):
            raise ValueError("source_counts must have one counter per dataset")
        for source_id, count in enumerate(torch.bincount(choices, minlength=len(datasets)).tolist()):
            source_counts[source_id] += count
    x = torch.empty((batch_size, width), dtype=torch.long, device=device)
    y = torch.empty_like(x)
    for source_id, dataset in enumerate(datasets):
        rows = torch.nonzero(choices == source_id, as_tuple=False).flatten()
        if not rows.numel():
            continue
        starts = _sample_starts(dataset, rows.numel(), width, generator=generator)
        indices = starts + torch.arange(width + 1)
        chunk = dataset.data[indices]
        row_x = chunk[:, :-1].to(device=device, dtype=torch.long, non_blocking=True)
        row_y = chunk[:, 1:].to(device=device, dtype=torch.long, non_blocking=True)
        _apply_answer_loss_mask(chunk, row_y, getattr(dataset, "is_byte", False))
        x[rows.to(device)] = row_x
        y[rows.to(device)] = row_y
    return x, y
