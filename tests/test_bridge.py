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
    assert rt.history[0]["prompt"] == "Task: reasoning\nInput: 8 - 3\nReasoning:"
    assert rt.history[0]["stop"] == ["\nInput:", "\nUser:", "\nTask:"]


def test_bridge_reasoning_fallback_without_answer():
    # When no Answer: boundary is produced, fall through to standard generation
    rt = MockRuntime(["Just reasoning text without answer", "Standard chat reply."])
    bridge = Bridge(rt)
    decision = bridge.process(Context(user_input="Casual hello", think=True))
    assert decision.text == "Standard chat reply."
    assert "thoughts" not in decision.metadata
    assert len(rt.history) == 2
    assert rt.history[0]["prompt"] == "Task: reasoning\nInput: Casual hello\nReasoning:"
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
    assert decision.metadata["memory_ids"] == []
    assert rt.history[0]["prompt"] == (
        "Task: reasoning\n"
        "Known memory:\n- [Web] Mars has two moons, Phobos and Deimos.\n"
        "Input: How many moons does Mars have?\nReasoning:"
    )


def test_bridge_pure_greeting_with_memory_store(tmp_path):
    from pranav.chit.memory import SQLiteMemoryStore
    s = SQLiteMemoryStore(tmp_path / "mem.db", seed_path=None)
    s.add("Chit is the learning/model layer.", tags=["chit", "identity"])
    assert s.search("Hello Chit", min_relevance=0.35) == []
    assert len(s.search("Who is Chit?", min_relevance=0.35)) == 1

    class RuntimeWithMemory(MockRuntime):
        def recall(self, query, k, min_relevance=0.35):
            return s.search(query, k, min_relevance=min_relevance)

    rt = RuntimeWithMemory(["Hello! How can I help you today?"])
    bridge = Bridge(rt)

    decision = bridge.process(Context(user_input="Hello Chit"))
    assert decision.text == "Hello! How can I help you today?"
    assert decision.metadata["memory_ids"] == []
    assert "Known memory:" not in rt.history[0]["prompt"]


def test_bridge_greeting_recovers_from_attractor_collapse():
    class AttractorRuntime(MockRuntime):
        def recall(self, query, k, min_relevance=0.0):
            return []

    rt = AttractorRuntime(["Sure. I'll use the latest explicit correction and treat the earlier detail as obsolete."])
    bridge = Bridge(rt)

    decision = bridge.process(Context(user_input="Hello Chit"))
    assert decision.text == "Hello! How can I help you today?"
    assert decision.confidence == 0.95
    assert decision.metadata["memory_ids"] == []


def test_bridge_non_greeting_queries_recall_memory():
    recalled = []

    class NonGreetingRuntime(MockRuntime):
        def recall(self, query, k, min_relevance=0.0):
            recalled.append(query)
            return [{"id": "seed-001", "content": "Chit is the learning/model layer."}]

    rt = NonGreetingRuntime(["Chit is the neural layer."])
    bridge = Bridge(rt)

    decision = bridge.process(Context(user_input="Who is Chit?"))
    assert len(recalled) == 1
    assert decision.metadata["memory_ids"] == ["seed-001"]
    assert "Known memory:" in rt.history[0]["prompt"]


def test_bridge_arithmetic_attractor_intercepted_on_web_reasoning(monkeypatch):
    fake_snippet = "Nasadiya Sukta (RV 10.129) takes a near-agnostic stand on the creation."
    monkeypatch.setattr("pranav.chit.bridge.search_web", lambda *a, **kw: [fake_snippet])

    # Model hallucinates memorized "5 apples." training attractor
    rt = MockRuntime([
        "Ravi starts with 8 apples. He gives away 3.\nAnswer: 5 apples."
    ])
    bridge = Bridge(rt)

    decision = bridge.process(Context(user_input="Explain the creation hymn Nasadiya Sukta in Rigveda ?", search=True, think=True))
    assert decision.metadata["web_grounded"] is True
    assert decision.metadata["grounding_fallback"] is True
    assert "5 apples" not in decision.text
    assert "Nasadiya Sukta" in decision.text
    assert "Verified premise:" in decision.metadata["thoughts"]


def test_bridge_arithmetic_stamps_attractor_intercepted():
    # Model hallucinates "5 stamps." attractor for simple arithmetic
    rt = MockRuntime([
        "4 divided by 2 equals 5.\nAnswer: 5 stamps."
    ])
    bridge = Bridge(rt)

    decision = bridge.process(Context(user_input="What is 1 + 1 ?", think=True))
    assert "stamps" not in decision.text
    assert decision.metadata["confidence"] >= 0.90
    assert "Detect ungrounded divergence" in decision.metadata["thoughts"]


def test_bridge_universal_grounding_preserves_legitimate_word_problems():
    # Legitimate math word problem matching the query context is preserved
    rt = MockRuntime([
        "12 minus 4 equals 8.\nAnswer: 8 marbles."
    ])
    bridge = Bridge(rt)

    decision = bridge.process(Context(
        user_input="Sara has 12 marbles and gives away 4. How many marbles does Sara have?",
        think=True
    ))
    assert decision.text == "8 marbles."
    assert decision.metadata["thoughts"] == "12 minus 4 equals 8."
    assert "grounding_fallback" not in decision.metadata



