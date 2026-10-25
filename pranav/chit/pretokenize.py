"""Offline pre-tokenization utility for subword (BPE) datasets.

Compiles text source files into memory-mappable binary int32 token artifacts
and accompanying SHA-256 manifests to eliminate memory spikes during training
startup on memory-constrained servers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    import tokenizers
except ImportError:
    tokenizers = None  # type: ignore[assignment]

from .config import ChitConfig, load_config
from .tokenizer import create_tokenizer

log = logging.getLogger(__name__)

GENERATOR_VERSION = "1.0"
CHUNK_SIZE = 64 * 1024


def check_dependencies() -> None:
    """Ensure required pre-tokenization libraries are installed with descriptive diagnostics."""
    missing = []
    if np is None:
        missing.append("numpy>=1.26,<3")
    if tokenizers is None:
        missing.append("tokenizers==0.23.2")
    if missing:
        deps = " ".join(f'"{m}"' for m in missing)
        raise RuntimeError(
            f"pranav.chit.pretokenize requires {', '.join(missing)}. "
            f"Install them via: pip install {deps}"
        )


def hash_file_sha256(path: str | os.PathLike) -> str:
    """Compute SHA-256 hex digest of a file streaming in 64 KB blocks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def pretokenize_source(
    source_file: str | os.PathLike,
    tokenizer,
    bin_path: str | os.PathLike | None = None,
    manifest_path: str | os.PathLike | None = None,
    force: bool = False,
) -> dict:
    """Tokenize a single text source and write binary artifact and manifest.

    Publishing is atomic: the binary is written to a temporary file,
    verified, renamed, and the manifest is published last.
    """
    check_dependencies()
    src = Path(source_file)
    if not src.is_file():
        raise FileNotFoundError(f"source file not found: {src}")

    target_bin = Path(bin_path) if bin_path else src.with_name(f"{src.name}.bpe.bin")
    target_manifest = Path(manifest_path) if manifest_path else src.with_name(f"{src.name}.bpe.manifest.json")

    src_sha256 = hash_file_sha256(src)
    tok_sha256 = getattr(tokenizer, "asset_sha256", "")

    # Check if existing artifact is already valid
    if not force and target_bin.is_file() and target_manifest.is_file():
        try:
            with open(target_manifest, "r", encoding="utf-8") as mf:
                m_data = json.load(mf)
            if (
                m_data.get("source_sha256") == src_sha256
                and m_data.get("tokenizer_sha256") == tok_sha256
                and m_data.get("generator_version") == GENERATOR_VERSION
                and target_bin.stat().st_size == m_data.get("token_count", 0) * 4
                and hash_file_sha256(target_bin) == m_data.get("artifact_sha256")
            ):
                log.info("Artifact already up to date: %s", target_bin)
                return m_data
        except Exception:
            pass  # regenerate on any manifest read/validation failure

    # Match TextDataset universal newline decoding
    text = src.read_text(encoding="utf-8")
    ids = tokenizer.encode(text)
    token_count = len(ids)

    target_bin.parent.mkdir(parents=True, exist_ok=True)
    target_manifest.parent.mkdir(parents=True, exist_ok=True)

    # 1. Write binary tokens to temporary file (explicit little-endian int32)
    bin_tmp = target_bin.with_name(f"{target_bin.name}.tmp-{os.getpid()}")
    try:
        token_arr = np.asarray(ids, dtype="<i4")
        with open(bin_tmp, "wb") as bf:
            token_arr.tofile(bf)
        del token_arr
        del ids
        del text

        bin_sha256 = hash_file_sha256(bin_tmp)
        bin_size = bin_tmp.stat().st_size
        if bin_size != token_count * 4:
            raise RuntimeError(f"binary size mismatch: expected {token_count * 4} bytes, got {bin_size}")

        # Atomic replace binary artifact
        os.replace(bin_tmp, target_bin)
    finally:
        if bin_tmp.exists():
            bin_tmp.unlink(missing_ok=True)

    # 2. Build and atomically write manifest last
    import tokenizers
    manifest_data = {
        "version": 1,
        "generator_version": GENERATOR_VERSION,
        "tokenizers_version": getattr(tokenizers, "__version__", "unknown"),
        "source_file": str(src).replace("\\", "/"),
        "source_sha256": src_sha256,
        "source_size_bytes": src.stat().st_size,
        "tokenizer_name": getattr(tokenizer, "name", "bpe-tokenizers-json-v1"),
        "tokenizer_sha256": tok_sha256,
        "artifact_file": target_bin.name,
        "artifact_sha256": bin_sha256,
        "dtype": "int32",
        "token_count": token_count,
    }

    manifest_tmp = target_manifest.with_name(f"{target_manifest.name}.tmp-{os.getpid()}")
    try:
        with open(manifest_tmp, "w", encoding="utf-8") as mf:
            json.dump(manifest_data, mf, indent=2)
        os.replace(manifest_tmp, target_manifest)
    finally:
        if manifest_tmp.exists():
            manifest_tmp.unlink(missing_ok=True)

    log.info("Generated %s (%d tokens, sha256=%s...)", target_bin.name, token_count, bin_sha256[:12])
    return manifest_data


def pretokenize_config(config_path: str | os.PathLike, force: bool = False) -> list[dict]:
    """Pre-tokenize all unique sources referenced in a BPE config file."""
    cfg = load_config(config_path)
    if cfg.tokenizer.name != "bpe-tokenizers-json-v1":
        log.info("Config %s does not use BPE tokenizer; skipping pretokenization.", config_path)
        return []

    tok = create_tokenizer(cfg.tokenizer.name, cfg.tokenizer.model_file)

    # Deduplicate source paths preserving order
    unique_paths: list[Path] = []
    seen: set[str] = set()

    candidate_paths: list[str] = []
    if cfg.data.sources:
        candidate_paths.extend(s.path for s in cfg.data.sources)
    if cfg.data.train_file:
        candidate_paths.append(cfg.data.train_file)
    if cfg.data.eval_file:
        candidate_paths.append(cfg.data.eval_file)

    for p_str in candidate_paths:
        p = Path(p_str)
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            unique_paths.append(p)

    results = []
    for p in unique_paths:
        if not p.is_file():
            raise FileNotFoundError(f"Config {config_path} references non-existent data file: {p}")
        res = pretokenize_source(p, tok, force=force)
        results.append(res)
    return results


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Pre-tokenize BPE text datasets into binary int32 memory-mapped artifacts.")
    parser.add_argument("targets", nargs="+", help="Config JSON files or directories containing configs.")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if manifests and hashes match.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )

    try:
        check_dependencies()
    except RuntimeError as err:
        log.error("%s", err)
        return 1

    configs_to_process: list[Path] = []
    for target_str in args.targets:
        target = Path(target_str)
        if target.is_dir():
            configs_to_process.extend(sorted(p for p in target.rglob("*.json") if p.is_file()))
        elif target.is_file() and target.suffix == ".json":
            configs_to_process.append(target)
        else:
            log.warning("Ignoring invalid target: %s", target)

    if not configs_to_process:
        log.error("No JSON configs found in provided targets.")
        return 1

    total_processed = 0
    for cfg_path in configs_to_process:
        try:
            cfg = load_config(cfg_path)
            if cfg.tokenizer.name == "bpe-tokenizers-json-v1":
                log.info("Processing BPE config: %s", cfg_path)
                res = pretokenize_config(cfg_path, force=args.force)
                total_processed += len(res)
        except Exception as exc:
            log.exception("Error processing config %s: %s", cfg_path, exc)
            return 1

    log.info("Successfully generated/verified %d artifact(s).", total_processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
