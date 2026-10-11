import pytest

from conftest import H, install_candidate_for_test, train_body, wait_job
from pranav.chit import api
from pranav.chit.bridge import Bridge, Context
from pranav.chit.tokenizer import ByteTokenizer


@pytest.fixture
def served(client):
    body = train_body()
    body["model"] = {**body["model"], "block_size": 128}
    job = client.post("/train", json=body, headers=H).json()
    completed = wait_job(client, job["id"])
    assert not completed["promoted"]
    install_candidate_for_test(completed)
    return client


def test_thinking_attaches_thoughts_and_preserves_clean_session(served):
    rt = api._state["runtime"]
    prompts = []

    def mock_generate(prompt, n_tokens, temp, top_k, stop=None):
        prompts.append((prompt, stop))
        return "Ravi has 8 apples. 8 - 3 = 5.\nAnswer: 5 apples."

    original_gen = rt.generate
    rt.generate = mock_generate
    try:
        r = served.post("/chat", json={
            "message": "Ravi has 8 apples. He gives 3 away. How many remain?",
            "think": True
        }, headers=H)
        assert r.status_code == 200
        data = r.json()
        sid = data["session_id"]
        assert data["text"] == "5 apples."
        assert data["metadata"]["thoughts"] == "Ravi has 8 apples. 8 - 3 = 5."
        assert data["metadata"]["thought_tokens"] == len(rt.tokenizer.encode(data["metadata"]["thoughts"]))

        # Verify prompt had reasoning primer and proper stop sequences
        prompt, stop = prompts[0]
        assert prompt.endswith("Chit: Reasoning:")
        assert "\nChit:" not in stop
        assert "\nUser:" in stop
        assert "\nTask:" in stop

        # Verify session history stored only clean final answer, NOT the scratchpad
        session_info = served.get(f"/sessions/{sid}", headers=H).json()
        messages = session_info["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "5 apples."
        assert "Reasoning" not in messages[1]["content"]
    finally:
        rt.generate = original_gen


def test_thinking_fallback_when_no_answer_boundary(served):
    rt = api._state["runtime"]

    def mock_generate(prompt, n_tokens, temp, top_k, stop=None):
        return "Direct reasoning deduction without an explicit answer delimiter."

    original_gen = rt.generate
    rt.generate = mock_generate
    try:
        r = served.post("/chat", json={
            "message": "Explain 1+1",
            "think": True
        }, headers=H)
        assert r.status_code == 200
        data = r.json()
        assert data["text"] == "Direct reasoning deduction without an explicit answer delimiter."
        assert data["metadata"]["thoughts"] == "Direct reasoning deduction without an explicit answer delimiter."
        assert data["metadata"]["thought_tokens"] > 0
    finally:
        rt.generate = original_gen


def test_thinking_rejected_for_continue_task(served):
    r = served.post("/chat", json={
        "message": "The sun rises in the",
        "task": "continue",
        "think": True
    }, headers=H)
    assert r.status_code == 422
    assert "thinking is not supported with task 'continue'" in str(r.json()["detail"])


def test_bridge_process_unit_reasoning():
    recorded = {}

    class DummyRuntime:
        def __init__(self):
            self.tokenizer = ByteTokenizer()
            self.model_config = {"block_size": 128}

        def recall(self, query, k, min_relevance=0.0):
            return []

        def generate(self, prompt, n_tokens, temp, top_k, stop=None):
            recorded["prompt"] = prompt
            recorded["stop"] = stop
            return "Step 1: Compute.\nAnswer: Done."

    runtime = DummyRuntime()
    bridge = Bridge(runtime)
    ctx = Context(user_input="What is 10 / 2?", think=True)
    decision = bridge.process(ctx)

    assert decision.text == "Done."
    assert decision.metadata["thoughts"] == "Step 1: Compute."
    assert decision.metadata["thought_tokens"] == len(runtime.tokenizer.encode("Step 1: Compute."))
    assert recorded["prompt"].endswith("Chit: Reasoning:")
    assert recorded["stop"] == ["\nUser:", "\nTask:"]
