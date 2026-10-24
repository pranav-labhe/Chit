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


def test_record_starts_and_answer_only_loss_masking():
    text = (
        "Task: chat\nUser: Hello!\nChit: Hi there, how can I help?\n\n"
        "Task: reasoning\nInput: 2 + 2\nReasoning: Add two and two.\nAnswer: 4\n\n"
        "Task: prose\nSunlight warmed the quiet garden path.\n"
    )
    dataset = TextDataset.from_text(text, ByteTokenizer(), block_size=64)
    assert len(dataset.record_starts) >= 3
    assert int(dataset.record_starts[0].item()) == 0

    x, y = random_batch(
        dataset,
        batch_size=8,
        device="cpu",
        generator=torch.Generator().manual_seed(7),
        block_size=64,
    )
    assert (y == -100).any(), "Prompt header tokens before Chit:/Reasoning: should be masked with -100"
    assert (y != -100).any(), "Completion tokens after Chit:/Reasoning: must remain unmasked"


def test_subword_pretokenized_mmap_parity(tmp_path):
    pytest.importorskip("tokenizers")
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
    from pranav.chit.pretokenize import pretokenize_source
    from pranav.chit.tokenizer import BpeTokenizer

    inner = Tokenizer(models.BPE(unk_token=None))
    inner.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    inner.decoder = decoders.ByteLevel()
    corpus = ["hello\r\n   def foo():\r\n       return 42"] * 10
    inner.train_from_iterator(corpus, trainers.BpeTrainer(vocab_size=300, min_frequency=1,
                                                          initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
                                                          special_tokens=[]))
    tok = BpeTokenizer(inner)

    # Test CRLF, multi-spaces, and absence of trailing newline using raw bytes (avoiding OS newline translation)
    test_bytes = b"hello\r\n   def foo():\r\n       return 42"
    f = tmp_path / "sample.txt"
    f.write_bytes(test_bytes)

    manifest = pretokenize_source(f, tok)
    expected_ids = tok.encode(f.read_text(encoding="utf-8"))
    assert manifest["token_count"] == len(expected_ids)

    # Load via memory-mapped TextDataset
    ds = TextDataset(f, tok, block_size=4)
    assert ds.data.tolist() == expected_ids


def test_subword_pretokenized_validation_and_tamper_detection(tmp_path):
    pytest.importorskip("tokenizers")
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
    from pranav.chit.pretokenize import pretokenize_source
    from pranav.chit.tokenizer import BpeTokenizer

    inner = Tokenizer(models.BPE(unk_token=None))
    inner.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    inner.decoder = decoders.ByteLevel()
    inner.train_from_iterator(["hello world testing tokens"] * 5,
                              trainers.BpeTrainer(vocab_size=300, min_frequency=1,
                                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
                                                  special_tokens=[]))
    tok = BpeTokenizer(inner)

    f = tmp_path / "tamper_test.txt"
    f.write_text("hello world testing tokens " * 5, encoding="utf-8")
    pretokenize_source(f, tok)

    # 1. Valid artifact loads cleanly
    ds = TextDataset(f, tok, block_size=4)
    assert len(ds.data) > 4
    del ds
    import gc
    gc.collect()

    # 2. Missing artifact raises FileNotFoundError when allow_fallback=False
    f_missing = tmp_path / "no_artifact.txt"
    f_missing.write_text("hello world testing tokens " * 5, encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Missing pre-tokenized subword artifact"):
        TextDataset(f_missing, tok, block_size=4, allow_fallback=False)

    # 3. Missing artifact with allow_fallback=True loads via in-memory fallback
    ds_fb = TextDataset(f_missing, tok, block_size=4, allow_fallback=True)
    assert len(ds_fb.data) > 4

    # 4. Modifying source text triggers source hash mismatch
    f.write_text("hello world testing modified text " * 5, encoding="utf-8")
    with pytest.raises(ValueError, match="Source file hash mismatch"):
        TextDataset(f, tok, block_size=4)
    # Restore
    f.write_text("hello world testing tokens " * 5, encoding="utf-8")

    # 5. Modifying binary artifact (same-size bit flip) triggers checksum corruption detection
    bin_file = f.with_name(f"{f.name}.bpe.bin")
    raw_bin = bytearray(bin_file.read_bytes())
    raw_bin[0] = (raw_bin[0] + 1) % 256
    bin_file.write_bytes(raw_bin)
    with pytest.raises(ValueError, match="Binary artifact checksum corruption detected"):
        TextDataset(f, tok, block_size=4)

    # 6. Truncating binary artifact triggers size mismatch
    bin_file.write_bytes(raw_bin[:len(raw_bin) - 4])
    with pytest.raises(ValueError, match="Binary artifact size mismatch"):
        TextDataset(f, tok, block_size=4)


def test_subword_manifest_contract_strictness(tmp_path):
    pytest.importorskip("tokenizers")
    import json
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
    from pranav.chit.pretokenize import pretokenize_source
    from pranav.chit.tokenizer import BpeTokenizer

    inner = Tokenizer(models.BPE(unk_token=None))
    inner.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    inner.decoder = decoders.ByteLevel()
    inner.train_from_iterator(["hello contract test tokens"] * 5,
                              trainers.BpeTrainer(vocab_size=300, min_frequency=1,
                                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
                                                  special_tokens=[]))
    tok = BpeTokenizer(inner)

    f = tmp_path / "contract_test.txt"
    f.write_text("hello contract test tokens " * 5, encoding="utf-8")
    manifest = pretokenize_source(f, tok)
    manifest_path = f.with_name(f"{f.name}.bpe.manifest.json")

    # 1. Non-dict JSON raises ValueError
    manifest_path.write_text("[\"not\", \"an\", \"object\"]", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid manifest structure.*expected JSON object"):
        TextDataset(f, tok, block_size=4)

    # 2. Unsupported version
    manifest_path.write_text(json.dumps({**manifest, "version": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported manifest version '2'"):
        TextDataset(f, tok, block_size=4)

    # 3. Unsupported dtype
    manifest_path.write_text(json.dumps({**manifest, "dtype": "float32"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported artifact dtype 'float32'"):
        TextDataset(f, tok, block_size=4)

    # 4. Tokenizer name mismatch
    manifest_path.write_text(json.dumps({**manifest, "tokenizer_name": "different-tok"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Tokenizer name mismatch"):
        TextDataset(f, tok, block_size=4)

    # 5. Invalid token_count (non-int or negative)
    manifest_path.write_text(json.dumps({**manifest, "token_count": "many"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid token_count in manifest"):
        TextDataset(f, tok, block_size=4)

    # 6. Invalid hash format (not 64-char hex)
    manifest_path.write_text(json.dumps({**manifest, "artifact_sha256": "bad-hash"}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid artifact_sha256"):
        TextDataset(f, tok, block_size=4)

