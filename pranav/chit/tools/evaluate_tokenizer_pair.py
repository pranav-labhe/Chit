"""Compare matched byte and BPE checkpoints on held-out NLL and generation speed."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path

import torch
import numpy as np

from ..runtime import ChitRuntime
from ..training import load_checkpoint


def _percentiles(samples: list[float]) -> dict:
    p50, p95, p99 = np.percentile(samples, [50, 95, 99])
    return {"p50_ms": float(p50), "p95_ms": float(p95), "p99_ms": float(p99),
            "mean_ms": statistics.fmean(samples), "stdev_ms": statistics.pstdev(samples)}


def _heldout_metrics(runtime: ChitRuntime, text: str) -> dict:
    ids = runtime.tokenizer.encode(text)
    block = runtime.model_config["block_size"]
    nll = 0.0
    target_count = 0
    with torch.inference_mode():
        for start in range(0, max(0, len(ids) - 1), block):
            x_ids = ids[start:start + block]
            y_ids = ids[start + 1:start + block + 1]
            count = min(len(x_ids), len(y_ids))
            if not count:
                continue
            x = torch.tensor([x_ids[:count]], dtype=torch.long, device=runtime.device)
            y = torch.tensor([y_ids[:count]], dtype=torch.long, device=runtime.device)
            _, loss = runtime.model(x, y)
            nll += float(loss.item()) * count
            target_count += count
    mean_nll = nll / target_count if target_count else math.nan
    byte_count = len(text.encode("utf-8"))
    return {"eval_utf8_bytes": byte_count, "eval_tokens": len(ids),
            "eval_nats_per_token": mean_nll,
            "eval_bits_per_byte": nll / (byte_count * math.log(2)) if byte_count else math.nan}


def _generation_pair(runtimes: dict[str, ChitRuntime], prompt: str, count: int, tokens: int) -> dict:
    latencies = {name: [] for name in runtimes}
    char_counts = {name: [] for name in runtimes}
    for runtime in runtimes.values():
        for _ in range(3):
            runtime.generate(prompt, max_new_tokens=tokens, temperature=0.0, top_k=1)
    names = list(runtimes)
    for iteration in range(count):
        order = names if iteration % 2 == 0 else list(reversed(names))
        for name in order:
            started = time.perf_counter()
            output = runtimes[name].generate(prompt, max_new_tokens=tokens, temperature=0.0, top_k=1)
            latencies[name].append((time.perf_counter() - started) * 1000)
            char_counts[name].append(len(output))
    results = {}
    for name in names:
        elapsed = sum(latencies[name]) / 1000
        results[name] = {"runs": count, "max_new_tokens": tokens,
                         "latency": _percentiles(latencies[name]),
                         "mean_generated_tokens_per_second": count * tokens / elapsed,
                         "mean_output_chars_per_second": sum(char_counts[name]) / elapsed}
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--byte-checkpoint", type=Path, required=True)
    parser.add_argument("--bpe-checkpoint", type=Path, required=True)
    parser.add_argument("--eval-file", type=Path, default=Path("data/eval.txt"))
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--tokens", type=int, default=32)
    args = parser.parse_args(argv)
    if args.runs < 1 or args.tokens < 1:
        parser.error("runs and tokens must be positive")
    text = args.eval_file.read_text(encoding="utf-8")
    prompt = "Task: continue\nUser: Explain why it helps to check one assumption before acting.\nChit:"
    result = {"eval_file": str(args.eval_file), "runs": args.runs, "generation_tokens": args.tokens,
              "comparisons": {}}
    runtimes = {}
    for name, checkpoint_path in (("byte", args.byte_checkpoint), ("bpe", args.bpe_checkpoint)):
        checkpoint = load_checkpoint(checkpoint_path)
        runtime = ChitRuntime.from_checkpoint(checkpoint_path)
        runtimes[name] = runtime
        result["comparisons"][name] = {
            "checkpoint": str(checkpoint_path), "step": checkpoint.get("total_steps"),
            "tokenizer": checkpoint.get("tokenizer", "byte-utf8"),
            "model_config": checkpoint["model_config"],
            "last_eval": checkpoint.get("last_eval"),
            "heldout": _heldout_metrics(runtime, text),
        }
    for name, metrics in _generation_pair(runtimes, prompt, args.runs, args.tokens).items():
        result["comparisons"][name]["generation"] = metrics
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
