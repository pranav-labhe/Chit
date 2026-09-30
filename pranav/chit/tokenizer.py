"""Byte-level tokenizer: every UTF-8 byte is one token (vocab size 256)."""
from __future__ import annotations

from typing import Iterable


class ByteTokenizer:
    """Simple byte-level tokenizer. No external pretrained tokenizer is needed."""

    name = "byte-utf8"
    vocab_size = 256

    def encode(self, text: str) -> list[int]:
        # "surrogatepass" keeps lone surrogates (which can come from bad JSON input)
        # from crashing encoding; they are decoded back as replacement characters.
        return list(text.encode("utf-8", errors="surrogatepass"))

    def decode(self, ids: Iterable[int]) -> str:
        data = bytes(int(i) for i in ids)  # raises ValueError for ids outside 0..255
        return data.decode("utf-8", errors="replace")
