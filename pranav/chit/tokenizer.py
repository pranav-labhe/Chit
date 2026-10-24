"""Byte-level tokenizer: every UTF-8 byte is one token (vocab size 256)."""
from __future__ import annotations

import hashlib
from pathlib import Path
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


LEGACY_TOKENIZER_ALIASES: dict[str, str] = {
    "data/tokenizers/chit-bpe-v1.json": "checkpoints/tokenizers/chit-bpe-v1.json",
}


class BpeTokenizer:
    """Tokenizer backed by an immutable Hugging Face ``tokenizer.json`` asset."""

    name = "bpe-tokenizers-json-v1"

    def __init__(self, tokenizer):
        self._tokenizer = tokenizer
        self.vocab_size = tokenizer.get_vocab_size(with_added_tokens=True)
        self.asset = tokenizer.to_str(pretty=False)
        self.asset_sha256 = hashlib.sha256(self.asset.encode("utf-8")).hexdigest()

    @classmethod
    def from_file(cls, path: str):
        try:
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise RuntimeError("BPE support requires the optional 'bpe' dependencies") from exc
        target = Path(path)
        if not target.is_file():
            alias = LEGACY_TOKENIZER_ALIASES.get(str(path).replace("\\", "/"))
            if alias and Path(alias).is_file():
                target = Path(alias)
            else:
                raise FileNotFoundError(f"tokenizer asset file not found: {path}")
        try:
            return cls(Tokenizer.from_file(str(target)))
        except Exception as exc:
            raise OSError(f"cannot load tokenizer from {target}: {exc}") from exc

    @classmethod
    def from_asset(cls, asset: str):
        try:
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise RuntimeError("BPE support requires the optional 'bpe' dependencies") from exc
        return cls(Tokenizer.from_str(asset))

    def encode(self, text: str) -> list[int]:
        try:
            return self._tokenizer.encode(text, add_special_tokens=False).ids
        except Exception as exc:
            raise RuntimeError(f"BPE token encoding failed: {exc}") from exc

    def decode(self, ids: Iterable[int]) -> str:
        try:
            return self._tokenizer.decode([int(i) for i in ids], skip_special_tokens=False)
        except Exception as exc:
            raise RuntimeError(f"BPE token decoding failed: {exc}") from exc


def create_tokenizer(name: str = ByteTokenizer.name, model_file: str | None = None,
                     asset: str | None = None):
    if name == ByteTokenizer.name:
        return ByteTokenizer()
    if name == BpeTokenizer.name:
        if asset is not None:
            return BpeTokenizer.from_asset(asset)
        if model_file:
            return BpeTokenizer.from_file(model_file)
        raise ValueError("BPE tokenizer requires a tokenizer asset or model_file")
    raise ValueError(f"unsupported tokenizer {name!r}")
