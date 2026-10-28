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
    assert config.enable_generic_verifier is True
    assert config.enable_calibration is True
    assert config.best_of_n == 3
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
    assert p_cont.effective_task == "continue"

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
    assert p_search.effective_task == "knowledge"

    # Thinking plan
    p_think = router.route(Context(user_input="Analyze this", think=True), config)
    assert p_think.intent == "think"
    assert p_think.strategy == "think"
    assert p_think.effective_task == "reasoning"

    # Behavior & Grammar & Explicit task routing
    p_beh = router.route(Context(user_input="You do not have the evidence to answer. What should you do?"), config)
    assert p_beh.effective_task == "behavior"
    p_gram = router.route(Context(user_input="Rewrite this sentence in the past tense."), config)
    assert p_gram.effective_task == "grammar"
    p_explicit = router.route(Context(user_input="Hello", task="prose"), config)
    assert p_explicit.effective_task == "prose"


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


def test_best_of_3_candidate_selection():
    class MultiCandidateRuntime(MockRuntime):
        def __init__(self):
            super().__init__()
            self.items = [
                ("the the the the", 0.90, "stop"),  # Primary fails loop check
                ("Unrelated statement.", 0.70, "stop"),  # Cand 2 valid, low overlap
                ("Photosynthesis converts sunlight into energy.", 0.75, "stop"),  # Cand 3 valid, high overlap + conf
            ]

        def generate(self, prompt, n_tokens, temp, top_k, stop=None, return_details=False):
            self.history.append({"prompt": prompt, "temp": temp, "top_k": top_k})
            text, conf, fin = self.items.pop(0)
            return (text, conf, fin) if return_details else text

    rt = MultiCandidateRuntime()
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="Explain how photosynthesis converts sunlight."))
    assert decision.text == "Photosynthesis converts sunlight into energy."
    assert decision.confidence == 0.75
    assert len(rt.history) == 3  # 1 primary + 2 best-of-3 resampled candidates


def test_calibration_rejects_degenerate_curve(tmp_path):
    import json

    deg_file = tmp_path / "deg_cal.json"
    deg_file.write_text(
        json.dumps({"mapping": [{"raw": 0.0, "calibrated": 0.13}, {"raw": 1.0, "calibrated": 0.1385}]}),
        encoding="utf-8",
    )
    rt = MockRuntime()
    rt.checkpoint_meta = {"path": "dummy.pt"}
    bridge = Bridge(rt, config=BridgeConfig(calibration_file=str(deg_file)))
    assert bridge._calibration_mapping is None

    valid_file = tmp_path / "valid_cal.json"
    valid_file.write_text(
        json.dumps({"mapping": [{"raw": 0.0, "calibrated": 0.05}, {"raw": 1.0, "calibrated": 0.92}]}),
        encoding="utf-8",
    )
    bridge_valid = Bridge(rt, config=BridgeConfig(calibration_file=str(valid_file)))
    assert bridge_valid._calibration_mapping is not None


def test_think_fallback_preserves_knowledge_task_and_clean_primary_skips_resampling(monkeypatch):
    monkeypatch.setattr("pranav.chit.bridge.search_web", lambda *a, **kw: ["Chit uses 256 byte tokens."])
    rt = MockRuntime(
        responses=[
            "Scratchpad without answer delimiter.",
            "Chit uses 256 byte tokens.",
        ]
    )
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="What tokenizer does Chit use?", search=True, think=True))
    assert decision.text == "Chit uses 256 byte tokens."
    # First call is Task: reasoning, second call (fallback) must preserve Task: knowledge (not Task: chat) and not resample
    assert len(rt.history) == 2
    assert rt.history[0]["prompt"].startswith("Task: reasoning\n")
    assert rt.history[1]["prompt"].startswith("Task: knowledge\n")


def test_subword_tokenizer_defaults_and_self_identity_routing():
    class SubwordTokenizerStub:
        kind = "bpe"
        vocab_size = 2000

        def encode(self, text):
            return [1, 2, 3]

    rt = MockRuntime(responses=["Chit is a helpful local assistant."])
    rt.tokenizer = SubwordTokenizerStub()
    bridge = Bridge(rt)

    # Self-identity query ("Who are you?") routes to Task: knowledge and uses subword decoding defaults (0.2, 10)
    decision = bridge.process(Context(user_input="Who are you?"))
    assert decision.metadata["plan"]["effective_task"] == "knowledge"
    assert decision.metadata["plan"]["decoding"]["temperature"] == 0.2
    assert decision.metadata["plan"]["decoding"]["top_k"] == 10
    assert rt.history[0]["prompt"].startswith("Task: knowledge\n")
    assert rt.history[0]["temp"] == 0.2
    assert rt.history[0]["top_k"] == 10

    # Explicit caller overrides are still respected on subword models
    decision_override = bridge.process(Context(user_input="Hello there"), temperature=0.5, top_k=25)
    assert decision_override.metadata["plan"]["decoding"]["temperature"] == 0.5
    assert decision_override.metadata["plan"]["decoding"]["top_k"] == 25


def test_run_bridge_benchmark_auto_calibrates_promoted_champion(tmp_path, monkeypatch):
    import json
    from pranav.chit import api

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_id = "subword_promoted_job"
    job_folder = jobs_dir / job_id
    job_folder.mkdir()

    (job_folder / "job.json").write_text(json.dumps({"state": "succeeded", "promoted": True}), encoding="utf-8")
    (job_folder / "latest.pt").write_text("promoted-checkpoint-bytes", encoding="utf-8")

    bench_path = job_folder / "bridge_benchmark.json"

    def fake_run(cmd, check=True, capture_output=True):
        bench_path.write_text(
            json.dumps(
                {
                    "details": [
                        {"confidence": 0.1, "exact_match": 0.0},
                        {"confidence": 0.9, "exact_match": 1.0},
                    ]
                }
            ),
            encoding="utf-8",
        )

    calibrated_calls = []

    def fake_train_calibration(eval_p, out_p):
        calibrated_calls.append((Path(eval_p), Path(out_p)))

    reloaded = []

    class DummyBridge:
        def _load_calibration(self):
            reloaded.append(True)

    monkeypatch.setattr(api, "JOBS_DIR", str(jobs_dir))
    monkeypatch.setattr(api.subprocess, "run", fake_run)
    monkeypatch.setattr(
        "pranav.chit.tools.calibrate_confidence.train_calibration_from_eval",
        fake_train_calibration,
    )
    monkeypatch.setitem(api._state, "bridge", DummyBridge())

    api._run_bridge_benchmark(job_id)

    saved = json.loads(bench_path.read_text(encoding="utf-8"))
    assert saved["status"] == "completed"
    assert len(calibrated_calls) == 1
    assert calibrated_calls[0][0] == bench_path
    assert reloaded == [True]



