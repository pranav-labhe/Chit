from pranav.chit.bridge import Bridge, Context
from pranav.chit.tokenizer import ByteTokenizer


class MockRuntime:
    def __init__(self, responses=None):
        self.tokenizer = ByteTokenizer()
        self.model_config = {"block_size": 128}
        self.responses = responses or ["Mock output"]
        self.history = []

    def recall(self, query, k, min_relevance=0.0):
        return []

    def generate(self, prompt, n_tokens, temp, top_k, stop=None):
        self.history.append({"prompt": prompt, "stop": stop})
        if self.responses:
            return self.responses.pop(0)
        return "Default output"


def test_bridge_standard_chat_generation():
    rt = MockRuntime(["Hello, human!"])
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="Hello"))
    assert decision.text == "Hello, human!"
    assert decision.metadata["task"] == "chat"
    assert "thoughts" not in decision.metadata
    assert rt.history[0]["prompt"].endswith("User: Hello\nChit:")


def test_bridge_continue_task():
    rt = MockRuntime(["continuation text"])
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="Prefix", task="continue"))
    assert decision.text == "continuation text"
    assert decision.metadata["task"] == "continue"
    assert rt.history[0]["prompt"] == "Prefix"


def test_bridge_reasoning_scaffold_with_answer():
    rt = MockRuntime(["Deduction step.\nAnswer: Final."])
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="8 - 3", think=True))
    assert decision.text == "Final."
    assert decision.metadata["thoughts"] == "Deduction step."
    assert decision.metadata["thought_tokens"] == len(rt.tokenizer.encode("Deduction step."))
    assert rt.history[0]["prompt"] == "Input: 8 - 3\nReasoning:"
    assert rt.history[0]["stop"] == ["\nInput:", "\nUser:", "\nTask:"]


def test_bridge_reasoning_fallback_without_answer():
    # When no Answer: boundary is produced, fall through to standard generation
    rt = MockRuntime(["Just reasoning text without answer", "Standard chat reply."])
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="Casual hello", think=True))
    assert decision.text == "Standard chat reply."
    assert "thoughts" not in decision.metadata
    assert len(rt.history) == 2
    assert rt.history[0]["prompt"] == "Input: Casual hello\nReasoning:"
    assert rt.history[1]["prompt"].endswith("User: Casual hello\nChit:")


def test_bridge_search_and_thinking_pipeline_unified(monkeypatch):
    fake_snippets = ["Mars has two moons, Phobos and Deimos."]
    monkeypatch.setattr("pranav.chit.bridge.search_web", lambda *a, **kw: fake_snippets)

    rt = MockRuntime(["Phobos and Deimos are moons.\nAnswer: 2 moons."])
    bridge = Bridge(rt)

    decision = bridge.process(Context(user_input="How many moons does Mars have?", search=True, think=True))
    assert decision.text == "2 moons."
    assert decision.metadata["thoughts"] == "Phobos and Deimos are moons."
    assert decision.metadata["thought_tokens"] == len(rt.tokenizer.encode("Phobos and Deimos are moons."))
    assert decision.metadata["web_grounded"] is True
    assert decision.metadata["sources"] == fake_snippets
    assert decision.metadata["web_search_query"] == "How many moons does Mars have?"
    assert rt.history[0]["prompt"] == "Input: How many moons does Mars have?\nReasoning:"

