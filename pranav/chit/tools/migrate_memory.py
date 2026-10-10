"""Validate or import legacy memory JSON into the SQLite memory database."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..memory import SQLiteMemoryStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="legacy memory JSON list")
    parser.add_argument("database", type=Path, help="SQLite destination path")
    parser.add_argument("--apply", action="store_true", help="write to SQLite (default is dry-run)")
    parser.add_argument("--backup", type=Path, help="backup destination; defaults to a timestamped copy")
    args = parser.parse_args(argv)

    source_bytes = args.source.read_bytes()
    raw = json.loads(source_bytes.decode("utf-8"))
    if not isinstance(raw, list):
        parser.error("source must contain a JSON list")
    records = [SQLiteMemoryStore._normalize(m) for m in raw]
    ids = [item["id"] for item in records]
    if len(ids) != len(set(ids)):
        parser.error("source contains duplicate memory IDs")
    report = {"source_records": len(records), "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
              "destination": str(args.database), "dry_run": not args.apply}
    if args.apply:
        args.database.parent.mkdir(parents=True, exist_ok=True)
        if args.source.resolve() == args.database.resolve():
            parser.error("source and destination must be different files")
        backup = args.backup or args.source.with_name(
            f"{args.source.name}.backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}")
        if backup.exists():
            parser.error(f"backup already exists: {backup}")
        shutil.copy2(args.source, backup)
        store = SQLiteMemoryStore(args.database, seed_path=None)
        store.import_json(args.source)
        missing = [mid for mid in ids if store.get(mid) is None]
        if missing:
            parser.error(f"import verification failed: {len(missing)} source record(s) missing")
        report.update(destination_records=store.count(), backup=str(backup), verified=True)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
