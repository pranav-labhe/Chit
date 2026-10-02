import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from conftest import H, install_candidate_for_test, train_body, wait_job
from pranav.chit import api
from pranav.chit.formats import render_chat_prompt
from pranav.chit.sessions import SessionNotFound, SessionStore


# ------------------------------------------------------------------ store


def test_create_append_history(tmp_path):
    s = SessionStore(tmp_path / "s.db")
    sid = s.create()["id"]
    assert s.get(sid)["turns"] == 0 and s.history(sid) == []
    s.append(sid, [("user", "hi"), ("assistant", "hello")])
    s.append(sid, [("user", "again"), ("assistant", "yes")])
    assert [m["content"] for m in s.history(sid)] == ["hi", "hello", "again", "yes"]
    assert [m["content"] for m in s.history(sid, limit=2)] == ["again", "yes"]  # most recent, oldest-first
    assert s.get(sid)["turns"] == 4


def test_sessions_are_isolated_and_persist(tmp_path):
    a, b = SessionStore(tmp_path / "s.db"), None
    s1, s2 = a.create()["id"], a.create()["id"]
    a.append(s1, [("user", "one")])
    a.append(s2, [("user", "two")])
    b = SessionStore(tmp_path / "s.db")                     # a new process opening the same file
    assert [m["content"] for m in b.history(s1)] == ["one"]
    assert [m["content"] for m in b.history(s2)] == ["two"]


def test_unknown_session_and_bad_role(tmp_path):
    s = SessionStore(tmp_path / "s.db")
    with pytest.raises(SessionNotFound):
        s.history("0" * 32)
    with pytest.raises(SessionNotFound):
        s.append("0" * 32, [("user", "x")])
    sid = s.create()["id"]
    with pytest.raises(ValueError):
        s.append(sid, [("system", "x")])
    assert s.history(sid) == []                              # nothing half-written


def test_max_turns_drops_oldest(tmp_path):
    s = SessionStore(tmp_path / "s.db", max_turns=4)
    sid = s.create()["id"]
    for i in range(5):
        s.append(sid, [("user", f"q{i}"), ("assistant", f"a{i}")])
        if s.summary_needed(sid):
            s.summarize_overflow(sid)
    assert [m["content"] for m in s.history(sid)] == ["q3", "a3", "q4", "a4"]
    session = s.get(sid)
    assert session["summary_status"] == "ready"
    assert session["summary_through_seq"] > 0
    assert "q0" in session["summary"]


def test_delete_cascades_and_prune(tmp_path):
    s = SessionStore(tmp_path / "s.db")
    old, new = s.create()["id"], s.create()["id"]
    s.append(old, [("user", "x")])
    long_ago = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    with sqlite3.connect(s.path) as db:
        db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (long_ago, old))
    assert s.prune(30) == 1
    with pytest.raises(SessionNotFound):
        s.get(old)
    assert s.get(new)["id"] == new
    assert s.delete(new) and not s.delete(new)
    with sqlite3.connect(s.path) as db:
        assert db.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 0   # turns went with their session


# ------------------------------------------------------------------ prompt


HIST = [{"role": "user", "content": "My name is Asha."}, {"role": "assistant", "content": "Hello Asha."}]


def test_prompt_without_history_is_unchanged():
    assert render_chat_prompt("Hi", ["a fact"]) == "Task: chat\nKnown memory:\n- a fact\nUser: Hi\nChit:"


def test_prompt_includes_history_in_order():
    p = render_chat_prompt("Who am I?", [], history=HIST)
    assert p.endswith("User: My name is Asha.\nChit: Hello Asha.\nUser: Who am I?\nChit:")


def test_prompt_distinguishes_user_facts_and_derived_summary():
    p = render_chat_prompt("What is my deadline?", [],
                           facts=[{"key": "deadline", "value": "Thursday"}],
                           summary="The user is preparing a report.")
    assert "User-stated facts (latest correction wins):\n- deadline: Thursday" in p
    assert "Earlier conversation summary (derived context):\nThe user is preparing a report." in p
    assert p.endswith("User: What is my deadline?\nChit:")


def test_prompt_trims_oldest_turns_first_and_keeps_message():
    p = render_chat_prompt("Who am I?", ["fact"], history=HIST, max_bytes=len(render_chat_prompt("Who am I?", ["fact"])) + 5)
    assert "Asha" not in p and "- fact" in p and p.endswith("User: Who am I?\nChit:")
    tiny = render_chat_prompt("Who am I?", ["fact"], history=HIST, max_bytes=10)
    assert "- fact" not in tiny and tiny.endswith("User: Who am I?\nChit:")   # message is never dropped


def test_prompt_truncates_long_utf8_message_to_fit_when_scaffold_fits():
    p = render_chat_prompt("नमस्ते " * 100, [], max_bytes=128)
    assert len(p.encode("utf-8")) <= 128
    assert p.startswith("Task: chat\nKnown memory:\n- (none)\nUser: नमस्ते")
    assert p.endswith("\nChit:")


def test_prompt_preserves_markdown_structure_and_code_fences():
    message = "Review this:\n## Error\n```python\nprint(items[3])\n```\nWhy does it fail?"
    prompt = render_chat_prompt(message, [], max_bytes=256)
    assert "## Error" in prompt
    assert "```python\nprint(items[3])\n```" in prompt
    assert prompt.endswith("\nChit:")


def test_trimming_never_starts_on_an_orphan_reply():
    hist = HIST + [{"role": "user", "content": "Q2"}, {"role": "assistant", "content": "A2"}]
    full = render_chat_prompt("Now", [], history=hist)
    cut = render_chat_prompt("Now", [], history=hist, max_bytes=len(full) - 3)
    assert "Chit: Hello Asha." not in cut and "User: Q2" in cut


# ------------------------------------------------------------------ API


@pytest.fixture
def served(client):
    body = train_body()
    body["model"] = {**body["model"], "block_size": 128}    # room for history; the default test model has 16
    job = client.post("/train", json=body, headers=H).json()
    completed = wait_job(client, job["id"])
    assert not completed["promoted"]
    install_candidate_for_test(completed)
    return client


def test_chat_creates_then_continues_a_session(served):
    prompts = []
    rt = api._state["runtime"]
    real = rt.generate
    rt.generate = lambda prompt, *a, **k: (prompts.append(prompt), real(prompt, *a, **k))[1]
    api._state["bridge"].max_new_tokens = 6                 # short replies, so turn 1 still fits in 128 bytes

    first = served.post("/chat", json={"message": "My name is Asha."}, headers=H).json()
    sid = first["session_id"]
    assert len(sid) == 32
    second = served.post("/chat", json={"message": "Who am I?", "session_id": sid}, headers=H).json()
    assert second["session_id"] == sid

    assert "Asha" not in prompts[0].split("User:")[0]        # nothing earlier for the first message
    assert "User-stated facts (latest correction wins):\n- name: Asha" in prompts[1]
    msgs = served.get(f"/sessions/{sid}", headers=H).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "My name is Asha." and msgs[2]["content"] == "Who am I?"


def test_history_is_trimmed_to_the_model_context(client):
    job = client.post("/train", json=train_body(), headers=H).json()   # block_size 16: no room for history
    completed = wait_job(client, job["id"])
    assert not completed["promoted"]
    install_candidate_for_test(completed)
    prompts = []
    rt = api._state["runtime"]
    real = rt.generate
    rt.generate = lambda prompt, *a, **k: (prompts.append(prompt), real(prompt, *a, **k))[1]
    sid = client.post("/chat", json={"message": "My name is Asha."}, headers=H).json()["session_id"]
    client.post("/chat", json={"message": "Who am I?", "session_id": sid}, headers=H)
    assert "Asha" not in prompts[1] and prompts[1].endswith("User: Who am I?\nChit:")
    assert len(client.get(f"/sessions/{sid}", headers=H).json()["messages"]) == 4   # still stored in full


def test_separate_chats_do_not_share_history(served):
    a = served.post("/chat", json={"message": "alpha"}, headers=H).json()["session_id"]
    b = served.post("/chat", json={"message": "beta"}, headers=H).json()["session_id"]
    assert a != b
    assert [m["content"] for m in served.get(f"/sessions/{b}", headers=H).json()["messages"]][0] == "beta"


def test_unknown_or_malformed_session_ids(served):
    r = served.post("/chat", json={"message": "hi", "session_id": "0" * 32}, headers=H)
    assert r.status_code == 404
    assert served.post("/chat", json={"message": "hi", "session_id": "not-an-id"}, headers=H).status_code == 422
    assert served.get("/sessions/" + "0" * 32, headers=H).status_code == 404
    assert served.get("/sessions/..%2f..%2fetc", headers=H).status_code == 404


def test_session_crud_and_auth(served):
    sid = served.post("/sessions", headers=H).json()["id"]
    served.post("/chat", json={"message": "hi", "session_id": sid}, headers=H)
    listing = served.get("/sessions", headers=H).json()
    assert listing["total"] == 1 and listing["sessions"][0]["turns"] == 2
    assert served.delete(f"/sessions/{sid}", headers=H).status_code == 204
    assert served.get(f"/sessions/{sid}", headers=H).status_code == 404
    assert served.delete(f"/sessions/{sid}", headers=H).status_code == 404
    for call in (lambda: served.post("/sessions"), lambda: served.get("/sessions"),
                 lambda: served.get(f"/sessions/{sid}")):
        assert call().status_code == 401


def test_session_fact_controls_api(served):
    sid = served.post("/sessions", headers=H).json()["id"]
    served.post("/chat", json={"message": "I prefer tea.", "session_id": sid}, headers=H)
    facts_url = f"/sessions/{sid}/facts"
    initial = served.get(facts_url, headers=H).json()
    assert initial["enabled"] and initial["facts"][0]["value"] == "tea"

    disabled = served.patch(facts_url, json={"enabled": False}, headers=H).json()
    assert disabled["enabled"] is False
    served.post("/chat", json={"message": "My budget is $50.", "session_id": sid}, headers=H)
    assert [fact["key"] for fact in served.get(facts_url, headers=H).json()["facts"]] == ["preference"]

    served.patch(facts_url, json={"enabled": True}, headers=H)
    refreshed = served.post(f"{facts_url}/refresh", headers=H).json()
    assert {fact["key"]: fact["value"] for fact in refreshed["facts"]} == {
        "preference": "tea", "budget": "$50"}
    assert served.delete(facts_url, headers=H).json()["facts"] == []


def test_continue_task_does_not_use_sessions(served):
    r = served.post("/chat", json={"message": "Chit is", "task": "continue", "temperature": 0}, headers=H)
    assert r.status_code == 200 and r.json()["session_id"] is None
    assert served.get("/sessions", headers=H).json()["total"] == 0
    bad = served.post("/chat", json={"message": "x", "task": "continue", "session_id": "0" * 32}, headers=H)
    assert bad.status_code == 422
