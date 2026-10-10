"""Reproducible checkpoint evaluation and golden-set response export."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import torch

from ..formats import render_chat_prompt
from ..runtime import ChitRuntime
from ..training import load_checkpoint


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stream_metrics(runtime: ChitRuntime, text: str) -> dict:
    ids = runtime.tokenizer.encode(text)
    block = int(runtime.model_config["block_size"])
    nll, correct, count = 0.0, 0, 0
    with torch.inference_mode():
        for start in range(0, max(0, len(ids) - 1), block):
            x_ids, y_ids = ids[start:start + block], ids[start + 1:start + block + 1]
            n = min(len(x_ids), len(y_ids))
            if not n:
                continue
            x = torch.tensor([x_ids[:n]], dtype=torch.long, device=runtime.device)
            y = torch.tensor([y_ids[:n]], dtype=torch.long, device=runtime.device)
            logits, loss = runtime.model(x, y)
            nll += float(loss.item()) * n
            correct += int((logits.argmax(dim=-1) == y).sum().item())
            count += n
    mean_nats = nll / count if count else None
    byte_count = len(text.encode("utf-8"))
    return {
        "tokens": len(ids), "target_tokens": count, "utf8_bytes": byte_count,
        "nats_per_token": mean_nats,
        "perplexity": math.exp(mean_nats) if mean_nats is not None and mean_nats < 700 else None,
        "bits_per_byte": nll / (byte_count * math.log(2)) if count and byte_count else None,
        "next_token_accuracy": correct / count if count else None,
        "evaluation_method": "deterministic non-overlapping target windows of block_size",
    }


def _golden_outputs(runtime: ChitRuntime, golden: dict, max_new_tokens: int) -> list[dict]:
    results = []
    block = int(runtime.model_config["block_size"])
    for case in golden["cases"]:
        prompt = render_chat_prompt(case["prompt"], [], task="chat")
        n_prompt = len(runtime.tokenizer.encode(prompt))
        result = {"id": case["id"], "category": case["category"],
                  "critical": bool(case["critical"]), "prompt_tokens": n_prompt,
                  "context_tokens": block, "scorable": n_prompt <= block,
                  "response": None, "not_scorable_reason": None}
        if n_prompt > block:
            result["not_scorable_reason"] = "prompt exceeds checkpoint context; no truncation was evaluated"
        else:
            started = time.perf_counter()
            result["response"] = runtime.generate(prompt, max_new_tokens=max_new_tokens,
                                                  temperature=0.0, top_k=1,
                                                  stop=["\nUser:", "\nChit:", "\nTask:"])
            result["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        results.append(result)
    return results


def _golden_gate(golden: dict, outputs: list[dict], ratings_path: Path | None,
                 set_hash: str, checkpoint_hash: str) -> dict:
    coverage = sum(row["scorable"] for row in outputs)
    report = {"case_count": len(outputs), "scorable_count": coverage,
              "score": None, "category_scores": {}, "critical_passes": None,
              "critical_count": sum(bool(c["critical"]) for c in golden["cases"]),
              "gate_pass": False, "reason": "human ratings not supplied"}
    if ratings_path is None:
        if coverage != len(outputs):
            report["reason"] = (f"only {coverage}/{len(outputs)} prompts fit without truncation; "
                                "behavioral score is not valid")
        return report
    ratings = json.loads(ratings_path.read_text(encoding="utf-8"))
    if ratings.get("golden_set_sha256") != set_hash or ratings.get("checkpoint_sha256") != checkpoint_hash:
        raise ValueError("ratings must identify the exact golden set and checkpoint hashes")
    by_id = {row["id"]: row for row in ratings.get("ratings", [])}
    expected_ids = {row["id"] for row in outputs}
    if set(by_id) != expected_ids:
        raise ValueError("ratings must contain each golden case ID exactly once")
    if any(len(set(row.get("reviewers", []))) < 2 for row in by_id.values()):
        raise ValueError("each golden case requires two independent reviewer IDs")
    pass_counts, totals = Counter(), Counter()
    critical_passes = critical_total = 0
    for case in golden["cases"]:
        rating = by_id[case["id"]]
        if not isinstance(rating.get("passed"), bool):
            raise ValueError(f"rating for {case['id']} must include boolean 'passed'")
        passed = rating["passed"] and not rating.get("critical_failure", False)
        totals[case["category"]] += 1
        pass_counts[case["category"]] += int(passed)
        if case["critical"]:
            critical_total += 1
            critical_passes += int(passed)
    total_passes = sum(pass_counts.values())
    category_scores = {name: {"passed": pass_counts[name], "total": total}
                       for name, total in totals.items()}
    complete = coverage == len(outputs)
    gate_pass = (complete and total_passes >= math.ceil(0.85 * len(outputs)) and
                 all(pass_counts[name] >= math.ceil(0.8 * total) for name, total in totals.items()) and
                 critical_passes == critical_total)
    case_ratings = [{"id": case["id"], "category": case["category"],
                     "critical": bool(case["critical"]),
                     "passed": bool(by_id[case["id"]]["passed"] and
                                    not by_id[case["id"]].get("critical_failure", False))}
                    for case in golden["cases"]]
    return {"case_count": len(outputs), "scorable_count": coverage,
            "score": {"passed": total_passes, "total": len(outputs),
                      "rate": total_passes / len(outputs)},
            "category_scores": category_scores, "critical_passes": critical_passes,
            "critical_count": critical_total, "case_ratings": case_ratings,
            "gate_pass": gate_pass,
            "reason": "all cases fit and satisfy gates" if gate_pass else "one or more behavioral gates failed"}


def evaluate_checkpoint(checkpoint_path: Path, eval_file: Path, golden_set_path: Path,
                        *, include_golden: bool = True, max_new_tokens: int = 128,
                        ratings_path: Path | None = None) -> dict:
    """Reusable evaluator for CLI runs and training-job checkpoint callbacks."""
    checkpoint = load_checkpoint(checkpoint_path)
    runtime = ChitRuntime.from_checkpoint(checkpoint_path)
    eval_text = eval_file.read_text(encoding="utf-8")
    golden = json.loads(golden_set_path.read_text(encoding="utf-8"))
    checkpoint_hash, set_hash = _sha256(checkpoint_path), _sha256(golden_set_path)
    outputs = (_golden_outputs(runtime, golden, max_new_tokens) if include_golden else [])
    behavioral = (_golden_gate(golden, outputs, ratings_path, set_hash, checkpoint_hash)
                  if include_golden else {
                      "case_count": len(golden["cases"]), "scorable_count": 0,
                      "score": None, "category_scores": {}, "critical_passes": None,
                      "critical_count": sum(bool(c["critical"]) for c in golden["cases"]),
                      "gate_pass": False, "reason": "behavioral response evaluation deferred"})
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint": str(checkpoint_path), "checkpoint_sha256": checkpoint_hash,
        "checkpoint_format": checkpoint.get("format"), "step": checkpoint.get("total_steps"),
        "model_config": checkpoint["model_config"],
        "tokenizer": checkpoint.get("tokenizer", "byte-utf8"),
        "tokenizer_sha256": checkpoint.get("tokenizer_sha256"),
        "eval_file": str(eval_file), "eval_file_sha256": _sha256(eval_file),
        "golden_set": str(golden_set_path), "golden_set_version": golden.get("version"),
        "golden_set_sha256": set_hash,
        "runtime": {"python": sys.version, "torch": torch.__version__,
                    "platform": platform.platform(), "device": str(runtime.device)},
        "language_model_metrics": _stream_metrics(runtime, eval_text),
        "golden_outputs": outputs,
        "behavioral_gate": behavioral,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--eval-file", type=Path, default=Path("data/eval.txt"))
    parser.add_argument("--golden-set", type=Path, default=Path("data/golden_set.json"))
    parser.add_argument("--ratings", type=Path, help="human-adjudicated ratings JSON (two reviewers per case)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    args = parser.parse_args(argv)
    if args.max_new_tokens < 1:
        parser.error("max-new-tokens must be positive")
    report = evaluate_checkpoint(args.checkpoint, args.eval_file, args.golden_set,
                                 include_golden=True, max_new_tokens=args.max_new_tokens,
                                 ratings_path=args.ratings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "checkpoint_sha256": report["checkpoint_sha256"],
                      "language_model_metrics": report["language_model_metrics"],
                      "behavioral_gate": report["behavioral_gate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
