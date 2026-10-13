"""Benchmark Bridge pipeline performance, fidelity, and quality metrics."""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path
from typing import Any

from pranav.chit.bridge import Bridge, BridgeConfig, Context
from pranav.chit.runtime import ChitRuntime


DEDICATED_PROBES = [
    # Arithmetic Probes (symbolic and word-form)
    {"id": "PROBE_MATH_01", "type": "arithmetic", "prompt": "What is 14 + 28?", "expected": "42", "search": False, "think": False},
    {"id": "PROBE_MATH_02", "type": "arithmetic", "prompt": "Calculate 100 - 37", "expected": "63", "search": False, "think": False},
    {"id": "PROBE_MATH_03", "type": "arithmetic", "prompt": "What is 6 * 7?", "expected": "42", "search": False, "think": False},
    {"id": "PROBE_MATH_04", "type": "arithmetic", "prompt": "Compute 48 / 6", "expected": "8", "search": False, "think": False},
    {"id": "PROBE_MATH_05", "type": "arithmetic", "prompt": "What is 12 plus 15?", "expected": "27", "search": False, "think": False},
    {"id": "PROBE_MATH_06", "type": "arithmetic", "prompt": "What is 50 minus 18?", "expected": "32", "search": False, "think": False},
    {"id": "PROBE_MATH_07", "type": "arithmetic", "prompt": "What is 7 times 8?", "expected": "56", "search": False, "think": False},
    {"id": "PROBE_MATH_08", "type": "arithmetic", "prompt": "What is 72 divided by 9?", "expected": "8", "search": False, "think": False},

    # Long-Context Queries (testing working memory and context budget limits)
    {
        "id": "PROBE_CTX_01",
        "type": "long_context",
        "prompt": "Here is our discussion: Project Chit is a 4.87M parameter byte Transformer. It operates with a compact context window. Please state the exact name of the project.",
        "must_include": ["chit"],
        "search": False,
        "think": False,
    },
    {
        "id": "PROBE_CTX_02",
        "type": "long_context",
        "prompt": "We previously discussed three principles: 1) Model Capability, 2) Pipeline Fidelity, and 3) Pipeline Damage. Which principle subtracts from System Quality?",
        "must_include": ["damage"],
        "search": False,
        "think": False,
    },
    {
        "id": "PROBE_CTX_03",
        "type": "long_context",
        "prompt": "Consider the following sequence of instructions: Step A is verification, Step B is execution, Step C is reflection. What is the very first step?",
        "must_include": ["step a", "verification"],
        "search": False,
        "think": False,
    },
    {
        "id": "PROBE_CTX_04",
        "type": "long_context",
        "prompt": "In an architectural redesign with frozen weights, we decouple policy from execution. Are model weights retrained or frozen?",
        "must_include": ["frozen"],
        "search": False,
        "think": False,
    },

    # Web turns (factual queries testing grounding and retrieval)
    {"id": "PROBE_WEB_01", "type": "web", "prompt": "What is the capital city of France?", "must_include": ["paris"], "search": True, "think": False},
    {"id": "PROBE_WEB_02", "type": "web", "prompt": "How many continents are there on Earth?", "must_include": ["7", "seven"], "search": True, "think": False},
    {"id": "PROBE_WEB_03", "type": "web", "prompt": "What is the chemical symbol for water?", "must_include": ["h2o"], "search": True, "think": False},
]

LEGACY_CANNED_REPLIES = {
    "hello! how can i help you today?",
    "i am here to help. what would you like to explore or work through?",
}


def detect_loop(text: str) -> bool:
    """Detect degenerate token loops or repeated n-grams (> 3 repeats)."""
    clean = text.strip().lower()
    if not clean:
        return False
    # Check repeated words / n-grams
    words = re.findall(r"\b\w+\b", clean)
    if len(words) >= 4:
        # Check single word loop
        for i in range(len(words) - 3):
            if words[i] == words[i + 1] == words[i + 2] == words[i + 3]:
                return True
        # Check 2-gram loop
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
        for i in range(len(bigrams) - 6):
            if bigrams[i] == bigrams[i + 2] == bigrams[i + 4] == bigrams[i + 6]:
                return True
        # Check 3-gram loop
        trigrams = [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words) - 2)]
        for i in range(len(trigrams) - 6):
            if trigrams[i] == trigrams[i + 3] == trigrams[i + 6]:
                return True
    # Character loop (e.g. "......", "aaaaa")
    if re.search(r"(.)\1{5,}", clean):
        return True
    return False


def compute_ece(confidences: list[float], accuracies: list[bool], n_bins: int = 10) -> float:
    """Expected Calibration Error across n_bins in [0, 1]."""
    if not confidences or not accuracies:
        return 0.0

    bins = [[] for _ in range(n_bins)]
    for conf, acc in zip(confidences, accuracies):
        clamped = max(0.0, min(0.999999, conf))
        bin_idx = int(clamped * n_bins)
        bins[bin_idx].append((conf, 1.0 if acc else 0.0))

    total = len(confidences)
    ece = 0.0
    for b in bins:
        if not b:
            continue
        bin_size = len(b)
        avg_conf = sum(x[0] for x in b) / bin_size
        avg_acc = sum(x[1] for x in b) / bin_size
        ece += (bin_size / total) * abs(avg_acc - avg_conf)

    return round(ece, 4)


def evaluate_case(bridge: Bridge, item: dict[str, Any]) -> dict[str, Any]:
    prompt = item["prompt"]
    search = bool(item.get("search", False))
    think = bool(item.get("think", False))

    ctx = Context(user_input=prompt, search=search, think=think)
    t0 = time.perf_counter()
    decision = bridge.process(ctx)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    text = decision.text or ""
    lower_text = text.lower()
    meta = decision.metadata or {}

    # 1. Loop detection
    is_loop = detect_loop(text)

    # 2. Replacement char
    has_replacement = "\ufffd" in text

    # 3. Truncated before stop
    is_incomplete = meta.get("is_incomplete", False)
    if not is_incomplete and text:
        trimmed = text.rstrip(" \t")
        # If text doesn't end with terminal punctuation
        if not trimmed.endswith((".", "!", "?", '"', "'", "\n", "`", "}")):
            is_incomplete = True

    # 4. Canned reply check
    is_canned = False
    clean_lower = lower_text.strip()
    if clean_lower in LEGACY_CANNED_REPLIES or meta.get("grounding_fallback", False):
        is_canned = True

    # Correctness check
    is_correct = False
    if "expected" in item:
        # Arithmetic exact match: check if expected number appears as an isolated token or exact result
        expected = str(item["expected"]).lower().strip()
        tokens = re.findall(r"\b\w+\b", lower_text)
        is_correct = expected in tokens or expected in lower_text
    elif "must_include" in item:
        all_included = True
        for req in item["must_include"]:
            req_clean = req.lower().strip()
            # If multiple options separated by 'or'
            sub_options = [opt.strip() for opt in req_clean.split(" or ")]
            if not any(opt in lower_text for opt in sub_options):
                all_included = False
                break
        must_avoid = item.get("must_avoid", [])
        none_avoided = True
        for req in must_avoid:
            if req.lower().strip() in lower_text:
                none_avoided = False
                break
        is_correct = all_included and none_avoided

    raw_conf = float(meta.get("confidence") or (decision.confidence if decision.confidence is not None else 0.5))

    return {
        "id": item["id"],
        "prompt": prompt,
        "type": item.get("type", item.get("category", "golden")),
        "output": text,
        "raw_text": meta.get("raw_text", text),
        "confidence": raw_conf,
        "latency_ms": latency_ms,
        "is_loop": is_loop,
        "has_replacement": has_replacement,
        "is_incomplete": is_incomplete,
        "is_canned": is_canned,
        "is_correct": is_correct,
        "source": meta.get("source", "neural"),
    }


def run_benchmark(checkpoint_path: str = "checkpoints/latest.pt",
                  golden_path: str = "data/golden_set.json",
                  output_path: str | None = None,
                  config: BridgeConfig | None = None) -> dict[str, Any]:
    print(f"Loading runtime from {checkpoint_path}...")
    runtime = ChitRuntime.from_checkpoint(checkpoint_path)
    bridge = Bridge(runtime, config=config)

    golden_cases = []
    golden_file = Path(golden_path)
    if golden_file.exists():
        data = json.loads(golden_file.read_text(encoding="utf-8"))
        golden_cases = data.get("cases", [])

    all_cases = golden_cases + DEDICATED_PROBES
    print(f"Evaluating {len(all_cases)} total cases ({len(golden_cases)} golden + {len(DEDICATED_PROBES)} probes)...")

    results = []
    latencies = []
    confidences = []
    accuracies = []

    math_total = 0
    math_correct = 0

    for i, item in enumerate(all_cases, 1):
        res = evaluate_case(bridge, item)
        results.append(res)
        latencies.append(res["latency_ms"])
        confidences.append(res["confidence"])
        accuracies.append(res["is_correct"])

        if item.get("type") == "arithmetic" or "PROBE_MATH" in item.get("id", ""):
            math_total += 1
            if res["is_correct"]:
                math_correct += 1

        print(f"[{i}/{len(all_cases)}] {res['id']}: correct={res['is_correct']}, conf={res['confidence']:.2f}, lat={res['latency_ms']:.1f}ms")

    latencies.sort()
    p95_idx = int(0.95 * len(latencies))
    p95_latency = round(latencies[min(p95_idx, len(latencies) - 1)], 2)

    total_n = len(results)
    loop_rate = round(sum(r["is_loop"] for r in results) / total_n, 4)
    replacement_rate = round(sum(r["has_replacement"] for r in results) / total_n, 4)
    truncated_rate = round(sum(r["is_incomplete"] for r in results) / total_n, 4)
    canned_rate = round(sum(r["is_canned"] for r in results) / total_n, 4)
    arithmetic_exact_match = round(math_correct / math_total, 4) if math_total else 0.0
    ece = compute_ece(confidences, accuracies)

    metrics = {
        "checkpoint": checkpoint_path,
        "total_cases": total_n,
        "golden_cases_count": len(golden_cases),
        "probe_cases_count": len(DEDICATED_PROBES),
        "loop_rate": loop_rate,
        "replacement_char_rate": replacement_rate,
        "truncated_before_stop_rate": truncated_rate,
        "canned_reply_rate": canned_rate,
        "arithmetic_exact_match": arithmetic_exact_match,
        "expected_calibration_error": ece,
        "p95_latency_ms": p95_latency,
        "details": results,
    }

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Results saved to {output_path}")

    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Bridge pipeline fidelity and quality metrics.")
    parser.add_argument("--checkpoint", default="checkpoints/latest.pt", help="Path to checkpoint")
    parser.add_argument("--golden-set", default="data/golden_set.json", help="Path to golden set JSON")
    parser.add_argument("--output", default="docs/benchmarks/bridge-refactor-final.json", help="Path to output JSON")
    parser.add_argument("--enable-calibration", action="store_true", help="Enable isotonic confidence calibration")
    parser.add_argument("--enable-verifier", action="store_true", help="Enable generic verifier")
    parser.add_argument("--disable-calculator", action="store_true", help="Disable calculator tool")
    parser.add_argument("--disable-budget", action="store_true", help="Disable reserve generation budget")
    parser.add_argument("--disable-attractor-shim", action="store_true", help="Disable legacy attractor shim")
    parser.add_argument("--temperature", type=float, default=0.7, help="Default sampling temperature")
    args = parser.parse_args()

    config = BridgeConfig(
        enable_calculator=not args.disable_calculator,
        enable_generic_verifier=args.enable_verifier,
        enable_calibration=args.enable_calibration,
        legacy_attractor_shim=not args.disable_attractor_shim,
        reserve_generation_budget=not args.disable_budget,
        default_temperature=args.temperature,
    )

    metrics = run_benchmark(args.checkpoint, args.golden_set, args.output, config=config)
    print("\n--- Summary Metrics ---")
    for k in ["loop_rate", "replacement_char_rate", "truncated_before_stop_rate",
              "canned_reply_rate", "arithmetic_exact_match", "expected_calibration_error", "p95_latency_ms"]:
        print(f"  {k}: {metrics[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
