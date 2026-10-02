"""Promote an evaluated checkpoint after paired golden-set review.

The service must be restarted after promotion to load the new champion. Training
jobs never invoke this command or overwrite the serving checkpoint directly.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..promotion_state import file_sha256, install_checkpoint, recover_promotion
from ..runtime import ChitRuntime


def sha256(path: Path) -> str:
    return file_sha256(path)


def paired_lower_bound(candidate: list[dict], champion: list[dict], *, samples: int = 20_000) -> float:
    """One-sided 95% bootstrap lower bound for candidate's paired pass-rate lift."""
    c, h = {x["id"]: bool(x["passed"]) for x in candidate}, {x["id"]: bool(x["passed"]) for x in champion}
    if not c or c.keys() != h.keys():
        raise ValueError("reports must contain the same non-empty golden case IDs")
    diffs = [int(c[k]) - int(h[k]) for k in sorted(c)]
    rng, means = random.Random(20261003), []
    for _ in range(samples):
        means.append(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs))
    return sorted(means)[int(0.05 * (samples - 1))]


def _compatible(candidate_ckpt: Path, champion_ckpt: Path) -> None:
    challenger, champion = ChitRuntime.from_checkpoint(candidate_ckpt), ChitRuntime.from_checkpoint(champion_ckpt)
    if challenger.tokenizer.name != champion.tokenizer.name:
        raise ValueError("tokenizer family differs; promotion requires a separately approved migration")


def promote(candidate: Path, candidate_eval: Path, champion_eval: Path,
            target: Path, *, min_lift: float = 0.02) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    recover_promotion(target)
    report, incumbent = json.loads(candidate_eval.read_text()), json.loads(champion_eval.read_text())
    candidate_hash, champion_hash = sha256(candidate), sha256(target)
    for label, ev, actual in (("candidate", report, candidate_hash), ("champion", incumbent, champion_hash)):
        if ev.get("checkpoint_sha256") != actual:
            raise ValueError(f"{label} evaluation does not match the checkpoint hash")
    candidate_gate = report.get("behavioral_gate", {})
    if not candidate_gate.get("gate_pass"):
        raise ValueError("candidate behavioral gate is not passing and fully scorable")
    if report.get("golden_set_sha256") != incumbent.get("golden_set_sha256"):
        raise ValueError("candidate and champion must use the same versioned golden set")
    if report.get("eval_file_sha256") != incumbent.get("eval_file_sha256"):
        raise ValueError("candidate and champion must use the same held-out evaluation data")
    incumbent_gate = incumbent.get("behavioral_gate", {})
    initial_champion = (not incumbent_gate.get("gate_pass") and
                        incumbent_gate.get("scorable_count") == 0 and
                        incumbent_gate.get("case_count", 0) >= 50 and
                        len(incumbent.get("golden_outputs", [])) == incumbent_gate.get("case_count") and
                        all(row.get("not_scorable_reason", "").startswith("prompt exceeds checkpoint context")
                            for row in incumbent["golden_outputs"]))
    if incumbent_gate.get("gate_pass"):
        lift_lb = paired_lower_bound(report["behavioral_gate"]["case_ratings"],
                                    incumbent_gate["case_ratings"])
        if lift_lb <= min_lift:
            raise ValueError(f"candidate lift lower bound {lift_lb:.4f} does not exceed {min_lift:.4f}")
    elif initial_champion:
        # A context-ineligible incumbent cannot supply paired behavioral
        # evidence. Permit first release only through the strict absolute gate
        # already satisfied by two-reviewer scoring; retain held-out regression.
        lift_lb = None
    else:
        raise ValueError("champion has no comparable passing behavioral report")
    c_metric = report["language_model_metrics"]["bits_per_byte"]
    h_metric = incumbent["language_model_metrics"]["bits_per_byte"]
    if not (math.isfinite(c_metric) and math.isfinite(h_metric)) or c_metric > h_metric * 1.05:
        raise ValueError("candidate held-out bits/byte regresses by more than the allowed 5%")
    _compatible(candidate, target)

    target.parent.mkdir(parents=True, exist_ok=True)
    archive = target.parent / "champions"
    archive.mkdir(exist_ok=True)
    old_archive, new_archive = archive / f"{champion_hash}.pt", archive / f"{candidate_hash}.pt"
    if not old_archive.exists():
        shutil.copy2(target, old_archive)
    if not new_archive.exists():
        shutil.copy2(candidate, new_archive)
    manifest_path = target.parent / "champion.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = {"schema_version": 1, "updated_at": datetime.now(timezone.utc).isoformat(),
                "current": {"sha256": candidate_hash, "checkpoint": str(new_archive),
                            "evaluation": str(candidate_eval)},
                "previous": {"sha256": champion_hash, "checkpoint": str(old_archive),
                             "evaluation": str(champion_eval)},
                "decision": {"mode": "initial_champion_bootstrap" if initial_champion else "paired_challenger",
                             "paired_lift_lower_95": lift_lb, "minimum_lift": min_lift,
                             "candidate_bits_per_byte": c_metric, "champion_bits_per_byte": h_metric},
                "history": previous.get("history", []) + [{"at": datetime.now(timezone.utc).isoformat(),
                    "from": champion_hash, "to": candidate_hash, "reason": "reviewed evaluation gates passed"}]}
    install_checkpoint(target, new_archive, source_sha256=candidate_hash,
                       previous_sha256=champion_hash, previous_archive=old_archive,
                       manifest=manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-eval", type=Path, required=True)
    parser.add_argument("--champion-eval", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=Path("checkpoints/latest.pt"))
    parser.add_argument("--min-lift", type=float, default=0.02)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(promote(args.candidate, args.candidate_eval, args.champion_eval,
                                 args.target, min_lift=args.min_lift), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
