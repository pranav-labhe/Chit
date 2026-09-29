from pranav_mati.memory import MemoryStore
def test_memory(tmp_path):
    s=MemoryStore(tmp_path/'memory.json'); s.add('Pranav is building Mati.'); assert s.search('Mati')
