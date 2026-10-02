import json

import torch

from conftest import H, TINY, install_candidate_for_test, train_body, wait_job
from pranav.chit import api

TRAIN = {"max_steps": 6, "batch_size": 2, "eval_interval": 3, "eval_steps": 1, "checkpoint_interval": 3}
QA = {"kind": "qa", "question": "What is the return window?", "answer": "30 days.", "tags": ["returns"]}
FACT = {"kind": "text", "text": "Orders over 500 rupees ship free.", "tags": ["shipping"], "remember": True}


def teach(client, *items):
    r = client.post("/knowledge", json={"items": list(items)}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


def ktrain(client, **extra):
    return client.post("/knowledge/train", json={"config": "test", "model": TINY, "training": TRAIN, **extra},
                       headers=H)


def test_teach_list_get_delete(client):
    out = teach(client, QA, FACT)
    assert out["created"] == 2 and out["duplicates"] == 0
    assert teach(client, QA)["duplicates"] == 1                     # same content is stored once

    listing = client.get("/knowledge", params={"tag": "returns"}, headers=H).json()
    assert listing["total"] == 1 and listing["items"][0]["payload"]["answer"] == "30 days."
    assert client.get("/knowledge/stats", headers=H).json()["by_status"] == {"pending": 2, "trained": 0}

    entry_id = out["items"][0]["id"]
    assert client.get(f"/knowledge/{entry_id}", headers=H).json()["kind"] == "qa"
    assert client.delete(f"/knowledge/{entry_id}", headers=H).status_code == 204
    assert client.get(f"/knowledge/{entry_id}", headers=H).status_code == 404


def test_remember_makes_knowledge_usable_before_training(client):
    out = teach(client, FACT)
    assert out["items"][0]["memory_id"]
    hits = client.get("/memory/search", params={"q": "free shipping orders"}, headers=H).json()["results"]
    assert hits and hits[0]["source"] == f"knowledge:{out['items'][0]['id']}"


def test_invalid_knowledge_rejected(client):
    bad = [
        {"items": []},
        {"items": [{"kind": "qa", "question": "q"}]},
        {"items": [{"kind": "poem", "text": "x"}]},
        {"items": [{"kind": "text", "text": "x", "surprise": 1}]},
        {"items": [{"kind": "text", "text": "x", "tags": ["has space"]}]},
    ]
    for payload in bad:
        assert client.post("/knowledge", json=payload, headers=H).status_code == 422, payload


def test_knowledge_requires_auth(client):
    assert client.post("/knowledge", json={"items": [FACT]}).status_code == 401
    assert client.get("/knowledge").status_code == 401
    assert client.post("/knowledge/train", json={}).status_code == 401


def test_train_on_knowledge_keeps_entries_pending_until_promotion(client):
    ids = [i["id"] for i in teach(client, QA, FACT)["items"]]
    r = ktrain(client)
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["id"])
    assert job["state"] == "succeeded" and not job["promoted"], job
    assert job["init_checkpoint"] is None                          # nothing was served: auto -> scratch

    meta = job["metadata"]["knowledge"]
    assert meta["entries"] == 2
    manifest = json.loads(open(meta["manifest"], encoding="utf-8").read())
    assert sorted(manifest["entry_ids"]) == sorted(ids)
    train_text = open(job["config"]["data"]["train_file"], encoding="utf-8").read()
    assert train_text.count("User: What is the return window?\nChit: 30 days.\n") == 3   # repeat=3

    for i in ids:
        e = client.get(f"/knowledge/{i}", headers=H).json()
        assert e["status"] == "pending" and e["trained_job_id"] is None
    ck = torch.load(job["checkpoint"], weights_only=True)
    assert ck["metadata"]["knowledge"]["dataset_sha256"] == meta["dataset_sha256"]
    assert client.get("/knowledge/stats", headers=H).json()["by_status"]["pending"] == 2


def test_second_run_fine_tunes_the_served_model(client):
    teach(client, QA)
    first = wait_job(client, ktrain(client).json()["id"])
    install_candidate_for_test(first)
    teach(client, FACT)
    r = ktrain(client, select="pending", model={})           # no overrides: use served architecture
    second = wait_job(client, r.json()["id"])
    assert second["state"] == "succeeded", second
    assert second["init_checkpoint"].endswith("init.pt")
    assert second["metadata"]["knowledge"]["entries"] == 2   # neither item is trained before promotion
    ck = torch.load(second["checkpoint"], weights_only=True)
    assert ck["total_steps"] == 12 and ck["step"] == 6        # continued from the first run
    assert first["id"] != second["id"]


def test_init_current_cannot_change_architecture(client):
    teach(client, QA)
    first = wait_job(client, ktrain(client).json()["id"])
    install_candidate_for_test(first)
    r = ktrain(client, init="current", model={"n_layer": 3})
    assert r.status_code == 422 and "architecture" in r.text


def test_init_current_without_served_model(client):
    teach(client, QA)
    assert ktrain(client, init="current").status_code == 422


def test_not_promoted_leaves_entries_pending(client):
    teach(client, QA)
    job = wait_job(client, ktrain(client, promote=False).json()["id"])
    assert job["state"] == "succeeded" and not job["promoted"]
    assert client.get("/knowledge/stats", headers=H).json()["by_status"]["pending"] == 1


def test_nothing_to_train(client):
    assert ktrain(client).status_code == 422
    teach(client, QA)
    first = wait_job(client, ktrain(client).json()["id"])
    assert not first["promoted"]
    assert ktrain(client, select="pending").status_code == 202  # candidate is pending promotion


def test_knowledge_train_conflicts_with_active_job(client):
    teach(client, QA)
    active = client.post("/train", json=train_body(max_steps=100_000, checkpoint_interval=1000), headers=H).json()
    r = ktrain(client)
    assert r.status_code == 409 and r.json()["detail"]["active_job"] == active["id"]
    client.post(f"/train/{active['id']}/cancel", headers=H)
    wait_job(client, active["id"])


def test_memory_works_without_a_model(client):
    assert client.get("/health").json()["model_loaded"] is False
    assert client.post("/memory", json={"content": "Pranav likes chai."}, headers=H).status_code == 201
    assert client.get("/memory/search", params={"q": "chai"}, headers=H).json()["results"]


def test_job_history_survives_restart(client, tmp_path):
    teach(client, QA)
    job = wait_job(client, ktrain(client).json()["id"])
    from pranav.chit.jobs import TrainingJobManager
    reloaded = TrainingJobManager(api.JOBS_DIR)
    assert reloaded.get(job["id"])["state"] == "succeeded"


def test_interrupted_job_is_marked_failed_on_restart(tmp_path):
    from pranav.chit.jobs import TrainingJobManager
    d = tmp_path / "jobs" / "abc"
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({"id": "abc", "state": "running", "max_steps": 10,
                                            "created_at": "2026-01-01T00:00:00+00:00"}))
    job = TrainingJobManager(tmp_path / "jobs").get("abc")
    assert job["state"] == "failed" and "interrupted" in job["error"]
    assert json.loads((d / "job.json").read_text())["state"] == "failed"
