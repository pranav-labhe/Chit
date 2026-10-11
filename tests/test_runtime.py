import torch

from pranav.chit.memory import MemoryStore
from pranav.chit.model import ChitModel
from pranav.chit.runtime import ChitRuntime


def test_loads_legacy_checkpoint_without_tokenizer_metadata(tmp_path):
    config = {"vocab_size": 256, "block_size": 8, "n_layer": 1, "n_head": 2,
              "n_embd": 8, "dropout": 0.0}
    model = ChitModel(**config)
    checkpoint = tmp_path / "legacy.pt"
    torch.save({"model": model.state_dict(), "model_config": config}, checkpoint)
    runtime = ChitRuntime.from_checkpoint(checkpoint, device="cpu",
                                         memory=MemoryStore(tmp_path / "memory.json", seed_path=None))
    assert runtime.tokenizer.name == "byte-utf8"
    assert runtime.model.position_encoding == "absolute"
    assert runtime.generate("hi", max_new_tokens=1, temperature=0)  # legacy path serves inference


def test_checkpoint_runtime_has_default_memory_store(tmp_path):
    config = {"vocab_size": 256, "block_size": 8, "n_layer": 1, "n_head": 2,
              "n_embd": 8, "dropout": 0.0}
    model = ChitModel(**config)
    checkpoint = tmp_path / "standalone.pt"
    torch.save({"model": model.state_dict(), "model_config": config}, checkpoint)

    runtime = ChitRuntime.from_checkpoint(checkpoint, device="cpu")

    assert isinstance(runtime.memory, MemoryStore)


def test_early_stopping_halts_and_strips_stop_sequence(tmp_path):
    config = {"vocab_size": 256, "block_size": 32, "n_layer": 1, "n_head": 2,
              "n_embd": 8, "dropout": 0.0}
    model = ChitModel(**config)
    checkpoint = tmp_path / "model.pt"
    torch.save({"model": model.state_dict(), "model_config": config}, checkpoint)
    runtime = ChitRuntime.from_checkpoint(checkpoint, device="cpu")

    # Mock model.generate to verify early-stopping invocation:
    original_generate = runtime.model.generate
    call_counts = []

    def mock_generate(idx, max_new_tokens, temperature=0.8, top_k=50, generator=None,
                      stop_fn=None, repetition_penalty=1.0, *args, **kwargs):
        # Emulate token-by-token generation where token 10 corresponds to '\n'
        # and subsequent tokens emit "User:"
        stop_seq = b"\nUser:"
        for b in stop_seq:
            idx = torch.cat((idx, torch.tensor([[b]])), dim=1)
            call_counts.append(b)
            if stop_fn and stop_fn(idx):
                break
        return idx

    runtime.model.generate = mock_generate
    res = runtime.generate("Hello", max_new_tokens=100, stop=["\nUser:"])
    assert res == ""  # everything up to \nUser: (which was immediately emitted) is stripped
    assert len(call_counts) == len(b"\nUser:")  # stopped at exactly 6 tokens instead of 100!


def test_early_stopping_preserves_multibyte_utf8_boundaries(tmp_path):
    config = {"vocab_size": 256, "block_size": 32, "n_layer": 1, "n_head": 2,
              "n_embd": 8, "dropout": 0.0}
    model = ChitModel(**config)
    checkpoint = tmp_path / "model.pt"
    torch.save({"model": model.state_dict(), "model_config": config}, checkpoint)
    runtime = ChitRuntime.from_checkpoint(checkpoint, device="cpu")

    hindi_word = "नमस्ते"  # 18 UTF-8 bytes in Devanagari
    stop_marker = "\nUser:"
    payload_bytes = hindi_word.encode("utf-8") + stop_marker.encode("utf-8")

    def mock_generate(idx, max_new_tokens, temperature=0.8, top_k=50, generator=None,
                      stop_fn=None, repetition_penalty=1.0, *args, **kwargs):
        for b in payload_bytes:
            idx = torch.cat((idx, torch.tensor([[b]])), dim=1)
            if stop_fn and stop_fn(idx):
                break
        return idx

    runtime.model.generate = mock_generate
    res = runtime.generate("Translate: ", max_new_tokens=100, stop=[stop_marker])
    assert res == hindi_word
    assert res.encode("utf-8") == hindi_word.encode("utf-8")


def test_bridge_selects_greedy_when_memories_exist_unless_overridden(tmp_path):
    from pranav.chit.bridge import Bridge, Context

    config = {"vocab_size": 256, "block_size": 64, "n_layer": 1, "n_head": 2,
              "n_embd": 8, "dropout": 0.0}
    model = ChitModel(**config)
    checkpoint = tmp_path / "model.pt"
    torch.save({"model": model.state_dict(), "model_config": config}, checkpoint)
    runtime = ChitRuntime.from_checkpoint(checkpoint, device="cpu")

    captured = []
    runtime.recall = lambda q, limit=5, **kwargs: (captured.append(("recall", kwargs)), [{"id": "m1", "content": "fact"}])[1]
    runtime.generate = lambda prompt, n, temp, top_k, **kw: (captured.append(("generate", temp)), "answer")[1]

    bridge = Bridge(runtime)
    # 1. Default caller temperature is None: should switch to 0.0
    bridge.process(Context(user_input="What is the fact?"))
    assert any(c[0] == "recall" and c[1].get("min_relevance") == 0.35 for c in captured)
    assert any(c[0] == "generate" and c[1] == 0.0 for c in captured)

    # 2. Caller explicitly overrides temperature to 0.4: should honor 0.4
    captured.clear()
    bridge.process(Context(user_input="What is the fact?"), temperature=0.4)
    assert any(c[0] == "generate" and c[1] == 0.4 for c in captured)


