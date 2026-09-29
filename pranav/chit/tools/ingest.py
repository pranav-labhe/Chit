"""Ingest PDF/TXT/MD/text into the existing Chit Teach API.

Example:
    python -m pranav.chit.tools.ingest book.pdf --api-key "$CHIT_API_KEY"

The utility extracts and chunks material, then sends normal POST /knowledge
batches. It does not create a second teaching architecture.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from ..ingest import knowledge_items


def _post(url: str, api_key: str, items: list[dict]) -> dict:
    data = json.dumps({"items": items}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Teach API returned HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach Teach API: {e.reason}") from e


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source")
    p.add_argument("--url", default="http://127.0.0.1:8000/knowledge")
    p.add_argument("--api-key", default=os.environ.get("CHIT_API_KEY"))
    p.add_argument("--chunk-chars", type=int, default=4000)
    p.add_argument("--overlap", type=int, default=400)
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--dry-run", action="store_true", help="write JSONL to stdout instead of calling the API")
    a = p.parse_args(argv)

    if not a.dry_run and not a.api_key:
        p.error("--api-key or CHIT_API_KEY is required unless --dry-run is used")
    if not 1 <= a.batch_size <= 500:
        p.error("--batch-size must be between 1 and 500")

    try:
        items = knowledge_items(a.source, chunk_chars=a.chunk_chars, overlap=a.overlap, tags=a.tag)
        if a.dry_run:
            for item in items:
                print(json.dumps(item, ensure_ascii=False))
            print(f"generated {len(items)} knowledge chunk(s)", file=sys.stderr)
            return 0

        created = duplicates = 0
        for start in range(0, len(items), a.batch_size):
            result = _post(a.url, a.api_key, items[start:start + a.batch_size])
            created += int(result.get("created", 0))
            duplicates += int(result.get("duplicates", 0))
        print(f"ingested {len(items)} chunk(s): created {created}, duplicates {duplicates}")
        return 0
    except (OSError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
