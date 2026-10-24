import pytest

from conftest import H, train_body as body, wait_job as wait
from pranav.chit import api


def test_train_creates_candidate_without_serving_it(client):
    assert client.get("/health").json()["model_loaded"] is False
    assert client.get("/ready", headers=H).status_code == 503
    r = client.post("/train", json=body(), headers=H)
    assert r.status_code == 202
    assert r.headers["Location"] == f"/train/{r.json()['id']}"

    job = wait(client, r.json()["id"])
    assert job["state"] == "succeeded", job["error"]
    assert job["step"] == 6 and job["progress"] == 1.0
    assert job["promoted"] is False
    assert len(job["evaluations"]) == 2
    assert job["final_evaluation"].endswith("evaluation.json")
    assert [p["step"] for p in job["history"]] == [1, 3, 6]

    assert client.get("/health").json()["model_loaded"] is False
    assert client.get("/ready", headers=H).status_code == 503
    assert client.post("/generate", json={"prompt": "Chit", "tokens": 5}, headers=H).status_code == 503
    assert job["id"] in [j["id"] for j in client.get("/train", headers=H).json()["jobs"]]


def test_unevaluated_direct_promotion_is_rejected(client):
    r = client.post("/train", json={**body(), "promote": True}, headers=H)
    assert r.status_code == 422 and "reviewed gates" in r.text


def test_promote_false_keeps_served_model(client):
    job = wait(client, client.post("/train", json={**body(), "promote": False}, headers=H).json()["id"])
    assert job["state"] == "succeeded" and job["promoted"] is False
    assert client.get("/health").json()["model_loaded"] is False


def test_cancel_and_single_active_job(client):
    first = client.post("/train", json=body(max_steps=100_000, checkpoint_interval=1000), headers=H).json()
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


@pytest.mark.parametrize("method,path,kwargs", [
    ("GET", "/candidates", {}),
    ("POST", "/candidates/0123456789abcdef0123456789abcdef/evaluate", {}),
    ("POST", "/candidates/0123456789abcdef0123456789abcdef/benchmark", {}),
    ("POST", "/candidates/0123456789abcdef0123456789abcdef/promote", {}),
    ("POST", "/admin/rollback", {"params": {"to_sha256": "dummy"}}),
    ("POST", "/admin/reload", {}),
    ("POST", "/train/tokenizer", {"json": {"config": "test"}}),
])
def test_candidate_and_admin_endpoints_require_auth(client, monkeypatch, method, path, kwargs):
    # Missing API key -> 401
    assert client.request(method, path, **kwargs).status_code == 401
    # Invalid API key -> 401
    assert client.request(method, path, headers={"X-API-Key": "wrong"}, **kwargs).status_code == 401
    # Unconfigured API key and ALLOW_UNAUTHENTICATED_TRAINING=False -> 403
    monkeypatch.setattr(api, "API_KEY", None)
    assert client.request(method, path, **kwargs).status_code == 403

    # Authenticated request with valid key passes auth check
    monkeypatch.setattr(api, "API_KEY", api.API_KEY or "test-key")
    from conftest import H
    res_auth = client.request(method, path, headers=H, **kwargs)
    assert res_auth.status_code not in (401, 403)


def test_train_tokenizer_and_bpe_training_flow(client, tmp_path):
    import json
    from pathlib import Path

    pytest.importorskip("tokenizers")
    data = tmp_path / "data"
    s1 = data / "source1.txt"
    s2 = data / "source2.txt"
    ev = data / "eval_bpe.txt"
    s1.write_text("Chit neural brain reasoning and dialogue. " * 30, encoding="utf-8")
    s2.write_text("Atmini cognitive architecture and memory stream. " * 30, encoding="utf-8")
    ev.write_text("Evaluation held out text tokens. " * 10, encoding="utf-8")

    cfg_dir = Path(api.CONFIG_DIR)
    tok_target = tmp_path / "custom_tok" / "bpe.json"

    bpe_cfg = {
        "device": "cpu",
        "model": {"vocab_size": 300, "block_size": 16, "n_layer": 1, "n_head": 2, "n_embd": 16},
        "training": {"max_steps": 2, "batch_size": 2, "eval_interval": 1, "eval_steps": 1, "checkpoint_interval": 1},
        "data": {
            "train_file": str(s1),
            "eval_file": str(ev),
            "sources": [
                {"path": str(s1), "weight": 0.5},
                {"path": str(s2), "weight": 0.5},
            ],
        },
        "tokenizer": {
            "name": "bpe-tokenizers-json-v1",
            "model_file": str(tok_target),
        },
    }
    (cfg_dir / "bpe_test.json").write_text(json.dumps(bpe_cfg), encoding="utf-8")

    # 1. Before training tokenizer, start_training should fail validate_config because tokenizer is unusable
    r_fail = client.post("/train", json={"config": "bpe_test"}, headers=H)
    assert r_fail.status_code == 422
    assert "tokenizer configuration is unusable" in r_fail.text

    # 2. Call POST /train/tokenizer
    res = client.post("/train/tokenizer", json={"config": "bpe_test", "vocab_size": 300}, headers=H)
    assert res.status_code == 200
    data_res = res.json()
    assert data_res["status"] == "created"
    assert data_res["config"] == "bpe_test"
    assert data_res["vocab_size"] == 300
    assert data_res["path"] == str(tok_target)
    sidecar = Path(api.CHECKPOINT).parent / "tokenizer.json"
    assert data_res["latest_sidecar_path"] == str(sidecar)
    assert len(data_res["checkpoint_asset_sha256"]) == 64
    assert str(s1) in data_res["files_used"]
    assert str(s2) in data_res["files_used"]
    assert str(ev) not in data_res["files_used"]
    assert tok_target.is_file()
    assert sidecar.is_file()
    assert tok_target.read_text(encoding="utf-8") == sidecar.read_text(encoding="utf-8")

    # 3. overwrite=False returns 409
    res_conflict = client.post("/train/tokenizer", json={"config": "bpe_test", "overwrite": False}, headers=H)
    assert res_conflict.status_code == 409
    assert "already exists" in res_conflict.json()["detail"]

    # 4. Now validate_config succeeds and POST /train starts cleanly
    r_train = client.post("/train", json={"config": "bpe_test"}, headers=H)
    assert r_train.status_code == 202


def test_train_tokenizer_missing_source_file(client, tmp_path):
    import json
    from pathlib import Path

    cfg_dir = Path(api.CONFIG_DIR)
    bpe_cfg = {
        "device": "cpu",
        "data": {
            "train_file": str(tmp_path / "data" / "train.txt"),
            "eval_file": str(tmp_path / "data" / "eval.txt"),
            "sources": [
                {"path": str(tmp_path / "data" / "missing.txt"), "weight": 1.0},
            ],
        },
        "tokenizer": {
            "name": "bpe-tokenizers-json-v1",
            "model_file": str(tmp_path / "tok.json"),
        },
    }
    (cfg_dir / "missing_source.json").write_text(json.dumps(bpe_cfg), encoding="utf-8")
    res = client.post("/train/tokenizer", json={"config": "missing_source"}, headers=H)
    assert res.status_code == 422
    assert "not found on server" in res.text


def test_maintenance_lock_endpoints_and_owner_reporting(client):
    lock_file = api.SYNC_LOCK_PATH
    try:
        # 1. Lock with owner ID on disk
        lock_file.write_text("gha-run-42-1-xyz\n", encoding="utf-8")

        for url, payload in [
            ("/train", body()),
            ("/train/tokenizer", {"config": "bpe_test"}),
            ("/knowledge/train", {"select": "all"}),
            ("/data/split", {"source": "train.txt", "config": "test"}),
        ]:
            res = client.post(url, json=payload, headers=H)
            assert res.status_code == 423, f"{url} expected 423 Locked, got {res.status_code}"
            detail = res.json()["detail"]
            assert detail["lock_owner"] == "gha-run-42-1-xyz"
            assert detail["lock_path"] == str(lock_file)
            assert "maintenance" in detail["message"].lower()

        # 2. Bounded lock owner length
        lock_file.write_text("X" * 500, encoding="utf-8")
        res = client.post("/train", json=body(), headers=H)
        assert res.status_code == 423
        assert len(res.json()["detail"]["lock_owner"]) == 256

        # 3. Empty lock file reports lock_owner=None
        lock_file.write_text("   \n", encoding="utf-8")
        res = client.post("/train", json=body(), headers=H)
        assert res.status_code == 423
        assert res.json()["detail"]["lock_owner"] is None

        # 4. Unlocked state restores normal operation
        lock_file.unlink()
        res = client.post("/train", json=body(), headers=H)
        assert res.status_code == 202
    finally:
        if lock_file.exists():
            lock_file.unlink()

