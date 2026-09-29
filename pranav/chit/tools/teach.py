"""Bulk-load knowledge from a JSONL file into the knowledge store (offline).

Each line is one entry, the same shape as an item of POST /knowledge:
    {"kind": "qa", "question": "...", "answer": "...", "tags": ["faq"]}
    {"kind": "text", "text": "..."}
    {"kind": "reasoning", "input": "...", "reasoning": "...", "answer": "..."}
Lines without "kind" take --kind. The whole file is added atomically.

    python -m pranav.chit.tools.teach data/reasoning.jsonl --kind reasoning
"""
import argparse
import json
import sys

from ..knowledge import KINDS, KnowledgeError, KnowledgeStore


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file")
    p.add_argument("--kind", choices=tuple(KINDS), help="default kind for lines without one")
    p.add_argument("--db", default="data/knowledge.db")
    p.add_argument("--tag", action="append", default=[], help="tag added to every entry (repeatable)")
    p.add_argument("--source", help="source recorded on every entry (default: the file name)")
    a = p.parse_args(argv)

    items = []
    try:
        with open(a.file, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                kind = row.pop("kind", a.kind)
                tags = row.pop("tags", []) + a.tag
                row.pop("id", None)  # ids in source files are not knowledge ids
                if kind in KINDS:
                    row = {k: v for k, v in row.items() if k in KINDS[kind]}
                items.append({"kind": kind, "payload": row, "tags": tags, "source": a.source or a.file})
        results = KnowledgeStore(a.db).add_many(items)
    except (OSError, json.JSONDecodeError, KnowledgeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    created = sum(r.created for r in results)
    print(f"added {created}, skipped {len(results) - created} duplicate(s) -> {a.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
