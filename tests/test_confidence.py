import pytest
import torch

from pranav.chit.api import ChatResponse
from pranav.chit.bridge import Bridge, Context
from pranav.chit.model import ChitModel
from pranav.chit.runtime import ChitRuntime
from pranav.chit.tokenizer import ByteTokenizer


CFG = dict(vocab_size=256, block_size=32, n_layer=2, n_head=2, n_embd=32)


def test_model_generate_returns_tensor_by_default():
    model = ChitModel(**CFG).eval()
    x = torch.tensor([[1, 2, 3]])
    out = model.generate(x, 5)
    assert isinstance(out, torch.Tensor)
    assert out.shape == (1, 8)


def test_model_generate_return_details():
    model = ChitModel(**CFG).eval()
    x = torch.tensor([[1, 2, 3]])
    out, conf, finish_reason = model.generate(x, 10, return_details=True)
    assert isinstance(out, torch.Tensor)
    assert out.shape == (1, 13)
    assert isinstance(conf, float)
    assert 0.0 <= conf <= 1.0
    assert finish_reason == "length"


def test_model_generate_stop_fn_finish_reason():
    model = ChitModel(**CFG).eval()
    x = torch.tensor([[1, 2, 3]])
    out, conf, finish_reason = model.generate(
        x, 20, stop_fn=lambda idx: idx.size(1) >= 6, return_details=True
    )
    assert out.shape == (1, 6)
    assert finish_reason == "stop"
    assert 0.0 <= conf <= 1.0


def test_runtime_generate_backward_compatibility(tmp_path):
    model = ChitModel(**CFG)
    checkpoint = tmp_path / "model.pt"
    torch.save({"model": model.state_dict(), "model_config": CFG}, checkpoint)
    runtime = ChitRuntime.from_checkpoint(checkpoint, device="cpu")

    # Default call returns plain string
    res = runtime.generate("Hello", max_new_tokens=5)
    assert isinstance(res, str)

    # Detailed call returns 3-tuple
    text, conf, finish_reason = runtime.generate("Hello", max_new_tokens=5, return_details=True)
    assert isinstance(text, str)
    assert isinstance(conf, float)
    assert 0.0 <= conf <= 1.0
    assert finish_reason in ("length", "stop")


def test_runtime_generate_stop_sequence_sets_finish_stop(tmp_path):
    model = ChitModel(**CFG)
    checkpoint = tmp_path / "model.pt"
    torch.save({"model": model.state_dict(), "model_config": CFG}, checkpoint)
    runtime = ChitRuntime.from_checkpoint(checkpoint, device="cpu")

    # Mock model to emit specific stop marker
    def mock_model_generate(idx, max_new_tokens, *args, **kwargs):
        stop_seq = b"\nUser:"
        for b in stop_seq:
            idx = torch.cat((idx, torch.tensor([[b]])), dim=1)
            if kwargs.get("stop_fn") and kwargs["stop_fn"](idx):
                break
        if kwargs.get("return_details"):
            return idx, 0.95, "stop"
        return idx

    runtime.model.generate = mock_model_generate
    text, conf, finish_reason = runtime.generate("Hi", max_new_tokens=20, stop=["\nUser:"], return_details=True)
    assert text == ""
    assert finish_reason == "stop"
    assert conf == 0.95


class DummyRuntime:
    def __init__(self, text="Sample response", conf=0.85, finish_reason="length"):
        self.tokenizer = ByteTokenizer()
        self.model_config = {"block_size": 128}
        self._text = text
        self._conf = conf
        self._finish_reason = finish_reason

    def recall(self, query, k, min_relevance=0.0):
        return []

    def generate(self, prompt, n_tokens, temp, top_k, stop=None, return_details=False):
        if return_details:
            return self._text, self._conf, self._finish_reason
        return self._text


def test_bridge_completeness_detection_incomplete():
    # Length finish without terminal punctuation -> incomplete
    rt = DummyRuntime(text="The cat is runni", conf=0.80, finish_reason="length")
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="Where is cat?"))

    assert decision.confidence == 0.80
    assert decision.metadata["confidence"] == 0.80
    assert decision.metadata["is_incomplete"] is True
    assert decision.metadata["is_uncertain"] is False


def test_bridge_completeness_detection_complete_period():
    # Length finish with period -> complete
    rt = DummyRuntime(text="The cat is running.", conf=0.80, finish_reason="length")
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="Where is cat?"))

    assert decision.metadata["is_incomplete"] is False


def test_bridge_completeness_detection_stop_reason():
    # Stop finish even without period -> not incomplete (model cleanly stopped)
    rt = DummyRuntime(text="Cat", conf=0.90, finish_reason="stop")
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="Where is cat?"))

    assert decision.metadata["is_incomplete"] is False


def test_bridge_uncertainty_and_retrieval_triggers():
    # Low confidence (< 0.40) flags uncertainty and retrieval trigger
    rt = DummyRuntime(text="Quantum gravity formula.", conf=0.28, finish_reason="stop")
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="What is quantum gravity?"))

    assert decision.confidence == 0.28
    assert decision.metadata["is_uncertain"] is True
    assert decision.metadata["needs_retrieval"] is True


def test_bridge_reasoning_scaffold_carries_confidence():
    rt = DummyRuntime(
        text="Calculating 5+5 is 10.\nAnswer: 10.",
        conf=0.92,
        finish_reason="stop"
    )
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="5 + 5", think=True))

    assert decision.text == "10."
    assert decision.metadata["thoughts"] == "Calculating 5+5 is 10."
    assert decision.confidence == 0.92
    assert decision.metadata["confidence"] == 0.92
    assert decision.metadata["is_uncertain"] is False
    assert decision.metadata["is_incomplete"] is False


def test_bridge_handles_legacy_runtime_without_kwargs():
    class LegacyRuntime:
        def __init__(self):
            self.tokenizer = ByteTokenizer()
            self.model_config = {"block_size": 128}

        def recall(self, q, k, min_relevance=0.0):
            return []

        def generate(self, prompt, n_tokens, temp, top_k, stop=None):
            # No return_details parameter
            return "Legacy reply."

    bridge = Bridge(LegacyRuntime())
    decision = bridge.process(Context(user_input="Hello"))
    assert decision.text == "Legacy reply."
    assert decision.confidence == 1.0
    assert decision.metadata["confidence"] == 1.0
    assert decision.metadata["is_uncertain"] is False


def test_chat_response_schema():
    resp = ChatResponse(
        text="Hello",
        session_id="0123456789abcdef0123456789abcdef",
        confidence=0.88,
        is_incomplete=False,
        is_uncertain=False,
        metadata={"confidence": 0.88}
    )
    d = resp.model_dump()
    assert d["text"] == "Hello"
    assert d["confidence"] == 0.88
    assert d["is_incomplete"] is False
    assert d["is_uncertain"] is False
