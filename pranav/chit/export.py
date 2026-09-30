"""Export a training checkpoint as a versioned, inference-only bundle."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import torch

from . import __version__
from .model import clean_state_dict
from .training import load_checkpoint


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def export_chit(checkpoint_path, output_dir="exports/chit_v1") -> Path:
    """Write weights (no optimizer state), model config and metadata with a checksum."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ck = load_checkpoint(checkpoint_path)
    weights = out / "chit_weights.pt"
    torch.save(clean_state_dict(ck["model"]), weights)
    (out / "model_config.json").write_text(json.dumps(ck["model_config"], indent=2), encoding="utf-8")
    meta = {
        "version": __version__,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_checkpoint": str(checkpoint_path),
        "step": ck.get("step"),
        "total_steps": ck.get("total_steps", ck.get("step")),
        "best_eval_loss": ck.get("best_eval_loss"),
        "tokenizer": ck.get("tokenizer", "byte-utf8"),
        "weights_sha256": _sha256(weights),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out
