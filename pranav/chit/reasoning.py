"""Reasoning examples (JSONL with input / reasoning / answer)."""
from __future__ import annotations

import json
from pathlib import Path

from .formats import render_reasoning

REQUIRED = ("input", "reasoning", "answer")


def load_reasoning_examples(path: str | Path = "data/reasoning.jsonl") -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                x = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: invalid JSON ({e})") from e
            missing = [k for k in REQUIRED if not isinstance(x.get(k), str) or not x[k].strip()]
            if missing:
                raise ValueError(f"{path}:{n}: missing or empty field(s): {', '.join(missing)}")
            out.append(x)
    return out


def format_reasoning_example(x: dict) -> str:
    return render_reasoning(x["input"], x["reasoning"], x["answer"])
