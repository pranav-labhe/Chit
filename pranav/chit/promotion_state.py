"""Crash-recovery journal for checkpoint promotion and rollback operations."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temp, path)


def install_checkpoint(target: Path, source: Path, *, source_sha256: str,
                       previous_sha256: str, previous_archive: Path,
                       manifest: dict) -> None:
    """Journal first, atomically swap checkpoint, then commit the champion manifest."""
    journal_path = target.parent / "promotion_transaction.json"
    manifest_path = target.parent / "champion.json"
    manifest_before = (json.loads(manifest_path.read_text(encoding="utf-8"))
                       if manifest_path.exists() else None)
    journal = {"schema_version": 1, "state": "prepared",
               "started_at": datetime.now(timezone.utc).isoformat(),
               "target": str(target), "source": str(source),
               "source_sha256": source_sha256, "previous_sha256": previous_sha256,
               "previous_archive": str(previous_archive), "manifest_before": manifest_before,
               "manifest_after": manifest}
    write_json_atomic(journal_path, journal)
    fd, name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    os.close(fd)
    temp = Path(name)
    try:
        shutil.copy2(source, temp)
        if file_sha256(temp) != source_sha256:
            raise ValueError("candidate hash changed while preparing promotion")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    write_json_atomic(target.parent / "champion.json", manifest)
    journal["state"] = "committed"
    journal["committed_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(journal_path, journal)


def recover_promotion(target: Path) -> dict | None:
    """Finish a prepared swap or restore the old archive before model loading."""
    journal_path = target.parent / "promotion_transaction.json"
    if not journal_path.exists():
        return None
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("state") != "prepared":
        return None
    current_hash = file_sha256(target) if target.exists() else None
    if current_hash == journal["source_sha256"]:
        write_json_atomic(target.parent / "champion.json", journal["manifest_after"])
        journal["state"] = "committed_recovered"
    elif current_hash == journal["previous_sha256"]:
        before = journal.get("manifest_before")
        if before is not None:
            write_json_atomic(target.parent / "champion.json", before)
        journal["state"] = "aborted_recovered"
    else:
        previous = Path(journal["previous_archive"])
        if file_sha256(previous) != journal["previous_sha256"]:
            raise ValueError("promotion recovery failed: previous champion archive is invalid")
        fd, name = tempfile.mkstemp(prefix=target.name + ".recover.", suffix=".tmp", dir=target.parent)
        os.close(fd)
        temp = Path(name)
        try:
            shutil.copyfile(previous, temp)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        before = journal.get("manifest_before")
        if before is not None:
            write_json_atomic(target.parent / "champion.json", before)
        else:
            (target.parent / "champion.json").unlink(missing_ok=True)
        journal["state"] = "restored_recovered"
    journal["recovered_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(journal_path, journal)
    return {"state": journal["state"]}
