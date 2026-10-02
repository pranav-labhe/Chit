import threading

import json

import pytest

from pranav.chit.memory import MemoryStore, SQLiteMemoryStore
from pranav.chit.tools.migrate_memory import main as migrate_memory


def test_memory(tmp_path):
    s = MemoryStore(tmp_path / "memory.json", seed_path=None)
    s.add("Pranav is building Chit.")
    assert s.search("Chit")


def test_stopwords_do_not_match_and_ranking(tmp_path):
    s = MemoryStore(tmp_path / "m.json", seed_path=None)
    s.add("The sky is blue.", importance=0.1)
    s.add("Blue whales are the largest animals.", importance=0.9)
    assert s.search("what is the") == []
    assert [m["content"] for m in s.search("blue")][0].startswith("Blue whales")


def test_delete_and_tags(tmp_path):
    s = MemoryStore(tmp_path / "m.json", seed_path=None)
    m = s.add("Orders ship in two days.", tags=["shipping"])
    assert s.search("ship", tags=["shipping"]) and not s.search("ship", tags=["returns"])
    assert s.delete(m["id"]) and not s.delete(m["id"])


def test_concurrent_adds_are_not_lost(tmp_path):
    s = MemoryStore(tmp_path / "m.json", seed_path=None)
    threads = [threading.Thread(target=s.add, args=(f"fact {i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s.all()) == 20


def test_sqlite_store_keeps_ids_and_cascades_embedding_rows(tmp_path):
    s = SQLiteMemoryStore(tmp_path / "memory.db", seed_path=None)
    item = s.add("A tagged SQLite fact.", tags=["database"], source="test")
    with s._conn() as db:
        db.execute("INSERT INTO memory_embeddings(memory_id,model_version,dimension,vector,status,updated_at) "
                   "VALUES(?,?,?,?,?,?)", (item["id"], "embed-v1", 2, b"\x00", "ready", "now"))
    assert s.get(item["id"]) == item
    assert s.search("SQLite", tags=["database"])[0]["id"] == item["id"]
    assert s.delete(item["id"])
    with s._conn() as db:
        assert db.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0] == 0


def test_json_import_is_dry_runnable_idempotent_and_preserves_duplicate_content(tmp_path):
    source = tmp_path / "legacy.json"
    records = [
        {"id": "one", "type": "fact", "content": "same", "importance": 0.4,
         "tags": ["x"], "created_at": "2024-01-01T00:00:00Z", "source": "a"},
        {"id": "two", "type": "fact", "content": "same", "importance": 0.8,
         "tags": ["y"], "created_at": "2024-01-02T00:00:00Z"},
    ]
    source.write_text(json.dumps(records), encoding="utf-8")
    store = SQLiteMemoryStore(tmp_path / "memory.db", seed_path=None)
    assert store.import_json(source, dry_run=True)["records"] == 2
    assert store.count() == 0
    store.import_json(source)
    store.import_json(source)
    assert store.count() == 2
    assert store.get("one")["source"] == "a"
    assert store.get("two")["tags"] == ["y"]


def test_json_import_rejects_conflicting_ids_without_partial_write(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.db", seed_path=None)
    store.add("original", source="kept")
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps([
        {"id": "new", "content": "would be inserted"},
        {"id": store.all()[0]["id"], "content": "different content"},
    ]), encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        store.import_json(source)
    assert store.count() == 1


class _FakeEmbeddingProvider:
    model_version = "fake-v1"
    dimension = 2

    def encode(self, texts):
        import numpy as np
        vectors = []
        for text in texts:
            value = text.lower()
            vectors.append([1.0, 0.0] if any(w in value for w in ("cat", "feline")) else [0.0, 1.0])
        return np.asarray(vectors, dtype=np.float32)


def test_hybrid_search_finds_paraphrase_and_reindexes_new_version(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.db", seed_path=None,
                              embedding_provider=_FakeEmbeddingProvider(), semantic_threshold=0.5)
    cat = store.add("A cat sleeps on the chair.")
    store.add("The dog runs through the yard.")
    assert store.search("feline", limit=2)[0]["id"] == cat["id"]

    class NewVersion(_FakeEmbeddingProvider):
        model_version = "fake-v2"

    store.embedding_provider = NewVersion()
    report = store.reindex_embeddings(batch_size=1)
    assert report == {"model_version": "fake-v2", "pending": 2, "indexed": 2, "failed": 0}


def test_migration_cli_dry_run_does_not_create_destination_and_apply_backs_up(tmp_path):
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps([{"id": "x", "content": "preserved"}]), encoding="utf-8")
    destination = tmp_path / "out" / "memory.db"
    assert migrate_memory([str(source), str(destination)]) == 0
    assert not destination.exists()
    assert migrate_memory([str(source), str(destination), "--apply"]) == 0
    assert destination.exists()
    assert list(tmp_path.glob("legacy.json.backup-*"))
