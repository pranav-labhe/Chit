"""Shared fixtures: an isolated API instance with tiny data and configs."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from pranav.chit import api

KEY = "test-key"
H = {"X-API-Key": KEY}
TINY = {"block_size": 16, "n_layer": 1, "n_head": 2, "n_embd": 16}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CHECKPOINT", str(tmp_path / "served" / "latest.pt"))
    monkeypatch.setattr(api, "JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr(api, "API_KEY", KEY)
    monkeypatch.setattr(api, "ALLOW_UNAUTHENTICATED_TRAINING", False)
    monkeypatch.setattr(api, "MEMORY_PATH", str(tmp_path / "data" / "memory.json"))
    monkeypatch.setattr(api, "KNOWLEDGE_DB", str(tmp_path / "data" / "knowledge.db"))
    monkeypatch.chdir(tmp_path)
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / "train.txt").write_text("Chit learns from examples. " * 20, encoding="utf-8")
    (data / "eval.txt").write_text("Atmini observes and remembers. " * 5, encoding="utf-8")
    (cfg_dir / "test.json").write_text(json.dumps({
        "device": "cpu",
        "data": {"train_file": str(data / "train.txt"), "eval_file": str(data / "eval.txt")},
    }), encoding="utf-8")
    monkeypatch.setattr(api, "CONFIG_DIR", str(cfg_dir))
    with TestClient(api.app) as c:
        yield c


def wait_job(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/train/{job_id}", headers=H).json()
        if job["state"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def train_body(**training):
    return {"config": "test", "model": TINY,
            "training": {"max_steps": 6, "batch_size": 2, "eval_interval": 3,
                         "eval_steps": 1, "checkpoint_interval": 3, **training}}

