from conftest import H, install_candidate_for_test, train_body, wait_job
from pranav.chit import api


def _serve_context_sized_model(client, block_size=128):
    body = train_body()
    body["model"] = {**body["model"], "block_size": block_size}
    job = client.post("/train", json=body, headers=H).json()
    completed = wait_job(client, job["id"])
    assert not completed["promoted"]
    install_candidate_for_test(completed)


def test_generate_defaults_to_assistant_request_and_uses_memory(client):
    _serve_context_sized_model(client)
    memory = client.post("/memory", json={"content": "The preferred color is amber."}, headers=H)
    assert memory.status_code == 201

    calls = []
    api._state["runtime"].generate = lambda *args, **kwargs: (calls.append((args, kwargs)), "reply")[1]
    response = client.post("/generate", json={
        "prompt": "What is the preferred color?", "tokens": 37, "temperature": 0,
        "top_k": 9, "stop": ["END"],
    }, headers=H)

    assert response.status_code == 200
    assert response.json()["text"] == "reply"
    assert set(response.json()) == {"text", "confidence", "web_grounded", "sources", "is_uncertain", "is_incomplete", "metadata"}
    (prompt, tokens, temperature, top_k), kwargs = calls[0]
    assert prompt.startswith("Task: chat\nKnown memory:\n- The preferred color is amber.")
    assert "User: What is the preferred color?\nChit:" in prompt
    assert (tokens, temperature, top_k) == (37, 0, 1)
    assert kwargs["stop"] == ["END"]


def test_generate_continue_mode_keeps_raw_text_continuation(client):
    _serve_context_sized_model(client)
    calls = []
    api._state["runtime"].generate = lambda *args, **kwargs: (calls.append((args, kwargs)), " next")[1]

    response = client.post("/generate", json={
        "prompt": "The next byte follows", "mode": "continue", "tokens": 11,
        "temperature": 0.2, "top_k": 4, "stop": ["END"],
    }, headers=H)

    assert response.status_code == 200 and response.json() == {"text": " next"}
    args, kwargs = calls[0]
    assert args == ("The next byte follows", 11, 0.2, 4)
    assert kwargs == {"stop": ["END"]}


def test_generate_rejects_unknown_mode_and_keeps_auth(client):
    assert client.post("/generate", json={"prompt": "hello", "mode": "unknown"}, headers=H).status_code == 422
    assert client.post("/generate", json={"prompt": "hello"}).status_code == 401


def test_chat_keeps_response_fields_and_accepts_generation_length(client):
    _serve_context_sized_model(client)
    calls = []
    api._state["runtime"].generate = lambda *args, **kwargs: (calls.append((args, kwargs)), "reply")[1]

    response = client.post("/chat", json={"message": "Write a greeting.", "tokens": 19}, headers=H)

    assert response.status_code == 200
    assert set(response.json()) == {"text", "session_id", "metadata", "confidence", "is_incomplete", "is_uncertain", "web_grounded", "sources"}
    assert response.json()["text"] == "reply"
    assert response.json()["session_id"]
    assert calls[0][0][1] == 19


def test_chat_passes_markdown_verbatim_and_allows_blank_lines_in_response(client):
    _serve_context_sized_model(client)
    calls = []
    api._state["runtime"].generate = lambda *args, **kwargs: (calls.append((args, kwargs)), "reply")[1]
    message = "## Bug\n```py\nx[3]\n```\nWhy?"

    response = client.post("/chat", json={"message": message}, headers=H)

    assert response.status_code == 200
    prompt, *_ = calls[0][0]
    assert message in prompt
    assert "\n\n" not in calls[0][1]["stop"]


def test_generate_continue_mode_rejects_search_and_think(client):
    _serve_context_sized_model(client)
    res_search = client.post("/generate", json={"prompt": "abc", "mode": "continue", "search": True}, headers=H)
    assert res_search.status_code == 422
    assert "web search is not supported with mode 'continue'" in str(res_search.json())

    res_think = client.post("/generate", json={"prompt": "abc", "mode": "continue", "think": True}, headers=H)
    assert res_think.status_code == 422
    assert "thinking is not supported with mode 'continue'" in str(res_think.json())


def test_generate_assistant_mode_supports_search_and_think(client, monkeypatch):
    _serve_context_sized_model(client)
    fake_snippet = "Light travels at 299,792 km/s in vacuum."
    monkeypatch.setattr("pranav.chit.bridge.search_web", lambda *a, **kw: [fake_snippet])

    res = client.post("/generate", json={"prompt": "Speed of light?", "mode": "assistant", "search": True}, headers=H)
    assert res.status_code == 200
    data = res.json()
    assert data["web_grounded"] is True
    assert fake_snippet in data["sources"]
    assert "confidence" in data
    assert "metadata" in data

