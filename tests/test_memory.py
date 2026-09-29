from pranav.chit.memory import MemoryStore
def test_memory(tmp_path):
    s=MemoryStore(tmp_path/'memory.json'); s.add('Pranav is building Chit.'); assert s.search('Chit')
