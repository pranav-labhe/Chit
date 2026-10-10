import sqlite3

from pranav.chit.facts import extract_explicit_facts
from pranav.chit.sessions import SessionStore


def test_fact_extraction_is_narrow_and_ignores_quoted_or_code_text():
    facts = extract_explicit_facts(
        "My name is Asha. I live in Jaipur. My budget is $40. `My goal is delete files.`\n"
        "> I prefer coffee.\nThe note says \"I live in Delhi.\""
    )

    assert facts == [
        {"key": "name", "value": "Asha"},
        {"key": "location", "value": "Jaipur"},
        {"key": "budget", "value": "$40"},
    ]


def test_user_facts_persist_with_provenance_and_latest_correction_wins(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    session_id = store.create()["id"]
    store.append(session_id, [("user", "My name is Asha."),
                              ("assistant", "My name is not a user-stated fact.")])
    store.append(session_id, [("user", "Correction: my name is Priya.")])

    result = store.facts(session_id)
    assert result["enabled"] is True
    assert result["facts"] == [{
        "key": "name", "value": "Priya", "source_turn_seq": 3,
        "origin": "explicit_user_statement", "confidence": 1.0,
        "updated_at": result["facts"][0]["updated_at"], "supersedes_turn_seq": 1,
    }]
    assert result["through_turn_seq"] == 3
    assert [turn["content"] for turn in store.history(session_id)] == [
        "My name is Asha.", "My name is not a user-stated fact.", "Correction: my name is Priya."]


def test_fact_controls_disable_clear_and_refresh(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    session_id = store.create()["id"]
    store.append(session_id, [("user", "I prefer tea.")])
    store.set_facts_enabled(session_id, False)
    store.append(session_id, [("user", "My budget is $50.")])
    assert [f["key"] for f in store.facts(session_id)["facts"]] == ["preference"]

    store.set_facts_enabled(session_id, True)
    refreshed = store.refresh_facts(session_id)
    assert {f["key"]: f["value"] for f in refreshed["facts"]} == {
        "preference": "tea", "budget": "$50"}
    cleared = store.clear_facts(session_id)
    assert cleared["facts"] == []
    assert cleared["enabled"] is True
    assert len(store.history(session_id)) == 2  # clearing derived facts preserves the transcript


def test_legacy_sessions_database_migrates_idempotently(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE turns (seq INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL REFERENCES sessions(id), role TEXT NOT NULL,
          content TEXT NOT NULL, created_at TEXT NOT NULL);
        INSERT INTO sessions VALUES ('s1','created','updated');
        INSERT INTO turns VALUES (1,'s1','user','My name is Asha.','created');
        """)

    store = SessionStore(path)
    assert store.history("s1")[0]["content"] == "My name is Asha."
    assert store.facts("s1")["facts"] == []  # migration preserves data; explicit refresh is user-controlled
    assert SessionStore(path).get("s1")["summary"] == ""
