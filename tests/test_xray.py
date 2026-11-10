"""Tests for the Brain X-Ray inspection engine, API endpoints, and standalone Canvas UI."""
from __future__ import annotations

import httpx
import pytest
import torch
from fastapi.testclient import TestClient

from pranav.chit import api, ui
from pranav.chit.bridge import Bridge, BridgeConfig
from pranav.chit.model import ChitModel
from pranav.chit.runtime import ChitRuntime
from pranav.chit.tokenizer import ByteTokenizer
from pranav.chit.xray import (
    _check_text_integrity,
    _grade_pathway,
    build_brain_xray,
    clear_xray_cache,
    probe_brain,
)


def _tiny_runtime(block_size: int = 64) -> ChitRuntime:
    cfg = {
        "vocab_size": 256,
        "block_size": block_size,
        "n_layer": 2,
        "n_head": 2,
        "n_embd": 32,
        "dropout": 0.0,
        "position_encoding": "rope",
        "rope_theta": 10000.0,
    }
    model = ChitModel(**cfg)
    rt = ChitRuntime(
        model,
        device="cpu",
        model_config=cfg,
        checkpoint_meta={
            "step": 500,
            "total_steps": 500,
            "best_eval_loss": 6.15,
            "last_eval": {"step": 500, "train_loss": 0.16, "eval_loss": 6.15},
        },
    )
    rt.tokenizer = ByteTokenizer()
    return rt


def test_text_integrity_and_pathway_grading_catches_real_subword_salad():
    clear_xray_cache()
    # Real scrambled responses observed from undertrained/overfitted checkpoints must never pass
    for bad in (
        "",
        "the the the the",
        "bad \ufffd char",
        "Yes—a long separate emailsion—such asparentarent shift",
        "LinuxG permpty (such as an bisrencCPOST /mps/backup, ,rencync returning systemd)",
        "Go with folders and carry a coffee at high-connections canved two heavy cars couter",
    ):
        sane, _ = _check_text_integrity(bad)
        assert not sane, f"Expected broken integrity for: {bad!r}"

    status_leak, _, reason_leak = _grade_pathway(
        "Use ensure means baskets capaces (deposities fewer errors) and lower-volume.",
        0.55,
        ("weights", "sqlite", "memory", "database"),
        ("ensure", "baskets", "kiln"),
    )
    assert status_leak == "broken"
    assert reason_leak

    status_ok, score_ok, _ = _grade_pathway(
        "Chit is the neural language model layer inside Atmini, while Atmini is the broader system.",
        0.82,
        ("atmini", "model", "layer", "neural"),
        ("kiln", "baskets"),
    )
    assert status_ok == "healthy"
    assert score_ok >= 0.72


def test_build_brain_xray_handles_small_block_size_and_exposes_overfitting():
    clear_xray_cache()
    rt = _tiny_runtime(block_size=64)
    xray = build_brain_xray(rt)

    assert len(xray["lobes"]) == 6
    assert len(xray["pathways"]) == 18
    assert len(xray["synapses"]) > 0
    assert xray["checkpoint"]["overfit_warning"] is not None
    assert xray["completeness_pct"] <= 45
    assert "_internal_vectors" not in xray

    # Second call uses cache and still strips internal tensors cleanly
    xray_cached = build_brain_xray(rt)
    assert "_internal_vectors" not in xray_cached
    assert xray_cached["completeness_pct"] == xray["completeness_pct"]


def test_probe_brain_detects_broken_weights_vs_clean_weights(monkeypatch):
    clear_xray_cache()
    rt = _tiny_runtime(block_size=128)
    bridge = Bridge(rt, config=BridgeConfig(enable_calibration=False))

    # Case 1: Weights themselves emit subword salad -> Brain + Chat both flagged misbehaving
    monkeypatch.setattr(
        rt,
        "generate",
        lambda *a, **kw: ("Go with folders canved couter sofact.", 0.65, "stop"),
    )
    probe_bad = probe_brain(rt, bridge, "What is deadlock in concurrent systems?", compare_chat=True)
    assert probe_bad["misbehaved"] is True
    assert probe_bad["raw_brain"]["status"] == "broken"
    assert len(probe_bad["layer_activity"]) == 2
    assert len(probe_bad["activated_pathways"]) >= 1

    # Case 2: Weights answer cleanly on-topic with high confidence -> healthy
    monkeypatch.setattr(
        rt,
        "generate",
        lambda *a, **kw: (
            "Deadlock occurs when threads wait forever for locks held by each other.",
            0.84,
            "stop",
        ),
    )
    probe_good = probe_brain(rt, bridge, "What is deadlock in concurrent systems?", compare_chat=True)
    assert probe_good["misbehaved"] is False
    assert probe_good["raw_brain"]["status"] == "healthy"


def test_xray_api_endpoints_and_ui_inspector_route(tmp_path, monkeypatch):
    clear_xray_cache()
    rt = _tiny_runtime(block_size=128)
    bridge = Bridge(rt, config=BridgeConfig(enable_calibration=False))

    monkeypatch.setattr(api, "API_KEY", "secret-xray-key")
    monkeypatch.setattr(api, "CHECKPOINT", str(tmp_path / "missing.pt"))
    monkeypatch.setattr(api, "JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr(api, "MEMORY_DB", str(tmp_path / "memory.db"))
    monkeypatch.setattr(api, "MEMORY_PATH", str(tmp_path / "memory.json"))
    monkeypatch.setattr(api, "KNOWLEDGE_DB", str(tmp_path / "knowledge.db"))
    monkeypatch.setattr(api, "SESSIONS_DB", str(tmp_path / "sessions.db"))

    with TestClient(api.app) as client:
        monkeypatch.setitem(api._state, "runtime", rt)
        monkeypatch.setitem(api._state, "bridge", bridge)

        # Unauthenticated rejected
        assert client.get("/model/xray").status_code == 401
        assert client.post("/model/xray/probe", json={"prompt": "Hello"}).status_code == 401

        headers = {"X-API-Key": "secret-xray-key"}
        r_xray = client.get("/model/xray", headers=headers)
        assert r_xray.status_code == 200
        body = r_xray.json()
        assert len(body["lobes"]) == 6
        assert len(body["pathways"]) == 18

        r_probe = client.post("/model/xray/probe", headers=headers, json={"prompt": "What is deadlock?"})
        assert r_probe.status_code == 200
        p_body = r_probe.json()
        assert "raw_brain" in p_body
        assert "diagnosis" in p_body

    # UI separate /inspector HTML page & BASE_PATH=/console & proxy allowlist
    monkeypatch.setattr(ui, "BASE_PATH", "/console")
    monkeypatch.setattr(ui, "_new_http_client", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"completeness_pct": 25})),
        follow_redirects=False,
    ))
    with TestClient(ui.app, base_url="https://app.chitt.online") as uclient:
        page = uclient.get("/console/inspector")
        assert page.status_code == 200
        assert "brainCanvas" in page.text
        assert 'const BASE = "/console"' in page.text

        uclient.post("/console/_ui/login", json={"api_key": "secret-xray-key"},
                     headers={"Origin": "https://app.chitt.online"})
        proxied = uclient.post("/console/_ui/proxy", json={"method": "GET", "path": "/model/xray"})
        assert proxied.status_code == 200
        assert proxied.json() == {"completeness_pct": 25}
