"""Restore a checkpoint retained by promote_candidate.py."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ..promotion_state import file_sha256, install_checkpoint, recover_promotion
from ..runtime import ChitRuntime


def _sha256(path: Path) -> str:
    return file_sha256(path)


def rollback(target: Path, to_sha256: str) -> dict:
    recover_promotion(target)
    manifest_path = target.parent / "champion.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive = target.parent / "champions" / f"{to_sha256}.pt"
    if not archive.is_file() or _sha256(archive) != to_sha256:
        raise ValueError("requested rollback checkpoint is missing or its hash does not match")
    ChitRuntime.from_checkpoint(archive)
    current_hash = _sha256(target)
    manifest["previous"] = manifest.get("current")
    manifest["current"] = {"sha256": to_sha256, "checkpoint": str(archive), "evaluation": None}
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest.setdefault("history", []).append({"at": manifest["updated_at"], "from": current_hash,
                                               "to": to_sha256, "reason": "operator rollback"})
    current_archive = target.parent / "champions" / f"{current_hash}.pt"
    if not current_archive.exists():
        import shutil
        shutil.copy2(target, current_archive)
    install_checkpoint(target, archive, source_sha256=to_sha256,
                       previous_sha256=current_hash, previous_archive=current_archive,
                       manifest=manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("checkpoints/latest.pt"))
    parser.add_argument("--to-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(rollback(args.target, args.to_sha256), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
