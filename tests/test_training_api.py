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
    monkeypatch.chdir(tmp_path)  # the runtime's MemoryStore writes data/memory.json relative to cwd
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


def wait(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/train/{job_id}", headers=H).json()
        if job["state"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def body(**training):
    return {"config": "test", "model": TINY,
            "training": {"max_steps": 6, "batch_size": 2, "eval_interval": 3,
                         "eval_steps": 1, "checkpoint_interval": 3, **training}}


def test_train_promotes_and_serves_new_model(client):
    assert client.get("/health").json()["model_loaded"] is False
    r = client.post("/train", json=body(), headers=H)
    assert r.status_code == 202
    assert r.headers["Location"] == f"/train/{r.json()['id']}"

    job = wait(client, r.json()["id"])
    assert job["state"] == "succeeded", job["error"]
    assert job["step"] == 6 and job["progress"] == 1.0
    assert job["promoted"] is True
    assert [p["step"] for p in job["history"]] == [1, 3, 6]

    assert client.get("/health").json()["model_loaded"] is True
    g = client.post("/generate", json={"prompt": "Chit", "tokens": 5}, headers=H)
    assert g.status_code == 200
    assert job["id"] in [j["id"] for j in client.get("/train", headers=H).json()["jobs"]]


def test_promote_false_keeps_served_model(client):
    job = wait(client, client.post("/train", json={**body(), "promote": False}, headers=H).json()["id"])
    assert job["state"] == "succeeded" and job["promoted"] is False
    assert client.get("/health").json()["model_loaded"] is False


def test_cancel_and_single_active_job(client):
    first = client.post("/train", json=body(max_steps=100_000), headers=H).json()
    second = client.post("/train", json=body(), headers=H)
    assert second.status_code == 409
    assert second.json()["detail"]["active_job"] == first["id"]

    assert client.post(f"/train/{first['id']}/cancel", headers=H).status_code == 202
    job = wait(client, first["id"])
    assert job["state"] == "cancelled" and job["promoted"] is False
    assert client.post(f"/train/{first['id']}/cancel", headers=H).status_code == 409
    assert client.get("/health").json()["model_loaded"] is False  # served model untouched


@pytest.mark.parametrize("payload", [
    {"config": "test", "model": {"n_embd": 30, "n_head": 4}},     # not divisible
    {"config": "test", "training": {"max_steps": 10**9}},          # over the cap
    {"config": "test", "model": {"block_size": 2048}},             # larger than the data
    {"config": "test", "training": {"learning_rate": -1}},         # out of range
    {"config": "test", "unknown": 1},                              # extra field
    {"config": "../configs/test"},                                 # path traversal
])
def test_invalid_requests_rejected(client, payload):
    assert client.post("/train", json=payload, headers=H).status_code == 422


def test_unknown_config_and_job(client):
    assert client.post("/train", json={"config": "nope"}, headers=H).status_code == 404
    assert client.get("/train/does-not-exist", headers=H).status_code == 404
    assert client.get("/train/configs", headers=H).json() == {"configs": ["test"]}


def test_training_requires_auth(client, monkeypatch):
    assert client.post("/train", json=body()).status_code == 401
    assert client.post("/train", json=body(), headers={"X-API-Key": "wrong"}).status_code == 401
    monkeypatch.setattr(api, "API_KEY", None)
    assert client.post("/train", json=body()).status_code == 403  # no key configured -> disabled
