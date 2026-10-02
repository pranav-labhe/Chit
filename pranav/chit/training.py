"""Training loop for Chit.

Used by both the CLI (``python -m pranav.chit.tools.train``) and the training
API (``pranav.chit.jobs``). The optional callbacks let a caller observe
progress and stop a run cooperatively without touching the loop itself.
"""
from __future__ import annotations

import logging
import math
import os
import random
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from tqdm import tqdm

from . import __version__
from .config import ChitConfig
from .data import TextDataset, random_batch
from .model import ChitModel, load_model_state
from .tokenizer import BpeTokenizer, ByteTokenizer, create_tokenizer

log = logging.getLogger(__name__)

CHECKPOINT_FORMAT = 3  # includes versioned tokenizer asset metadata


class TrainingCancelled(Exception):
    """Raised when ``should_stop`` asks the loop to stop early."""


def device_for(name: str) -> torch.device:
    if name == "cpu":
        return torch.device("cpu")
    if name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    if name in ("cuda", "auto"):
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    raise ValueError(f"unknown device {name!r}")


def set_seed(s: int) -> None:
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


seed = set_seed  # backwards-compatible alias


def lr_at(step: int, c: ChitConfig) -> float:
    """Learning rate for a 1-based optimizer step: linear warmup, then constant or cosine."""
    t = c.training
    if t.warmup_steps and step <= t.warmup_steps:
        return t.learning_rate * step / t.warmup_steps
    if t.lr_schedule == "constant":
        return t.learning_rate
    span = max(1, t.max_steps - t.warmup_steps)
    progress = min(1.0, (step - t.warmup_steps) / span)
    floor = t.learning_rate * t.min_lr_ratio
    if t.lr_schedule == "linear":
        return floor + (t.learning_rate - floor) * (1.0 - progress)
    return floor + (t.learning_rate - floor) * 0.5 * (1 + math.cos(math.pi * progress))


def context_length_at(step: int, c: ChitConfig) -> int:
    """Return this step's sequence length for an optional even-stage curriculum."""
    schedule = c.training.context_curriculum
    if not schedule:
        return c.model.block_size
    stage = min((max(step, 1) - 1) * len(schedule) // c.training.max_steps, len(schedule) - 1)
    return schedule[stage]


@torch.no_grad()
def estimate_loss(model, ds, batch: int, steps: int, dev) -> float:
    was_training = model.training
    model.eval()
    total = 0.0
    for _ in range(steps):
        _, l = model(*random_batch(ds, batch, dev))
        total += l.item()
    model.train(was_training)
    return total / steps


loss = estimate_loss  # backwards-compatible alias


def save_checkpoint(obj, path) -> None:
    """Write a checkpoint atomically, so a reader never sees a half-written file."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        torch.save(obj, tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


ARCHITECTURE_KEYS = ("vocab_size", "block_size", "n_layer", "n_head", "n_embd",
                    "position_encoding", "rope_theta")


def same_architecture(a: dict, b: dict) -> bool:
    """True if weights trained with model config ``a`` load into config ``b`` (dropout may differ)."""
    defaults = {"position_encoding": "absolute", "rope_theta": 10000.0}
    return all(a.get(k, defaults.get(k)) == b.get(k, defaults.get(k)) for k in ARCHITECTURE_KEYS)


def load_checkpoint(path) -> dict:
    """Load a checkpoint safely (tensors and plain data only, never pickled code)."""
    ck = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(ck, dict) or "model" not in ck or "model_config" not in ck:
        raise ValueError(f"{path} is not a Chit checkpoint")
    return ck


def train(
    c: ChitConfig,
    output_dir: str | Path = "checkpoints",
    *,
    init_checkpoint: str | Path | None = None,
    on_step: Callable[[int], None] | None = None,
    on_eval: Callable[[int, float, float], None] | None = None,
    on_checkpoint: Callable[[int, Path], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    keep_step_checkpoints: bool = True,
    progress: bool = True,
    metadata: dict | None = None,
) -> Path:
    """Train a Chit model from config ``c``; return the path of the final checkpoint.

    init_checkpoint                     start from these weights (fine-tuning) instead of
                                        random init; its model_config must equal c.model
    on_step(step)                       called after every optimizer step
    on_eval(step, train_loss, eval_loss) called at every evaluation point
    on_checkpoint(step, path)       called after each checkpoint is atomically saved
    should_stop()                       checked every step; True raises TrainingCancelled
    keep_step_checkpoints               also keep step_NNNNNN.pt files, not only latest.pt
    progress                            show a tqdm bar and print losses (CLI use)
    metadata                            extra JSON-safe data stored in every checkpoint
    """
    set_seed(c.seed)
    dev = device_for(c.device)
    tok = create_tokenizer(c.tokenizer.name, c.tokenizer.model_file)
    if c.model.vocab_size != tok.vocab_size:
        raise ValueError(f"model.vocab_size ({c.model.vocab_size}) must equal tokenizer vocab ({tok.vocab_size})")
    tr = TextDataset(c.data.train_file, tok, c.model.block_size)
    ev = TextDataset(c.data.eval_file, tok, c.model.block_size)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    latest = out / "latest.pt"
    t = c.training
    model_cfg = c.to_dict()["model"]
    tokenizer_asset = tok.asset if isinstance(tok, BpeTokenizer) else None
    tokenizer_sha256 = tok.asset_sha256 if isinstance(tok, BpeTokenizer) else None

    m = ChitModel(**model_cfg)
    init_step = 0
    if init_checkpoint is not None:
        ck = load_checkpoint(init_checkpoint)
        ck_tokenizer = ck.get("tokenizer", ByteTokenizer.name)
        if ck_tokenizer != tok.name:
            raise ValueError(f"init checkpoint tokenizer {ck_tokenizer!r} does not match {tok.name!r}")
        if ck.get("tokenizer_sha256") != tokenizer_sha256:
            raise ValueError("init checkpoint tokenizer assets do not match the configured tokenizer")
        if not same_architecture(ck["model_config"], model_cfg):
            raise ValueError(f"init checkpoint architecture {ck['model_config']} does not match {model_cfg}")
        load_model_state(m, ck["model"])
        init_step = int(ck.get("total_steps", ck.get("step", 0)) or 0)
    m.to(dev).train()
    opt = torch.optim.AdamW(m.parameters(), lr=lr_at(1, c), weight_decay=t.weight_decay)
    if progress:
        print("Device:", dev, "Parameters:", m.num_parameters(),
              "Init:", init_checkpoint or "random")

    best_eval = math.inf
    last_eval: dict | None = None
    steps = range(1, t.max_steps + 1)
    for step in (tqdm(steps, desc="Training Chit") if progress else steps):
        if should_stop and should_stop():
            raise TrainingCancelled(f"cancelled at step {step - 1}")
        for g in opt.param_groups:
            g["lr"] = lr_at(step, c)
        x, y = random_batch(tr, t.batch_size, dev, block_size=context_length_at(step, c))
        _, l = m(x, y)
        if not torch.isfinite(l):
            raise FloatingPointError(f"loss became {l.item()} at step {step}; lower the learning rate")
        opt.zero_grad(set_to_none=True)
        l.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), t.grad_clip)
        opt.step()
        if on_step:
            on_step(step)

        if step % t.eval_interval == 0 or step == 1 or step == t.max_steps:
            tl = estimate_loss(m, tr, t.batch_size, t.eval_steps, dev)
            el = estimate_loss(m, ev, t.batch_size, t.eval_steps, dev)
            best_eval = min(best_eval, el)
            last_eval = {"step": step, "train_loss": tl, "eval_loss": el}
            if progress:
                tqdm.write(f"step={step} train={tl:.4f} eval={el:.4f} lr={lr_at(step, c):.2e}")
            if on_eval:
                on_eval(step, tl, el)

        if step % t.checkpoint_interval == 0 or step == t.max_steps:
            ck = {
                "format": CHECKPOINT_FORMAT,
                "chit_version": __version__,
                "tokenizer": tok.name,
                "tokenizer_asset": tokenizer_asset,
                "tokenizer_sha256": tokenizer_sha256,
                "model": {k: v.detach().cpu() for k, v in m.state_dict().items()},
                "optimizer": opt.state_dict(),
                "model_config": model_cfg,
                "config": c.to_dict(),
                "step": step,
                "total_steps": init_step + step,
                "init_from": str(init_checkpoint) if init_checkpoint else None,
                "last_eval": last_eval,
                "best_eval_loss": None if math.isinf(best_eval) else best_eval,
                "metadata": metadata or {},
            }
            if keep_step_checkpoints:
                save_checkpoint(ck, out / f"step_{step:06d}.pt")
            save_checkpoint(ck, latest)
            if on_checkpoint:
                on_checkpoint(step, out / f"step_{step:06d}.pt" if keep_step_checkpoints else latest)
    return latest
