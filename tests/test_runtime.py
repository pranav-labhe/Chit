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
