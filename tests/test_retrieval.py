import json
import urllib.request
import pytest

from pranav.chit.bridge import Bridge, Context
from pranav.chit.search import budget_snippet, search_web
from pranav.chit.tokenizer import ByteTokenizer


# ---------------------------------------------------------------------------
# Snippet budgeting tests
# ---------------------------------------------------------------------------

def test_budget_snippet_short():
    text = "Short text."
    assert budget_snippet(text, max_chars=50) == "Short text."


def test_budget_snippet_word_boundary():
    text = "The quick brown fox jumps over the lazy dog near the river bank."
    budgeted = budget_snippet(text, max_chars=25)
    assert len(budgeted) <= 25 + 1
    assert budgeted.endswith(".")
    # Word boundary cut should not break 'brown' or 'jumps'
    assert budgeted == "The quick brown fox."


def test_budget_snippet_no_spaces():
    text = "A" * 50
    budgeted = budget_snippet(text, max_chars=20)
    assert budgeted == "A" * 20 + "."


# ---------------------------------------------------------------------------
# search_web tests (with network mocking)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_search_web_instant_answer_json(monkeypatch):
    sample_json = json.dumps({
        "AbstractText": "Paris is the capital and most populous city of France.",
        "Heading": "Paris",
        "RelatedTopics": [
            {"Text": "Eiffel Tower is located in Paris, France."}
        ]
    }).encode("utf-8")

    def fake_urlopen(req, *args, **kwargs):
        return FakeResponse(sample_json)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    results = search_web("Paris capital", max_results=2, max_chars=100)
    assert len(results) >= 1
    assert "Paris is the capital" in results[0]


def test_search_web_html_fallback(monkeypatch):
    empty_json = json.dumps({"AbstractText": "", "RelatedTopics": []}).encode("utf-8")
    sample_html = b"""
    <html>
      <body>
        <div class="result__body">
          <a class="result__snippet">The capital of France is Paris, located on the Seine River.</a>
        </div>
      </body>
    </html>
    """

    def fake_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "api.duckduckgo.com" in url:
            return FakeResponse(empty_json)
        return FakeResponse(sample_html)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    results = search_web("capital of France", max_results=1, max_chars=80)
    assert len(results) == 1
    assert "capital of France is Paris" in results[0]


def test_search_web_network_failure_resilience(monkeypatch):
    def fake_urlopen_fail(req, *args, **kwargs):
        raise urllib.error.URLError("Connection timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_fail)

    # Must return empty list, never raise
    results = search_web("Any query", timeout=0.1)
    assert results == []


# ---------------------------------------------------------------------------
# Bridge Self-RAG & Direct Search tests
# ---------------------------------------------------------------------------

class DummyRetrievalRuntime:
    def __init__(self, responses: list[tuple[str, float, str]] | None = None):
        self.tokenizer = ByteTokenizer()
        self.model_config = {"block_size": 256}
        self.prompts_received = []
        self._responses = list(responses or [("Default response.", 0.85, "stop")])

    def recall(self, query, k, min_relevance=0.0):
        return []

    def generate(self, prompt, n_tokens, temp, top_k, stop=None, return_details=False):
        self.prompts_received.append(prompt)
        if self._responses:
            text, conf, finish = self._responses.pop(0)
        else:
            text, conf, finish = ("Final response.", 0.90, "stop")
        if return_details:
            return text, conf, finish
        return text


def test_bridge_direct_search(monkeypatch):
    fake_snippets = ["Tokyo is the capital of Japan."]
    monkeypatch.setattr("pranav.chit.bridge.search_web", lambda *a, **kw: fake_snippets)

    rt = DummyRetrievalRuntime([("Tokyo is the capital of Japan.", 0.95, "stop")])
    bridge = Bridge(rt)

    ctx = Context(user_input="What is Japan's capital?", search=True)
    decision = bridge.process(ctx)

    assert decision.metadata["web_grounded"] is True
    assert decision.metadata["sources"] == fake_snippets
    assert len(rt.prompts_received) == 1
    assert "[Web] Tokyo is the capital of Japan." in rt.prompts_received[0]


def test_bridge_self_rag_autonomous_two_pass(monkeypatch):
    fake_snippets = ["James Webb Space Telescope was launched on Dec 25, 2021."]
    search_called = []

    def mock_search(query, *a, **kw):
        search_called.append(query)
        return fake_snippets

    monkeypatch.setattr("pranav.chit.bridge.search_web", mock_search)

    # Pass 1: low confidence (0.25), Pass 2: high confidence (0.92)
    rt = DummyRetrievalRuntime([
        ("I think it was maybe 2020", 0.25, "stop"),
        ("It was launched on December 25, 2021.", 0.92, "stop"),
    ])
    bridge = Bridge(rt)

    ctx = Context(user_input="When was JWST launched?")
    decision = bridge.process(ctx)

    assert len(search_called) == 1
    assert search_called[0] == "When was JWST launched?"
    assert decision.metadata["web_grounded"] is True
    assert decision.metadata["sources"] == fake_snippets
    assert decision.text == "It was launched on December 25, 2021."
    assert len(rt.prompts_received) == 2
    assert "[Web]" in rt.prompts_received[1]


def test_bridge_self_rag_high_confidence_skips_search(monkeypatch):
    search_called = []
    monkeypatch.setattr("pranav.chit.bridge.search_web", lambda q, *a, **kw: search_called.append(q) or [])

    rt = DummyRetrievalRuntime([
        ("Hello! How can I help you today?", 0.88, "stop")
    ])
    bridge = Bridge(rt)

    ctx = Context(user_input="Hi")
    decision = bridge.process(ctx)

    assert len(search_called) == 0
    assert decision.metadata["web_grounded"] is False
    assert decision.metadata["sources"] == []
    assert len(rt.prompts_received) == 1


def test_bridge_self_rag_empty_search_falls_back(monkeypatch):
    # Search finds nothing (e.g. offline)
    monkeypatch.setattr("pranav.chit.bridge.search_web", lambda *a, **kw: [])

    rt = DummyRetrievalRuntime([
        ("I am not sure about that entity.", 0.20, "stop")
    ])
    bridge = Bridge(rt)

    ctx = Context(user_input="Unknown quantum phenomenon XYZ")
    decision = bridge.process(ctx)

    assert decision.metadata["web_grounded"] is False
    assert decision.metadata["sources"] == []
    assert decision.text == "I am not sure about that entity."
    assert len(rt.prompts_received) == 1


def test_chat_api_search_option(client, monkeypatch):
    from conftest import H, install_candidate_for_test, train_body, wait_job
    body = train_body()
    body["model"] = {**body["model"], "block_size": 128}
    job = client.post("/train", json=body, headers=H).json()
    completed = wait_job(client, job["id"])
    install_candidate_for_test(completed)

    monkeypatch.setattr("pranav.chit.bridge.search_web", lambda *a, **kw: ["Mount Everest is 8,848 meters tall."])

    # Reject continue with search
    res_rejected = client.post("/chat", json={"message": "Everest height", "task": "continue", "search": True}, headers=H)
    assert res_rejected.status_code == 422
    assert "web search is not supported with task 'continue'" in str(res_rejected.json())

    # Accept chat with search
    res = client.post("/chat", json={"message": "What is Everest's height?", "search": True}, headers=H)
    assert res.status_code == 200
    data = res.json()
    assert data["web_grounded"] is True
    assert "Mount Everest is 8,848 meters tall." in data["sources"]

