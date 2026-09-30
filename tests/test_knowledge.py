import json

import pytest

from pranav.chit.knowledge import KnowledgeError, KnowledgeStore, build_dataset


@pytest.fixture
def store(tmp_path):
    return KnowledgeStore(tmp_path / "k.db")


def test_add_dedup_and_normalisation(store):
    a = store.add("qa", {"question": "Return window?", "answer": "30 days."}, tags=["returns"])
    b = store.add("qa", {"question": "  Return   window? ", "answer": "30 days."})
    assert a.created and not b.created and a.entry["id"] == b.entry["id"]
    assert store.stats()["total"] == 1


@pytest.mark.parametrize("kind,payload", [
    ("poem", {"text": "x"}),
    ("qa", {"question": "q"}),
    ("qa", {"question": "q", "answer": "  "}),
    ("text", {"text": "x", "extra": "y"}),
])
def test_validation(store, kind, payload):
    with pytest.raises(KnowledgeError):
        store.add(kind, payload)


def test_batch_is_atomic(store):
    with pytest.raises(KnowledgeError):
        store.add_many([{"kind": "text", "payload": {"text": "ok"}}, {"kind": "text", "payload": {}}])
    assert store.stats()["total"] == 0


def test_list_filters_and_mark_trained(store):
    t = store.add("text", {"text": "Shipping is free over 500 rupees."}, tags=["shipping"]).entry
    store.add("text", {"text": "Returns take 7 days."}, tags=["returns"])
    assert [e["id"] for e in store.list(tags=["shipping"])[0]] == [t["id"]]
    assert store.mark_trained([t["id"]], "job1") == 1
    assert store.get(t["id"])["status"] == "trained"
    assert store.list(status="pending")[1] == 1
    assert store.stats()["by_status"] == {"pending": 1, "trained": 1}


def test_build_dataset(store, tmp_path):
    store.add("qa", {"question": "Hi?", "answer": "Hello."})
    entries = store.select()
    ds = build_dataset(entries, tmp_path / "ds", base_text="Base corpus.", repeat=2)
    text = ds.train_file.read_text()
    assert text.startswith("Base corpus.\n") and text.count("User: Hi?\nChit: Hello.\n") == 2
    assert json.loads(ds.manifest_file.read_text())["entry_ids"] == [entries[0]["id"]]
    with pytest.raises(ValueError):
        build_dataset(entries, tmp_path / "ds2", repeat=1, max_bytes=5)
