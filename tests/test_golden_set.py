import json
from collections import Counter
from pathlib import Path


def test_golden_set_has_balanced_frozen_cases():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "data/golden_set.json").read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["version"] == 1
    assert len(cases) == 50
    assert len({case["id"] for case in cases}) == 50
    assert Counter(case["category"] for case in cases) == {
        "core_facts": 10,
        "practical_help": 10,
        "instruction_following": 10,
        "honesty_safety": 10,
        "context_tracking": 10,
    }
    assert sum(case["critical"] for case in cases) == 18
    assert all(case["prompt"].strip() and case["reference"].strip()
               and case["must_include"] for case in cases)


def test_golden_prompts_are_not_exact_training_or_eval_lines():
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / "data/golden_set.json").read_text(encoding="utf-8"))["cases"]
    training_and_eval = {
        line.strip()
        for path in (root / "data/train.txt", root / "data/eval.txt")
        for line in path.read_text(encoding="utf-8").splitlines()
    }

    assert not any(case["prompt"] in training_and_eval for case in cases)
