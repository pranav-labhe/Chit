import json
from pathlib import Path

import pytest

from pranav.chit.config import ConfigError, load_config
from pranav.chit.training import lr_at


def _write(tmp_path, raw):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(raw))
    return p


def test_repo_configs_load():
    root = Path(__file__).resolve().parents[1]
    for name in ("chit_tiny", "chit_cpu_learning", "chit_assistant_cpu"):
        load_config(root / "configs" / f"{name}.json")

    assistant = load_config(root / "configs" / "chit_assistant_cpu.json")
    assert assistant.model.block_size == 512
    assert assistant.model.n_layer > 2 and assistant.model.n_embd > 64
    assert Path(assistant.data.train_file).stat().st_size > assistant.model.block_size
    assert Path(assistant.data.eval_file).stat().st_size > assistant.model.block_size


def test_assistant_curriculum_covers_languages_and_holds_out_requests():
    root = Path(__file__).resolve().parents[1]
    train = (root / "data" / "train.txt").read_text(encoding="utf-8")
    evaluation = (root / "data" / "eval.txt").read_text(encoding="utf-8")
    assert "Translate into Hindi:" in train
    assert "Translate into Sanskrit:" in train
    assert "Translate into English:" in train

    def user_requests(text):
        return {line.removeprefix("User: ") for line in text.splitlines()
                if line.startswith("User: ")}

    train_requests = user_requests(train)
    eval_requests = user_requests(evaluation)
    assert len(train_requests) >= 30
    assert len(eval_requests) >= 5
    assert train_requests.isdisjoint(eval_requests)
    assert any(q.startswith("Translate into Hindi:") for q in eval_requests)
    assert any(q.startswith("Translate into Sanskrit:") for q in eval_requests)
    assert any(q.startswith("Translate into English:") for q in eval_requests)
    assert any("What is 45 divided by 5?" in q for q in eval_requests)  # held-out QA/reasoning
    assert any("Make this request more polite:" in q for q in eval_requests)  # instruction following
    assert any("describing a calm morning" in q for q in eval_requests)  # creative generation
    assert any("does not say how long" in q for q in eval_requests)  # abstention when evidence is missing
    assert "```text" in evaluation  # held-out Markdown code fence
    assert "## Goal\nPrepare dinner\n## Constraint" in evaluation  # Markdown structure
    assert "User: My bike tire is flat and I need to get to work." in train
    assert "User: I got this error in my Markdown report:" in train


@pytest.mark.parametrize("raw", [
    {"modle": {}},                                   # typo at top level
    {"training": {"max_step": 5}},                   # typo in a section
    {"model": {"n_embd": 30, "n_head": 4}},          # not divisible
    {"device": "tpu"},
    {"training": {"lr_schedule": "linear"}},
])
def test_invalid_configs_rejected(tmp_path, raw):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, raw))


def test_lr_schedule(tmp_path):
    c = load_config(_write(tmp_path, {"training": {"learning_rate": 1.0, "max_steps": 100, "warmup_steps": 10,
                                                   "lr_schedule": "cosine", "min_lr_ratio": 0.1}}))
    assert lr_at(5, c) == pytest.approx(0.5)
    assert lr_at(10, c) == pytest.approx(1.0)
    assert lr_at(100, c) == pytest.approx(0.1)
