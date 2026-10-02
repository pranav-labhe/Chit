"""Typed configuration for Chit, loaded from JSON files in ``configs/``.

Unknown keys are rejected so a typo in a config file fails loudly instead of
being silently ignored, and every value is range-checked on construction.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

DEVICES = ("auto", "cpu", "cuda")
LR_SCHEDULES = ("constant", "linear", "cosine")
POSITION_ENCODINGS = ("absolute", "rope")


class ConfigError(ValueError):
    """A configuration value is missing, unknown or out of range."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ConfigError(message)


@dataclass
class ModelConfig:
    vocab_size: int = 256
    block_size: int = 128
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 128
    dropout: float = 0.0
    position_encoding: str = "absolute"
    rope_theta: float = 10000.0

    def __post_init__(self) -> None:
        for name in ("vocab_size", "block_size", "n_layer", "n_head", "n_embd"):
            _require(isinstance(getattr(self, name), int) and getattr(self, name) >= 1,
                     f"model.{name} must be a positive integer")
        _require(self.n_embd % self.n_head == 0,
                 f"model.n_embd ({self.n_embd}) must be divisible by model.n_head ({self.n_head})")
        _require(0.0 <= self.dropout < 1.0, "model.dropout must be in [0, 1)")
        _require(self.position_encoding in POSITION_ENCODINGS,
                 f"model.position_encoding must be one of {POSITION_ENCODINGS}")
        _require(self.rope_theta > 0, "model.rope_theta must be > 0")
        if self.position_encoding == "rope":
            _require((self.n_embd // self.n_head) % 2 == 0,
                     "RoPE requires an even attention head dimension")


@dataclass
class TrainingConfig:
    batch_size: int = 16
    learning_rate: float = 3e-4
    weight_decay: float = 0.1
    max_steps: int = 1000
    eval_interval: int = 100
    eval_steps: int = 20
    checkpoint_interval: int = 100
    grad_clip: float = 1.0
    warmup_steps: int = 0
    lr_schedule: str = "constant"
    min_lr_ratio: float = 0.1
    context_curriculum: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in ("batch_size", "max_steps", "eval_interval", "eval_steps", "checkpoint_interval"):
            _require(isinstance(getattr(self, name), int) and getattr(self, name) >= 1,
                     f"training.{name} must be a positive integer")
        _require((self.max_steps + self.checkpoint_interval - 1) // self.checkpoint_interval <= 1000,
                 "training configuration may save at most 1000 checkpoints per job")
        _require(self.learning_rate > 0, "training.learning_rate must be > 0")
        _require(self.weight_decay >= 0, "training.weight_decay must be >= 0")
        _require(self.grad_clip > 0, "training.grad_clip must be > 0")
        _require(isinstance(self.warmup_steps, int) and self.warmup_steps >= 0,
                 "training.warmup_steps must be a non-negative integer")
        _require(self.lr_schedule in LR_SCHEDULES, f"training.lr_schedule must be one of {LR_SCHEDULES}")
        _require(0.0 <= self.min_lr_ratio <= 1.0, "training.min_lr_ratio must be in [0, 1]")
        _require(all(isinstance(v, int) and v >= 1 for v in self.context_curriculum),
                 "training.context_curriculum must contain positive integer token lengths")
        _require(all(a < b for a, b in zip(self.context_curriculum, self.context_curriculum[1:])),
                 "training.context_curriculum must be strictly increasing")


@dataclass
class DataSourceConfig:
    """A named corpus stream used by source-aware mixed training."""
    path: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        _require(isinstance(self.path, str) and bool(self.path.strip()),
                 "data.sources[].path must be a non-empty string")
        _require(isinstance(self.weight, (int, float)) and math.isfinite(self.weight) and self.weight > 0,
                 "data.sources[].weight must be a finite number greater than 0")


@dataclass
class DataConfig:
    train_file: str = "data/train.txt"
    eval_file: str = "data/eval.txt"
    sources: list[DataSourceConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        paths = [source.path for source in self.sources]
        _require(len(paths) == len(set(paths)), "data.sources must not contain duplicate paths")


@dataclass
class TokenizerConfig:
    name: str = "byte-utf8"
    model_file: str | None = None

    def __post_init__(self) -> None:
        _require(self.name in ("byte-utf8", "bpe-tokenizers-json-v1"),
                 "tokenizer.name must be 'byte-utf8' or 'bpe-tokenizers-json-v1'")
        if self.name == "bpe-tokenizers-json-v1":
            _require(bool(self.model_file), "tokenizer.model_file is required for BPE")


@dataclass
class ChitConfig:
    seed: int = 42
    device: str = "auto"
    model: ModelConfig = field(default_factory=ModelConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    data: DataConfig = field(default_factory=DataConfig)
    tokenizer: TokenizerConfig = field(default_factory=TokenizerConfig)

    def __post_init__(self) -> None:
        _require(isinstance(self.seed, int) and 0 <= self.seed < 2**32, "seed must be an integer in [0, 2**32)")
        _require(self.device in DEVICES, f"device must be one of {DEVICES}")
        _require(not self.training.context_curriculum or
                 (self.training.context_curriculum[0] <= self.model.block_size and
                  self.training.context_curriculum[-1] == self.model.block_size and
                  len(self.training.context_curriculum) <= self.training.max_steps),
                 "training.context_curriculum must not exceed model.block_size, end at it, and have "
                 "no more stages than max_steps")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _section(cls, raw: Any, name: str):
    if raw is None:
        return cls()
    _require(isinstance(raw, dict), f"{name} must be an object")
    unknown = set(raw) - {f.name for f in fields(cls)}
    _require(not unknown, f"unknown key(s) in {name}: {', '.join(sorted(unknown))}")
    try:
        return cls(**raw)
    except TypeError as e:  # wrong value types that dataclass construction rejects
        raise ConfigError(f"{name}: {e}") from e


def config_from_dict(raw: dict[str, Any]) -> ChitConfig:
    _require(isinstance(raw, dict), "config must be a JSON object")
    unknown = set(raw) - {f.name for f in fields(ChitConfig)}
    _require(not unknown, f"unknown top-level key(s): {', '.join(sorted(unknown))}")
    data_raw = raw.get("data")
    if isinstance(data_raw, dict) and "sources" in data_raw:
        data_raw = dict(data_raw)
        source_rows = data_raw["sources"]
        _require(isinstance(source_rows, list), "data.sources must be a list")
        data_raw["sources"] = [
            _section(DataSourceConfig, row, f"data.sources[{i}]") for i, row in enumerate(source_rows)
        ]
    return ChitConfig(
        seed=raw.get("seed", 42),
        device=raw.get("device", "auto"),
        model=_section(ModelConfig, raw.get("model"), "model"),
        training=_section(TrainingConfig, raw.get("training"), "training"),
        data=_section(DataConfig, data_raw, "data"),
        tokenizer=_section(TokenizerConfig, raw.get("tokenizer"), "tokenizer"),
    )


def load_config(path: str | Path) -> ChitConfig:
    """Load and validate a config file. Raises ConfigError, or OSError if unreadable."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: invalid JSON ({e})") from e
    return config_from_dict(raw)
