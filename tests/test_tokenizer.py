import pytest

from pranav.chit.tokenizer import BpeTokenizer, ByteTokenizer


def test_roundtrip():
    t = ByteTokenizer()
    s = "Atmini नमस्ते"
    assert t.decode(t.encode(s)) == s


def test_lone_surrogate_does_not_crash():
    t = ByteTokenizer()
    assert t.decode(t.encode("a\ud800b")).startswith("a")


def test_out_of_range_id_is_an_error():
    with pytest.raises(ValueError):
        ByteTokenizer().decode([300])


def test_bpe_unicode_roundtrip_and_serialized_asset():
    tokenizers = pytest.importorskip("tokenizers")
    from tokenizers import decoders, models, pre_tokenizers, trainers

    inner = tokenizers.Tokenizer(models.BPE(unk_token=None))
    inner.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    inner.decoder = decoders.ByteLevel()
    inner.train_from_iterator(["hello नमस्ते 🌍 שלום 👩‍💻", "hello world"],
                              trainers.BpeTrainer(vocab_size=300, min_frequency=1,
                                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
                                                  special_tokens=[]))
    tokenizer = BpeTokenizer(inner)
    source = "नमस्ते 🌍 שלום 👩‍💻"
    assert tokenizer.decode(tokenizer.encode(source)) == source
    restored = BpeTokenizer.from_asset(tokenizer.asset)
    assert restored.asset_sha256 == tokenizer.asset_sha256
    assert restored.decode(restored.encode(source)) == source
