"""Datasets and batching for next-token prediction."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import torch
from torch.utils.data import Dataset

logger = logging.getLogger(__name__)


def _stream_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(64 * 1024):
            h.update(chunk)
    return h.hexdigest()


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


def _find_subseq(row: list[int], pattern: list[int], start: int = 0, end: int | None = None) -> int:
    if not pattern:
        return -1
    plen = len(pattern)
    limit = (len(row) if end is None else min(end, len(row))) - plen
    if start > limit:
        return -1
    first = pattern[0]
    if plen == 1:
        try:
            return row.index(first, start, limit + 1)
        except ValueError:
            return -1
    pos = start
    while pos <= limit:
        try:
            idx = row.index(first, pos, limit + 1)
        except ValueError:
            return -1
        if row[idx : idx + plen] == pattern:
            return idx
        pos = idx + 1
    return -1


def _build_bpe_markers(tokenizer) -> dict[str, list[int]] | None:
    try:
        task_prefix = tokenizer.encode("Task:")
        nl_task = tokenizer.encode("\nTask:")
        nl_chit = tokenizer.encode("\nChit:")
        nl_reas = tokenizer.encode("\nReasoning:")
        nl_user = tokenizer.encode("\nUser:")
        prose = tokenizer.encode("Task: prose\n")
        nl_prose = tokenizer.encode("\nTask: prose\n")
        nl_only = tokenizer.encode("\n")
    except Exception:
        return None
    if not (task_prefix and nl_task and nl_chit and nl_reas and prose and nl_prose and nl_only):
        return None
    return {
        "task_prefix": list(task_prefix),
        "nl_task": list(nl_task),
        "nl_chit": list(nl_chit),
        "nl_reas": list(nl_reas),
        "nl_user": list(nl_user),
        "prose": list(prose),
        "nl_prose": list(nl_prose),
        "nl_only": list(nl_only),
    }


def _find_bpe_record_starts(token_data: torch.Tensor, markers: dict[str, list[int]] | None) -> torch.Tensor:
    if not markers:
        return torch.empty(0, dtype=torch.long)
    task_prefix = markers["task_prefix"]
    nl_task = markers["nl_task"]
    nl_only = markers["nl_only"]
    plen = len(nl_task)
    n_tokens = len(token_data)
    if n_tokens < plen:
        return torch.empty(0, dtype=torch.long)

    nl_offset = len(nl_only) if nl_task[: len(nl_only)] == nl_only else 0
    parts: list[torch.Tensor] = []
    if n_tokens >= len(task_prefix) and token_data[: len(task_prefix)].tolist() == task_prefix:
        parts.append(torch.zeros(1, dtype=torch.long))

    chunk_step = 1_000_000
    for start in range(0, n_tokens - plen + 1, chunk_step):
        end = min(n_tokens, start + chunk_step + plen - 1)
        sub = token_data[start:end]
        sub_len = len(sub) - plen + 1
        if sub_len <= 0:
            break
        mask = sub[:sub_len] == nl_task[0]
        for k in range(1, plen):
            mask &= sub[k : sub_len + k] == nl_task[k]
        hits = torch.nonzero(mask, as_tuple=False).flatten()
        if hits.numel() > 0:
            parts.append(hits + (start + nl_offset))

    if not parts:
        return torch.empty(0, dtype=torch.long)
    return torch.cat(parts, dim=0)


def _collect_followup_user_spans(
    row_tokens: list[int],
    search_start: int,
    seg_end: int,
    nl_user: list[int],
    nl_chit: list[int],
    nl_reas: list[int],
    width: int,
    spans: list[tuple[int, int]],
) -> None:
    if not nl_user:
        return
    cursor = search_start
    while cursor < seg_end:
        u_idx = _find_subseq(row_tokens, nl_user, cursor, seg_end)
        if u_idx == -1:
            break
        # Leave "\nUser:" unmasked as a valid turn-end stop sequence, mask prompt body after it
        m_start = u_idx + len(nl_user) - 1
        after_u = u_idx + len(nl_user)
        c_idx = _find_subseq(row_tokens, nl_chit, after_u, seg_end)
        r_idx = _find_subseq(row_tokens, nl_reas, after_u, seg_end)
        if c_idx != -1 and (r_idx == -1 or c_idx < r_idx):
            m_end = c_idx + len(nl_chit) - 1
            spans.append((m_start, m_end))
            cursor = c_idx + len(nl_chit)
        elif r_idx != -1:
            m_end = r_idx + len(nl_reas) - 1
            spans.append((m_start, m_end))
            cursor = r_idx + len(nl_reas)
        else:
            spans.append((m_start, min(width, seg_end - 1)))
            break


def _apply_bpe_answer_loss_mask(
    chunk: torch.Tensor,
    y: torch.Tensor,
    markers: dict[str, list[int]] | None,
) -> None:
    if not markers:
        return
    width = y.size(1)
    min_remaining = 16 if width >= 128 else 1
    nl_task = markers["nl_task"]
    nl_chit = markers["nl_chit"]
    nl_reas = markers["nl_reas"]
    nl_user = markers["nl_user"]
    prose = markers["prose"]
    nl_prose = markers["nl_prose"]

    chunk_cpu = chunk.tolist()
    for r, row_tokens in enumerate(chunk_cpu):
        rec_positions: list[int] = []
        pos = 0
        while True:
            idx = _find_subseq(row_tokens, nl_task, pos)
            if idx == -1:
                break
            rec_positions.append(idx)
            pos = idx + len(nl_task)

        spans: list[tuple[int, int]] = []
        first_end = rec_positions[0] if rec_positions else len(row_tokens)

        # 1. Initial segment before the first "\nTask:" boundary
        if first_end >= len(prose) and row_tokens[: len(prose)] == prose:
            spans.append((0, len(prose) - 1))
        else:
            chit_idx = _find_subseq(row_tokens, nl_chit, 0, first_end)
            reas_idx = _find_subseq(row_tokens, nl_reas, 0, first_end)
            if chit_idx != -1 and (reas_idx == -1 or chit_idx < reas_idx):
                spans.append((0, chit_idx + len(nl_chit) - 1))
                _collect_followup_user_spans(
                    row_tokens, chit_idx + len(nl_chit), first_end,
                    nl_user, nl_chit, nl_reas, width, spans,
                )
            elif reas_idx != -1:
                spans.append((0, reas_idx + len(nl_reas) - 1))
                _collect_followup_user_spans(
                    row_tokens, reas_idx + len(nl_reas), first_end,
                    nl_user, nl_chit, nl_reas, width, spans,
                )

        # 2. Subsequent records starting at each "\nTask:" boundary in the window
        for k, rec_idx in enumerate(rec_positions):
            seg_end = rec_positions[k + 1] if k + 1 < len(rec_positions) else len(row_tokens)
            # Keep "\nTask:" unmasked as the end-of-turn stop sequence for the prior answer;
            # mask the new record's prompt body immediately after "\nTask:".
            mask_start = rec_idx + len(nl_task) - 1
            if seg_end - rec_idx >= len(nl_prose) and row_tokens[rec_idx : rec_idx + len(nl_prose)] == nl_prose:
                spans.append((mask_start, rec_idx + len(nl_prose) - 1))
            else:
                search_from = rec_idx + len(nl_task)
                chit_idx = _find_subseq(row_tokens, nl_chit, search_from, seg_end)
                reas_idx = _find_subseq(row_tokens, nl_reas, search_from, seg_end)
                if chit_idx != -1 and (reas_idx == -1 or chit_idx < reas_idx):
                    spans.append((mask_start, chit_idx + len(nl_chit) - 1))
                    _collect_followup_user_spans(
                        row_tokens, chit_idx + len(nl_chit), seg_end,
                        nl_user, nl_chit, nl_reas, width, spans,
                    )
                elif reas_idx != -1:
                    spans.append((mask_start, reas_idx + len(nl_reas) - 1))
                    _collect_followup_user_spans(
                        row_tokens, reas_idx + len(nl_reas), seg_end,
                        nl_user, nl_chit, nl_reas, width, spans,
                    )
                else:
                    spans.append((mask_start, min(width, seg_end - 1)))

        if not spans:
            continue

        row_mask = torch.zeros(width, dtype=torch.bool)
        for s, e in spans:
            s_clamped = max(0, min(s, width))
            e_clamped = max(0, min(e, width))
            if e_clamped > s_clamped:
                row_mask[s_clamped:e_clamped] = True

        masked_count = int(row_mask.sum().item())
        if masked_count == 0:
            continue
        if width - masked_count >= min_remaining:
            y[r, row_mask] = -100
        elif width > min_remaining:
            # Cap masking so at least min_remaining target tokens remain active
            allowed = width - min_remaining
            true_indices = torch.nonzero(row_mask, as_tuple=False).flatten()[:allowed]
            if true_indices.numel() > 0:
                y[r, true_indices] = -100


def _apply_answer_loss_mask(
    chunk: torch.Tensor,
    y: torch.Tensor,
    is_byte: bool,
    bpe_markers: dict[str, list[int]] | None = None,
) -> None:
    """Mask prompt tokens with -100 so cross-entropy loss focuses on answer/reasoning tokens."""
    if not is_byte:
        _apply_bpe_answer_loss_mask(chunk, y, bpe_markers)
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

    def __init__(self, source: str | Path | None, tokenizer, block_size: int, *, text: str | None = None, allow_fallback: bool = False):
        if (source is None) == (text is None):
            raise ValueError("pass exactly one of a file path or text=")
        self.is_byte = getattr(tokenizer, "name", "") == "byte-utf8"
        self.bpe_markers = None if self.is_byte else _build_bpe_markers(tokenizer)
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
        elif not self.is_byte and text is None:
            src_path = Path(source)
            bin_path = src_path.with_name(f"{src_path.name}.bpe.bin")
            manifest_path = src_path.with_name(f"{src_path.name}.bpe.manifest.json")
            if bin_path.is_file() and manifest_path.is_file():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as mf:
                        m_data = json.load(mf)
                except Exception as exc:
                    raise ValueError(f"Corrupt manifest JSON for '{src_path}': {exc}") from exc

                if not isinstance(m_data, dict):
                    raise ValueError(f"Invalid manifest structure for '{src_path}': expected JSON object, got {type(m_data).__name__}")

                if m_data.get("version") != 1:
                    raise ValueError(f"Unsupported manifest version '{m_data.get('version')}' for '{src_path}'; expected 1")

                if m_data.get("generator_version") != "1.0":
                    raise ValueError(f"Incompatible artifact generator version '{m_data.get('generator_version')}' for '{src_path}'; expected '1.0'")

                if m_data.get("dtype") != "int32":
                    raise ValueError(f"Unsupported artifact dtype '{m_data.get('dtype')}' for '{src_path}'; expected 'int32'")

                expected_tok_name = getattr(tokenizer, "name", "")
                if m_data.get("tokenizer_name") != expected_tok_name:
                    raise ValueError(
                        f"Tokenizer name mismatch for '{src_path}': manifest has '{m_data.get('tokenizer_name')}', "
                        f"but active tokenizer is '{expected_tok_name}'"
                    )

                if m_data.get("artifact_file") != bin_path.name:
                    raise ValueError(
                        f"Artifact file name mismatch for '{src_path}': manifest points to '{m_data.get('artifact_file')}', "
                        f"expected '{bin_path.name}'"
                    )

                token_count = m_data.get("token_count")
                if not isinstance(token_count, int) or token_count <= 0:
                    raise ValueError(f"Invalid token_count in manifest for '{src_path}': expected positive integer, got {token_count!r}")

                if token_count <= block_size:
                    raise ValueError(f"Dataset '{src_path}' has {token_count} tokens; it must be larger than block_size ({block_size})")

                for h_field in ("source_sha256", "tokenizer_sha256", "artifact_sha256"):
                    val = m_data.get(h_field)
                    if not isinstance(val, str) or len(val) != 64 or not all(c in "0123456789abcdefABCDEF" for c in val):
                        raise ValueError(f"Manifest for '{src_path}' has invalid {h_field}: {val!r} (expected 64-char hex string)")

                expected_tok_sha256 = getattr(tokenizer, "asset_sha256", None)
                if not isinstance(expected_tok_sha256, str) or len(expected_tok_sha256) != 64:
                    raise ValueError(f"Active subword tokenizer '{tokenizer}' does not expose a valid 64-char asset_sha256")

                if m_data["tokenizer_sha256"] != expected_tok_sha256:
                    raise ValueError(
                        f"Tokenizer hash mismatch for '{src_path}': manifest has {m_data['tokenizer_sha256'][:12]}, "
                        f"but active tokenizer reports {expected_tok_sha256[:12]}"
                    )

                src_sha256 = _stream_sha256(src_path)
                if m_data["source_sha256"] != src_sha256:
                    raise ValueError(
                        f"Source file hash mismatch for '{src_path}': text modified since artifact generation "
                        f"(manifest={m_data['source_sha256'][:12]}, actual={src_sha256[:12]})"
                    )

                expected_bin_size = token_count * 4
                actual_bin_size = bin_path.stat().st_size
                if actual_bin_size != expected_bin_size:
                    raise ValueError(
                        f"Binary artifact size mismatch for '{src_path}': expected {expected_bin_size} bytes ({token_count} int32 tokens), "
                        f"got {actual_bin_size} bytes"
                    )

                bin_sha256 = _stream_sha256(bin_path)
                if m_data["artifact_sha256"] != bin_sha256:
                    raise ValueError(
                        f"Binary artifact checksum corruption detected for '{src_path}': expected {m_data['artifact_sha256'][:12]}, "
                        f"got {bin_sha256[:12]}"
                    )

                logger.info("Memory-mapping verified pre-tokenized BPE artifact: %s (%d tokens)", bin_path.name, token_count)
                token_data = torch.from_file(str(bin_path), shared=False, size=token_count, dtype=torch.int32)
                self.record_starts = _find_bpe_record_starts(token_data, self.bpe_markers)
            else:
                allow = allow_fallback or os.environ.get("CHIT_ALLOW_IN_MEMORY_TOKENIZATION") == "1"
                if not allow:
                    raise FileNotFoundError(
                        f"Missing pre-tokenized subword artifact for '{src_path}' (expected '{bin_path.name}' and '{manifest_path.name}'). "
                        f"Run 'python -m pranav.chit.pretokenize' to generate artifacts and prevent server OOM."
                    )
                logger.warning("No pre-tokenized artifact for '%s'; falling back to in-memory tokenization", src_path)
                text = src_path.read_text(encoding="utf-8")
                try:
                    ids = tokenizer.encode(text)
                except Exception as exc:
                    logger.error("Failed to tokenize dataset from %s: %s", src_path, exc, exc_info=True)
                    raise RuntimeError(f"Failed to tokenize dataset from {src_path}: {exc}") from exc
                token_data = torch.tensor(ids, dtype=torch.int32)
                self.record_starts = _find_bpe_record_starts(token_data, self.bpe_markers)
                del ids
                del text
        else:
            try:
                ids = tokenizer.encode(text)
            except Exception as exc:
                logger.error("Failed to tokenize dataset from provided text: %s", exc, exc_info=True)
                raise RuntimeError(f"Failed to tokenize dataset from provided text: {exc}") from exc
            token_data = torch.tensor(ids, dtype=torch.int32)
            self.record_starts = (
                _find_record_starts(text.encode("utf-8"))
                if self.is_byte
                else _find_bpe_record_starts(token_data, self.bpe_markers)
            )
            del ids
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
    _apply_answer_loss_mask(chunk, y, getattr(ds, "is_byte", False), getattr(ds, "bpe_markers", None))
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
        _apply_answer_loss_mask(
            chunk, row_y, getattr(dataset, "is_byte", False), getattr(dataset, "bpe_markers", None)
        )
        x[rows.to(device)] = row_x
        y[rows.to(device)] = row_y
    return x, y
