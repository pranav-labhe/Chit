from conftest import H, train_body, wait_job
from pranav.chit import api


def _serve_context_sized_model(client, block_size=128):
    body = train_body()
    body["model"] = {**body["model"], "block_size": block_size}
    job = client.post("/train", json=body, headers=H).json()
    assert wait_job(client, job["id"])["promoted"]


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
    assert response.json() == {"text": "reply"}
    (prompt, tokens, temperature, top_k), kwargs = calls[0]
    assert prompt.startswith("Task: chat\nKnown memory:\n- The preferred color is amber.")
    assert "User: What is the preferred color?\nChit:" in prompt
    assert (tokens, temperature, top_k) == (37, 0, 9)
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
    assert set(response.json()) == {"text", "session_id", "metadata"}
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
