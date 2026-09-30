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
    for name in ("chit_tiny", "chit_cpu_learning"):
        load_config(Path(__file__).resolve().parents[1] / "configs" / f"{name}.json")


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
