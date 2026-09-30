import pytest

from pranav.chit.tokenizer import ByteTokenizer


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
