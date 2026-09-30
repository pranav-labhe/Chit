"""Split a text corpus into training and evaluation files (offline).

    python -m pranav.chit.tools.split corpus.txt
    python -m pranav.chit.tools.split corpus.txt --by paragraph --eval-fraction 0.08 --block-size 128

Blank lines and exact duplicates (ignoring case and extra spaces) are removed, the
rest is shuffled with a fixed seed, and about ``--eval-fraction`` of it is held out
for ``data/eval.txt``. No item appears in both files, so the eval loss is honest.

``--by paragraph`` keeps blocks separated by blank lines together, so a
``User:`` / ``Chit:`` pair is never split across the two files.

Existing outputs are never overwritten unless you pass ``--force`` (the old files
are then kept as ``*.bak``). The same logic is available over HTTP as POST /data/split.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..datasets import MIN_USEFUL_EVAL_BYTES, backup, join_items, split_corpus, write_text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="text file to split (UTF-8)")
    p.add_argument("--by", choices=("line", "paragraph"), default="line", help="what counts as one item")
    p.add_argument("--eval-fraction", type=float, default=0.1, help="share of items held out (default 0.1)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--train-out", default="data/train.txt")
    p.add_argument("--eval-out", default="data/eval.txt")
    p.add_argument("--block-size", type=int, help="model.block_size; both files must be larger than this")
    p.add_argument("--force", action="store_true", help="overwrite existing output files (keeps *.bak)")
    a = p.parse_args(argv)

    if not 0 < a.eval_fraction < 0.5:
        p.error("--eval-fraction must be between 0 and 0.5")
    try:
        text = Path(a.source).read_text(encoding="utf-8")
        res = split_corpus(text, a.by, a.eval_fraction, a.seed)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    train_text, eval_text = join_items(res.train, a.by), join_items(res.eval, a.by)
    train_bytes, eval_bytes = len(train_text.encode("utf-8")), len(eval_text.encode("utf-8"))
    if a.block_size is not None and min(train_bytes, eval_bytes) <= a.block_size:
        print(f"error: train ({train_bytes} bytes) and eval ({eval_bytes} bytes) must both be larger than "
              f"block_size {a.block_size}. Add more text or raise --eval-fraction.", file=sys.stderr)
        return 2
    existing = [f for f in (a.train_out, a.eval_out) if Path(f).exists()]
    if existing and not a.force:
        print(f"error: {', '.join(existing)} already exists; pass --force to overwrite", file=sys.stderr)
        return 2

    try:
        for f in existing:
            backup(f)
        write_text(a.train_out, train_text)
        write_text(a.eval_out, eval_text)
    except OSError as e:
        print(f"error: could not write output: {e}", file=sys.stderr)
        return 2
    print(f"train: {len(res.train)} items, {train_bytes} bytes -> {a.train_out}")
    print(f"eval:  {len(res.eval)} items, {eval_bytes} bytes -> {a.eval_out}")
    if res.duplicates_removed:
        print(f"removed {res.duplicates_removed} duplicate item(s)")
    if existing:
        print("previous files kept as *.bak")
    if eval_bytes < MIN_USEFUL_EVAL_BYTES:
        print(f"warning: eval is under {MIN_USEFUL_EVAL_BYTES} bytes, so the eval loss will be noisy; "
              "add more text.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
