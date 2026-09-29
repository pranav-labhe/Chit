# Changelog

## 0.2.0

### Added
- **Knowledge API** (`/knowledge`, `/knowledge/train`): teach Chit text, Q&A and
  reasoning examples; they are stored in SQLite and used for training only when
  requested. Entries are deduplicated, tagged, auditable, and marked `trained`
  once a promoted run has learned them. Optional `remember` makes an item usable
  by `/chat` immediately via memory. See `docs/KNOWLEDGE_API.md`.
- **Fine-tuning**: `init: scratch | current | auto` on `/train` and
  `/knowledge/train`, and `--init` on the CLI. Starting weights are snapshotted
  into the job directory for reproducibility.
- Learning-rate warmup and cosine schedule (`warmup_steps`, `lr_schedule`, `min_lr_ratio`).
- `GET /model`, `DELETE /memory/{id}`, `stop` sequences on `/generate`,
  greedy decoding (`temperature: 0`).
- `python -m pranav.chit.tools.teach` for bulk JSONL import.
- Job history reloads after a restart; jobs interrupted by a crash show as `failed`.
- Checkpoints record format version, tokenizer, full config, total steps,
  best eval loss and job metadata (including the dataset hash).
- Export writes a SHA-256 of the weights and drops optimizer state.

### Changed
- Attention uses `scaled_dot_product_attention` (fused kernels, less memory);
  outputs are identical, and v0.1 checkpoints still load.
- Configs reject unknown keys and out-of-range values.
- Batching is vectorised; `generate` no longer leaves the model in eval mode.
- Memory writes are atomic and locked; search ignores stopwords and ranks by
  overlap, importance, then recency.
- `/memory` works before any model is trained, and memory is shared across
  model reloads (previously a promotion silently swapped in a new memory object).
- `/chat` stops at the end of Chit's turn instead of running on.
- CLI tools return non-zero exit codes with readable errors.
- `.gitignore` excludes checkpoints, exports, memory and the knowledge database.
- Dev dependencies split into `requirements-dev.txt`; `pyproject.toml` added.
