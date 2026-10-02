"""Train an immutable byte-level BPE tokenizer asset from a corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


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
        from tokenizers import Tokenizer, models, pre_tokenizers, decoders, trainers
    except ImportError:
        parser.error("install BPE support with: pip install '.[bpe]'")

    tokenizer = Tokenizer(models.BPE(unk_token=None))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(vocab_size=args.vocab_size, min_frequency=2,
                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
                                  special_tokens=[], show_progress=True)
    tokenizer.train([str(args.corpus.resolve())], trainer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(args.output))
    from ..tokenizer import BpeTokenizer
    asset_hash = BpeTokenizer(tokenizer).asset_sha256
    print(json.dumps({"tokenizer": "bpe-tokenizers-json-v1", "path": str(args.output),
                      "vocab_size": tokenizer.get_vocab_size(with_added_tokens=True),
                      "checkpoint_asset_sha256": asset_hash}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
