from pranav.chit.bridge import Bridge, Context
from pranav.chit.session import SessionStore


def test_session_roundtrip_and_retention(tmp_path):
    store = SessionStore(tmp_path / "sessions.db", max_turns=4)
    s = store.create()
    store.append_exchange(s["id"], "one", "ONE")
    store.append_exchange(s["id"], "two", "TWO")
    store.append_exchange(s["id"], "three", "THREE")

    turns = store.turns(s["id"])
    assert [t["content"] for t in turns] == ["two", "TWO", "three", "THREE"]


def test_bridge_uses_session_turns():
    class FakeRuntime:
        def __init__(self):
            self.prompts = []

        def recall(self, *_args):
            return []

        def generate(self, prompt, *_args, **_kwargs):
            self.prompts.append(prompt)
            return "reply"

    runtime = FakeRuntime()
    decision = Bridge(runtime).process(Context(
        user_input="third",
        session_turns=[
            {"role": "user", "content": "first"},
            {"role": "chit", "content": "second"},
        ],
    ))

    prompt = runtime.prompts[0]
    assert "User: first" in prompt
    assert "Chit: second" in prompt
    assert prompt.endswith("User: third\nChit:")
    assert decision.metadata["session_turn_count"] == 2
