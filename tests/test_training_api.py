import pytest

from conftest import H, train_body as body, wait_job as wait
from pranav.chit import api


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


def test_training_requests_keep_the_existing_default_preset():
    from pranav.chit.api import TrainRequest
    assert TrainRequest().config == "chit_cpu_learning"


def test_training_requires_auth(client, monkeypatch):
    assert client.post("/train", json=body()).status_code == 401
    assert client.post("/train", json=body(), headers={"X-API-Key": "wrong"}).status_code == 401
    monkeypatch.setattr(api, "API_KEY", None)
    assert client.post("/train", json=body()).status_code == 403  # no key configured -> disabled
