import threading

from pranav.chit.memory import MemoryStore


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
