"""Train an immutable byte-level BPE tokenizer asset from a corpus."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def train_bpe_tokenizer(
    corpus_files: list[Path],
    output: Path,
    vocab_size: int = 2000,
    *,
    show_progress: bool = False,
) -> dict:
    if vocab_size < 256:
        raise ValueError("vocab size must be at least 256 for byte coverage")
    if not corpus_files:
        raise ValueError("corpus_files must contain at least one file")
    for p in corpus_files:
        if not p.is_file():
            raise FileNotFoundError(f"corpus file does not exist: {p}")

    try:
        from tokenizers import Tokenizer, models, pre_tokenizers, decoders, trainers
    except ImportError as exc:
        raise RuntimeError("install BPE support with: pip install '.[bpe]'") from exc

    tokenizer = Tokenizer(models.BPE(unk_token=None))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=2,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        special_tokens=[],
        show_progress=show_progress,
    )
    tokenizer.train([str(p.resolve()) for p in corpus_files], trainer)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f"{output.name}.tmp-{os.getpid()}")
    tokenizer.save(str(tmp))
    os.replace(tmp, output)

    from ..tokenizer import BpeTokenizer

    asset_hash = BpeTokenizer(tokenizer).asset_sha256
    return {
        "tokenizer": "bpe-tokenizers-json-v1",
        "path": str(output),
        "vocab_size": tokenizer.get_vocab_size(with_added_tokens=True),
        "checkpoint_asset_sha256": asset_hash,
        "files_used": [str(p) for p in corpus_files],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="training-only text corpus; do not include eval data")
    parser.add_argument("output", type=Path, help="output tokenizer.json asset")
    parser.add_argument("--vocab-size", type=int, default=50_000)
    args = parser.parse_args(argv)
    if args.vocab_size < 256:
        parser.error("vocab size must be at least 256 for byte coverage")
    if not args.corpus.is_file():
        parser.error(f"corpus does not exist: {args.corpus}")
    try:
        result = train_bpe_tokenizer([args.corpus], args.output, args.vocab_size, show_progress=True)
    except RuntimeError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
