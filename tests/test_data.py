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
