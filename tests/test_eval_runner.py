import json
import pytest

from pranav.chit.tools.auto_rate import auto_rate
from pranav.chit.tools.eval_runner import _golden_gate


def _payload():
    return {"cases": [
        {"id": "a", "category": "facts", "critical": True},
        {"id": "b", "category": "facts", "critical": False},
    ]}


def _ratings():
    return {"golden_set_sha256": "set-hash", "checkpoint_sha256": "checkpoint-hash",
            "ratings": [
                {"id": "a", "passed": True, "critical_failure": False, "reviewers": ["r1", "r2"]},
                {"id": "b", "passed": True, "critical_failure": False, "reviewers": ["r1", "r2"]},
            ]}


def test_behavior_gate_never_scores_context_truncated_or_unreviewed_cases(tmp_path):
    set_file = tmp_path / "set.json"
    set_file.write_text("{}", encoding="utf-8")
    ratings_file = tmp_path / "ratings.json"
    ratings_file.write_text(__import__("json").dumps(_ratings()), encoding="utf-8")
    outputs = [{"id": "a", "scorable": False}, {"id": "b", "scorable": True}]

    gate = _golden_gate(_payload(), outputs, None, "set-hash", "checkpoint-hash")

    assert gate["score"] is None
    assert gate["scorable_count"] == 1
    assert not gate["gate_pass"]


def test_behavior_gate_requires_all_cases_to_fit_and_pass_review(tmp_path):
    ratings_file = tmp_path / "ratings.json"
    ratings_file.write_text(__import__("json").dumps(_ratings()), encoding="utf-8")
    outputs = [{"id": "a", "scorable": True}, {"id": "b", "scorable": True}]

    gate = _golden_gate(_payload(), outputs, ratings_file, "set-hash", "checkpoint-hash")

    assert gate["score"] == {"passed": 2, "total": 2, "rate": 1.0}
    assert gate["gate_pass"]


def test_behavior_gate_rejects_mismatched_evaluation_hash(tmp_path):
    ratings = _ratings()
    ratings["golden_set_sha256"] = "wrong"
    ratings_file = tmp_path / "ratings.json"
    ratings_file.write_text(__import__("json").dumps(ratings), encoding="utf-8")

    with pytest.raises(ValueError, match="exact golden set and checkpoint hashes"):
        _golden_gate(_payload(), [{"id": "a", "scorable": True},
                                  {"id": "b", "scorable": True}], ratings_file,
                     "set-hash", "checkpoint-hash")


def test_auto_rate_execution_and_ratings_output(tmp_path):
    golden_file = tmp_path / "golden.json"
    golden_data = {
        "cases": [
            {"id": "c1", "must_include": ["paris"], "must_avoid": ["london"], "critical": False},
            {"id": "c2", "must_include": ["paris"], "must_avoid": ["rome"], "critical": False},
            {"id": "c3", "must_include": ["answer"], "must_avoid": [], "critical": True},
            {"id": "c4", "must_include": ["hello"], "must_avoid": [], "critical": False},
        ]
    }
    golden_file.write_text(json.dumps(golden_data), encoding="utf-8")

    eval_file = tmp_path / "eval.json"
    eval_data = {
        "golden_set_sha256": "golden-sha-123",
        "checkpoint_sha256": "ckpt-sha-456",
        "golden_outputs": [
            # c1: scorable with 'response' key, passes must_include, avoids must_avoid -> passes
            {"id": "c1", "response": "The city is Paris.", "scorable": True},
            # c2: scorable with 'response' key, violates must_include (contains london not paris) -> fails
            {"id": "c2", "response": "The city is London.", "scorable": True},
            # c3: unscorable prompt with response=None, critical -> fails safely without AttributeError, marked critical_failure
            {"id": "c3", "response": None, "scorable": False},
            # c4: legacy 'output' key compatibility -> passes
            {"id": "c4", "output": "Hello world", "scorable": True},
        ]
    }
    eval_file.write_text(json.dumps(eval_data), encoding="utf-8")

    out_file = tmp_path / "ratings.json"
    result_path = auto_rate(golden_file, eval_file, out_file)
    assert result_path == out_file
    assert out_file.is_file()

    ratings_content = json.loads(out_file.read_text(encoding="utf-8"))
    assert ratings_content["golden_set_sha256"] == "golden-sha-123"
    assert ratings_content["checkpoint_sha256"] == "ckpt-sha-456"

    by_id = {r["id"]: r for r in ratings_content["ratings"]}
    assert len(by_id) == 4

    # c1 passed
    assert by_id["c1"]["passed"] is True
    assert by_id["c1"]["critical_failure"] is False
    assert len(by_id["c1"]["reviewers"]) == 2

    # c2 failed
    assert by_id["c2"]["passed"] is False
    assert by_id["c2"]["critical_failure"] is False

    # c3 failed safely with critical_failure
    assert by_id["c3"]["passed"] is False
    assert by_id["c3"]["critical_failure"] is True

    # c4 legacy 'output' key passed
    assert by_id["c4"]["passed"] is True
    assert by_id["c4"]["critical_failure"] is False
