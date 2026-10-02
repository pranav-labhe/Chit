"""Generate and score reports for the held-out English capability suite.

The tool exports deterministic candidate responses. Human reviewers supply
hash-bound ratings; it does not attempt to infer linguistic correctness from
training loss or exact string matching.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import torch

from ..formats import render_chat_prompt
from ..runtime import ChitRuntime
from ..training import load_checkpoint


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _outputs(runtime: ChitRuntime, suite: dict, max_new_tokens: int) -> list[dict]:
    block = int(runtime.model_config["block_size"])
    tokenizer = runtime.tokenizer
    results = []
    for case in suite["cases"]:
        prompt = render_chat_prompt(case["prompt"], [], task="chat", history=case.get("history", []))
        prompt_tokens = len(tokenizer.encode(prompt))
        row = {"id": case["id"], "category": case["category"], "subset": case.get("subset"),
               "critical": bool(case.get("critical")), "prompt_tokens": prompt_tokens,
               "context_tokens": block, "scorable": prompt_tokens <= block,
               "response": None, "not_scorable_reason": None}
        if row["scorable"]:
            row["response"] = runtime.generate(
                prompt, max_new_tokens=max_new_tokens, temperature=0.0, top_k=1,
                stop=["\nUser:", "\nChit:", "\nTask:"])
        else:
            row["not_scorable_reason"] = "full prompt exceeds checkpoint context; no truncation was evaluated"
        results.append(row)
    return results


def _training_source_audit(checkpoint: dict, suite: dict) -> tuple[list[dict], set[str]]:
    data_config = checkpoint.get("config", {}).get("data", {})
    configured_sources = data_config.get("sources") or []
    source_paths = ([row["path"] for row in configured_sources]
                    if configured_sources else [data_config.get("train_file", "data/train.txt")])
    normalized_sources = []
    for name in source_paths:
        path = Path(name)
        if not path.is_file():
            raise FileNotFoundError(f"cannot verify held-out prompts; training source is missing: {path}")
        text = " ".join(path.read_text(encoding="utf-8").casefold().split())
        normalized_sources.append({"path": str(path), "sha256": sha256(path), "normalized_text": text})
    overlaps = set()
    for case in suite["cases"]:
        prompt = " ".join(case["prompt"].casefold().split())
        if prompt and any(prompt in source["normalized_text"] for source in normalized_sources):
            overlaps.add(case["id"])
    return ([{"path": row["path"], "sha256": row["sha256"]} for row in normalized_sources], overlaps)


def _gate(suite: dict, outputs: list[dict], ratings_path: Path | None,
          suite_hash: str, checkpoint_hash: str, response_hash: str,
          prompt_overlaps: set[str]) -> dict:
    cases = suite["cases"]
    total = len(cases)
    scorable = sum(bool(row["scorable"]) for row in outputs)
    category_counts = Counter(case["category"] for case in cases)
    report = {"case_count": total, "scorable_count": scorable, "score": None,
              "category_scores": {}, "explicit_continuity": None, "ambiguous_continuity": None,
              "critical_passes": None,
              "training_prompt_overlaps": sorted(prompt_overlaps),
              "gate_pass": False,
              "reason": "human ratings not supplied" if ratings_path is None else "incomplete suite or ratings"}
    if ratings_path is None:
        if scorable != total:
            report["reason"] = f"only {scorable}/{total} prompts fit; behavioral scoring is invalid"
        return report
    ratings = json.loads(ratings_path.read_text(encoding="utf-8"))
    if (ratings.get("english_suite_sha256") != suite_hash or
            ratings.get("checkpoint_sha256") != checkpoint_hash or
            ratings.get("response_set_sha256") != response_hash):
        raise ValueError("ratings must match the exact suite, checkpoint, and generated response hashes")
    by_id = {row.get("id"): row for row in ratings.get("ratings", [])}
    ids = {case["id"] for case in cases}
    if set(by_id) != ids:
        raise ValueError("ratings must contain every English case ID exactly once")
    if any(len(set(row.get("reviewers", []))) < 2 for row in by_id.values()):
        raise ValueError("each English case requires two independent reviewer IDs")
    passes: dict[str, bool] = {}
    for case in cases:
        row = by_id[case["id"]]
        if not isinstance(row.get("passed"), bool):
            raise ValueError(f"rating for {case['id']} must include boolean 'passed'")
        passes[case["id"]] = row["passed"] and not row.get("critical_failure", False)

    counts = Counter()
    passed = Counter()
    for case in cases:
        counts[case["category"]] += 1
        passed[case["category"]] += int(passes[case["id"]])
    category_scores = {name: {"passed": passed[name], "total": count,
                              "rate": passed[name] / count}
                       for name, count in counts.items()}

    def subset_rate(subset_name: str):
        rows = [case for case in cases if case.get("subset") == subset_name]
        return ({"passed": sum(passes[case["id"]] for case in rows), "total": len(rows),
                 "rate": sum(passes[case["id"]] for case in rows) / len(rows)} if rows else None)

    explicit, ambiguous = subset_rate("explicit"), subset_rate("ambiguous")
    critical = [case for case in cases if case.get("critical")]
    critical_passes = sum(passes[case["id"]] for case in critical)
    total_passes = sum(passes.values())
    full = scorable == total
    full_review = len(ratings.get("ratings", [])) == total
    minimum_suite = total >= 120
    content_review = suite.get("content_review", {})
    suite_reviewed = (suite.get("status") == "reviewed" and
                      content_review.get("approved") is True and
                      len(set(content_review.get("reviewers", []))) >= 2)
    gate_pass = (full and full_review and minimum_suite and suite_reviewed and not prompt_overlaps
                 and total_passes >= math.ceil(.85 * total)
                 and all(passed[name] >= math.ceil(.8 * count) for name, count in counts.items())
                 and (explicit is None or explicit["rate"] >= .90)
                 and (ambiguous is None or ambiguous["rate"] >= .80)
                 and critical_passes == len(critical))
    reasons = []
    if not full: reasons.append("one or more prompts exceed context")
    if not minimum_suite: reasons.append("suite has fewer than 120 cases")
    if not suite_reviewed: reasons.append("suite content has not been independently approved by two reviewers")
    if prompt_overlaps: reasons.append("one or more suite prompts occur in the checkpoint training source")
    if total_passes < math.ceil(.85 * total): reasons.append("overall score below 85%")
    if any(passed[name] < math.ceil(.8 * count) for name, count in counts.items()):
        reasons.append("one or more category scores below 80%")
    if explicit and explicit["rate"] < .90: reasons.append("explicit continuity below 90%")
    if ambiguous and ambiguous["rate"] < .80: reasons.append("ambiguous continuity below 80%")
    if critical_passes != len(critical): reasons.append("critical failure present")
    report.update({"score": {"passed": total_passes, "total": total,
                              "rate": total_passes / total if total else 0},
                   "category_scores": category_scores, "explicit_continuity": explicit,
                   "ambiguous_continuity": ambiguous, "critical_passes": critical_passes,
                   "critical_count": len(critical), "gate_pass": gate_pass,
                   "reason": "all gates passed" if gate_pass else "; ".join(reasons)})
    return report


def evaluate(checkpoint_path: Path, suite_path: Path, max_new_tokens: int = 96,
             ratings_path: Path | None = None) -> dict:
    checkpoint = load_checkpoint(checkpoint_path)
    runtime = ChitRuntime.from_checkpoint(checkpoint_path)
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(suite.get("cases"), list) or not suite["cases"]:
        raise ValueError("English suite must contain a non-empty cases list")
    ids = [case.get("id") for case in suite["cases"]]
    if any(not isinstance(case_id, str) or not case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("English suite case IDs must be non-empty and unique")
    suite_hash, checkpoint_hash = sha256(suite_path), sha256(checkpoint_path)
    outputs = _outputs(runtime, suite, max_new_tokens)
    source_manifest, prompt_overlaps = _training_source_audit(checkpoint, suite)
    generation = {"temperature": 0, "top_k": 1, "max_new_tokens": max_new_tokens,
                  "memory": "disabled", "session_history": "only suite-provided history"}
    response_hash = hashlib.sha256(json.dumps(
        {"suite_sha256": suite_hash, "checkpoint_sha256": checkpoint_hash,
         "generation": generation, "outputs": outputs},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite": str(suite_path), "suite_name": suite.get("suite"),
        "suite_version": suite.get("version"), "suite_status": suite.get("status"),
        "suite_sha256": suite_hash,
        "checkpoint": str(checkpoint_path), "checkpoint_sha256": checkpoint_hash,
        "checkpoint_format": checkpoint.get("format"), "step": checkpoint.get("total_steps"),
        "model_config": checkpoint["model_config"],
        "tokenizer": checkpoint.get("tokenizer", "byte-utf8"),
        "tokenizer_sha256": checkpoint.get("tokenizer_sha256"),
        "training_sources": source_manifest,
        "generation": generation,
        "response_set_sha256": response_hash,
        "runtime": {"python": sys.version, "torch": torch.__version__,
                    "platform": platform.platform(), "device": str(runtime.device)},
        "outputs": outputs,
        "behavioral_gate": _gate(suite, outputs, ratings_path, suite_hash, checkpoint_hash,
                                 response_hash, prompt_overlaps),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--suite", type=Path, default=Path("data/english_foundation/eval_suite.json"))
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    args = parser.parse_args(argv)
    if args.max_new_tokens < 1:
        parser.error("max-new-tokens must be positive")
    report = evaluate(args.checkpoint, args.suite, args.max_new_tokens, args.ratings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "suite_sha256": report["suite_sha256"],
                      "checkpoint_sha256": report["checkpoint_sha256"],
                      "behavioral_gate": report["behavioral_gate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
