"""Measure serialized baseline and bounded-queue inference latency."""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import statistics
import time
from pathlib import Path

import torch
import numpy as np

from ..inference import InferenceManager
from ..runtime import ChitRuntime


def percentiles(values: list[float]) -> dict:
    p50, p95, p99 = np.percentile(values, [50, 95, 99])
    return {"p50_ms": float(p50), "p95_ms": float(p95), "p99_ms": float(p99),
            "mean_ms": statistics.fmean(values)}


async def run_benchmark(rt, prompt: str, count: int, max_new_tokens: int) -> dict:
    sequential_latencies: list[float] = []
    sequential_start = time.perf_counter()
    for _ in range(count):
        started = time.perf_counter()
        await asyncio.to_thread(rt.generate, prompt, max_new_tokens, 0.0, 1)
        sequential_latencies.append((time.perf_counter() - started) * 1000)
    sequential_elapsed = time.perf_counter() - sequential_start

    manager = InferenceManager(max_queue_size=max(1, count), queue_timeout_seconds=3600)
    await manager.start()
    latencies: list[float] = []
    start_all = time.perf_counter()

    async def one():
        started = time.perf_counter()
        await manager.run(lambda: rt.generate(prompt, max_new_tokens, temperature=0.0, top_k=1))
        latencies.append((time.perf_counter() - started) * 1000)

    try:
        await asyncio.gather(*(one() for _ in range(count)))
        elapsed = time.perf_counter() - start_all
        return {"requests": count,
                "serialized_baseline": {"elapsed_seconds": sequential_elapsed,
                    "throughput_rps": count / sequential_elapsed,
                    "latency": percentiles(sequential_latencies)},
                "bounded_queue": {"elapsed_seconds": elapsed,
                    "throughput_rps": count / elapsed, "latency": percentiles(latencies)},
                "manager": manager.stats}
    finally:
        await manager.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/latest.pt"))
    parser.add_argument("--prompt", default="Task: continue\nUser: Hello\nChit:")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--tokens", type=int, default=32)
    args = parser.parse_args(argv)
    if args.requests < 1 or args.tokens < 1:
        parser.error("requests and tokens must be positive")
    rt = ChitRuntime.from_checkpoint(args.checkpoint)
    if rt.device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(rt.device)
    rt.generate(args.prompt, min(args.tokens, 4), temperature=0.0, top_k=1)  # warm-up
    result = asyncio.run(run_benchmark(rt, args.prompt, args.requests, args.tokens))
    result.update({"checkpoint": str(args.checkpoint), "device": str(rt.device),
                   "model_config": rt.model_config, "tokenizer": rt.tokenizer.name,
                   "torch_version": torch.__version__, "python": platform.python_version(),
                   "platform": platform.platform(),
                   "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(rt.device)
                   if rt.device.type == "cuda" else None})
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
