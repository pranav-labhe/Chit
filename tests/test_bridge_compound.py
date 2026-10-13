"""Unit and integration tests for Chit Bridge compound pipeline architecture."""
from dataclasses import asdict
from pathlib import Path

import pytest
from pranav.chit.bridge import Bridge, BridgeConfig, Context, Plan, Router, ContextBuilder, Generator, Verifier
from pranav.chit.tokenizer import ByteTokenizer
from pranav.chit.tools.calculator import try_calculate
from pranav.chit.tools.calibrate_confidence import calibrate, fit_isotonic_regression


class MockRuntime:
    def __init__(self, responses=None, block_size=256):
        self.tokenizer = ByteTokenizer()
        self.model_config = {"block_size": block_size}
        self.responses = responses or ["Mock output"]
        self.history = []

    def recall(self, query, k, min_relevance=0.0):
        return []

    def generate(self, prompt, n_tokens, temp, top_k, stop=None, return_details=False):
        self.history.append({"prompt": prompt, "temp": temp, "top_k": top_k, "stop": stop})
        resp = self.responses.pop(0) if self.responses else "Default"
        if return_details:
            return resp, 0.88, "stop"
        return resp


def test_bridge_config_defaults_and_overrides():
    config = BridgeConfig()
    assert config.enable_calculator is True
    assert config.legacy_attractor_shim is True
    assert config.reserve_generation_budget is True
    assert config.enable_generic_verifier is False
    assert config.enable_calibration is False
    assert config.default_temperature == 0.7
    assert config.open_chat_top_k == 20

    custom = BridgeConfig(enable_calculator=False, default_temperature=0.2)
    assert custom.enable_calculator is False
    assert custom.default_temperature == 0.2


def test_router_generates_typed_plan():
    router = Router()
    config = BridgeConfig()

    # Continue plan
    p_cont = router.route(Context(user_input="text", task="continue"), config)
    assert isinstance(p_cont, Plan)
    assert p_cont.intent == "continue"
    assert p_cont.strategy == "direct"

    # Math plan
    p_math = router.route(Context(user_input="What is 15 + 27?"), config)
    assert p_math.intent == "math"
    assert p_math.strategy == "tool"
    assert p_math.decoding["top_k"] == 1

    # Search plan
    p_search = router.route(Context(user_input="Latest news", search=True), config)
    assert p_search.intent == "lookup"
    assert p_search.strategy == "search"
    assert p_search.decoding["temperature"] == 0.0

    # Thinking plan
    p_think = router.route(Context(user_input="Analyze this", think=True), config)
    assert p_think.intent == "think"
    assert p_think.strategy == "think"


def test_context_builder_budgeting():
    cb = ContextBuilder()
    config = BridgeConfig(reserve_generation_budget=True)

    # Context block >= 256 receives reserve
    max_p, reserve = cb.compute_budget(256, 128, config, is_thinking=False)
    assert reserve == min(128, max(32, min(96, int(256 * 0.4))))
    assert max_p == 256 - reserve
    assert max_p + reserve == 256

    # When reserve disabled
    config_no_res = BridgeConfig(reserve_generation_budget=False)
    max_p_no, res_no = cb.compute_budget(256, 128, config_no_res, is_thinking=False)
    assert res_no == 0
    assert max_p_no == 256


def test_calculator_tool_exact_and_safety():
    assert try_calculate("14 + 28") == "42"
    assert try_calculate("What is 100 - 37?") == "63"
    assert try_calculate("6 * 7") == "42"
    assert try_calculate("48 / 6") == "8"
    assert try_calculate("12 plus 15") == "27"
    assert try_calculate("50 minus 18") == "32"
    assert try_calculate("7 times 8") == "56"
    assert try_calculate("72 divided by 9") == "8"
    assert try_calculate("(14 + 28)") == "42"
    assert try_calculate("((100 - 37))") == "63"

    # Safety guards
    assert try_calculate("10 / 0") == "Error: Division by zero is undefined."
    assert try_calculate("v1.2.3") is None  # Version rejected
    assert try_calculate("2026-10-12") is None  # Date rejected
    assert try_calculate("if 2 + 2 was 5") is None  # Hypothetical rejected
    assert try_calculate("10000000000 + 1") is None  # Overflow rejected


def test_bridge_calculator_execution_and_metadata():
    rt = MockRuntime()
    bridge = Bridge(rt)

    decision = bridge.process(Context(user_input="What is 25 * 4?"))
    assert decision.text == "100"
    assert decision.confidence is None
    assert decision.metadata["source"] == "tool"
    assert decision.metadata["plan"]["intent"] == "math"
    assert len(rt.history) == 0  # Zero neural inference calls


def test_verifier_generic_invariants():
    v = Verifier()
    config = BridgeConfig(enable_generic_verifier=True)

    # Empty
    is_valid, viol = v.verify("", "q", "", "stop", config)
    assert not is_valid
    assert "is_empty" in viol

    # Repetitive
    loop_text = "the word the word the word the word the word"
    is_valid, viol = v.verify(loop_text, "q", "", "stop", config)
    assert not is_valid
    assert "is_repetitive" in viol

    # Replacement character
    bad_utf8 = "bad \ufffd char"
    is_valid, viol = v.verify(bad_utf8, "q", "", "stop", config)
    assert not is_valid
    assert "has_replacement_char" in viol

    # Disjoint from premise
    is_valid, viol = v.verify("totally unrelated astronomy", "what is photosynthesis", "plants convert sunlight", "stop", config)
    assert not is_valid
    assert "is_disjoint_from_evidence" in viol

    # Valid grounded response
    is_valid, viol = v.verify("plants convert sunlight to energy", "what is photosynthesis", "plants convert sunlight", "stop", config)
    assert is_valid
    assert viol == []


def test_confidence_calibration():
    # Fit simple isotonic regression
    x = [0.1, 0.4, 0.6, 0.9]
    y = [0.0, 0.0, 1.0, 1.0]
    mapping = fit_isotonic_regression(x, y)
    assert len(mapping) >= 2

    # Calibrate interpolation
    assert calibrate(0.1, mapping) <= 0.1
    assert calibrate(0.9, mapping) >= 0.8
    assert calibrate(0.5, None) == 0.5


def test_ablation_toggles():
    rt = MockRuntime(["Neural math answer"])
    # Disable calculator: falls back to neural execution
    config_no_calc = BridgeConfig(enable_calculator=False)
    bridge_no_calc = Bridge(rt, config=config_no_calc)

    decision = bridge_no_calc.process(Context(user_input="What is 5 + 5?"))
    assert decision.text == "Neural math answer"
    assert decision.metadata["source"] == "neural"
    assert len(rt.history) == 1


def test_candidate_benchmark_and_calibration_lifecycle(tmp_path, monkeypatch):
    import asyncio
    import json
    from pranav.chit import api

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "test_candidate_123"
    job_folder = jobs_dir / job_id
    job_folder.mkdir()

    # Create dummy job.json and checkpoint
    (job_folder / "job.json").write_text(json.dumps({"state": "succeeded"}), encoding="utf-8")
    (job_folder / "latest.pt").write_text("dummy checkpoint", encoding="utf-8")

    dummy_bench = {
        "status": "completed",
        "arithmetic_exact_match": 1.0,
        "expected_calibration_error": 0.22,
        "p95_latency_ms": 15000.0,
        "truncated_before_stop_rate": 0.15,
        "loop_rate": 0.0,
    }
    (job_folder / "bridge_benchmark.json").write_text(json.dumps(dummy_bench), encoding="utf-8")

    monkeypatch.setattr(api, "JOBS_DIR", str(jobs_dir))

    res = asyncio.run(api.list_candidates())
    assert len(res["candidates"]) == 1
    cand = res["candidates"][0]
    assert cand["job_id"] == job_id
    assert cand["bridge_benchmark"] == dummy_bench
