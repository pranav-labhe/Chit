import pytest
import torch

from pranav.chit.data import TextDataset, random_batch
from pranav.chit.tokenizer import ByteTokenizer


def test_byte_corpus_stays_packed_and_batches_become_embedding_indices(tmp_path):
    text = "English, हिन्दी, संस्कृत। " * 12
    path = tmp_path / "corpus.txt"
    path.write_text(text, encoding="utf-8")

    dataset = TextDataset(path, ByteTokenizer(), block_size=12)
    assert dataset.data.dtype == torch.uint8
    assert bytes(dataset.data.tolist()) == text.encode("utf-8")

    inputs, targets = random_batch(dataset, batch_size=3, device="cpu", generator=torch.Generator().manual_seed(2))
    assert inputs.dtype == targets.dtype == torch.long
    assert inputs.shape == targets.shape == (3, 12)
    assert torch.equal(inputs[:, 1:], targets[:, :-1])


def test_byte_corpus_still_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "invalid.txt"
    path.write_bytes(b"valid prefix " + bytes([0xFF]) * 8)
    with pytest.raises(UnicodeDecodeError):
        TextDataset(path, ByteTokenizer(), block_size=4)


def test_random_batch_supports_shorter_curriculum_window():
    dataset = TextDataset.from_text("0123456789abcdef" * 4, ByteTokenizer(), block_size=12)
    x, y = random_batch(dataset, 3, "cpu", generator=torch.Generator().manual_seed(1), block_size=5)
    assert x.shape == y.shape == (3, 5)
    assert torch.equal(x[:, 1:], y[:, :-1])


def test_bpe_dataset_keeps_token_ids_above_byte_range():
    tokenizers = pytest.importorskip("tokenizers")
    from tokenizers import decoders, models, pre_tokenizers, trainers
    from pranav.chit.tokenizer import BpeTokenizer

    inner = tokenizers.Tokenizer(models.BPE(unk_token=None))
    inner.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    inner.decoder = decoders.ByteLevel()
    inner.train_from_iterator(["hello world नमस्ते 🌍"] * 5,
                              trainers.BpeTrainer(vocab_size=300, min_frequency=1,
                                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
                                                  special_tokens=[]))
    tokenizer = BpeTokenizer(inner)
    text = "hello world नमस्ते 🌍 " * 4
    dataset = TextDataset.from_text(text, tokenizer, block_size=4)
    assert dataset.data.max().item() > 255
    x, y = random_batch(dataset, 2, "cpu", block_size=4)
    assert x.shape == y.shape == (2, 4)
