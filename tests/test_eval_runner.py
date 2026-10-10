import pytest

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
