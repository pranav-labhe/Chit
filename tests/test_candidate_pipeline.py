from conftest import H, TINY, wait_job

TRAIN = {"max_steps": 6, "batch_size": 2, "eval_interval": 3, "eval_steps": 1, "checkpoint_interval": 3}


def test_knowledge_training_candidate_then_master_promote(client):
    teach = client.post(
        "/knowledge",
        json={"items": [{"kind": "qa", "question": "Who builds Chit?", "answer": "Pranav."}]},
        headers=H,
    )
    assert teach.status_code == 201
    entry_id = teach.json()["items"][0]["id"]

    started = client.post(
        "/knowledge/train",
        json={"config": "test", "model": TINY, "training": TRAIN, "promote": False},
        headers=H,
    )
    assert started.status_code == 202
    candidate = wait_job(client, started.json()["id"])
    assert candidate["state"] == "succeeded"
    assert candidate["promoted"] is False
    assert candidate["candidate_checkpoint"]
    assert client.get("/health").json()["model_loaded"] is False
    assert client.get(f"/knowledge/{entry_id}", headers=H).json()["status"] == "pending"

    promoted = client.post(f"/train/{candidate['id']}/promote", headers=H)
    assert promoted.status_code == 200
    assert promoted.json()["promoted"] is True
    assert client.get("/health").json()["model_loaded"] is True
    learned = client.get(f"/knowledge/{entry_id}", headers=H).json()
    assert learned["status"] == "trained"
    assert learned["trained_job_id"] == candidate["id"]
