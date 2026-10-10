# Changelog

## 0.2.0

### Added
- **Real-Time System Metrics**: `GET /sys_metrics` exposes CPU, Memory, and Disk usage via `psutil`. The UI features a real-time polling traffic-light badge in the header.
- **Universal Page Guides**: All UI views now feature explicit "Page Guide" buttons mapping friendly UI terms directly to exact JSON API payloads and endpoints.
- **Job Configuration Tracking**: The backend now captures the learning plan (`config_name`) inside the training job metadata and displays it directly on the Job Card.
- **Explicit Checkpoint Timestamps**: The Studio UI explicitly tracks and displays the physical file modification timestamps for candidate (`latest.pt` inside job folder) and live (`checkpoints/latest.pt`) models to verify promotions.
- **Golden Gate Integration UI**: Evaluated candidate models now display their explicit Gate Pass / Fail safety metrics on the job cards directly.
- **Training data API** (`GET /data`, `POST /data/split`) and `python -m pranav.chit.tools.split`: check the train/eval files as they are on the server (size, hash, leakage), and split a corpus into held-out train/eval files, with `.bak` backups. See `docs/DATA_API.md`.
- **Chat sessions** (`/sessions`, `session_id` on `/chat`): each conversation keeps its
  turn-by-turn history in SQLite under a session id, and recent turns are sent to the
  model as context, trimmed to fit its context window. See `docs/SESSIONS.md`.
- `task: "continue"` on `/chat` for plain-text models (the message is the start of a
  sentence; no chat wrapper), and an optional `temperature` on `/chat`.
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

### Fixed
- **UI Proxy Route Allowlist**: Registered `GET /sys_metrics` in `ui.ROUTES` so telemetry queries are no longer rejected with HTTP 403/404 by `/_ui/proxy`.
- **Candidates State Matching**: Fixed `GET /candidates` filtering logic to recognize completed jobs with state `"succeeded"`, exposing candidate cards, timestamps, evaluations, and promotion controls in the UI.
- **Timestamp Synchronization**: Added `checkpoint_timestamp` extraction and formatting to `#studioLiveStamp` and candidate cards, with dynamic `(Currently Live AI)` badge matching.
- **Universal Page Guides**: Integrated comprehensive Page Guide dialogs across all 8 UI screens and API reference with precise field and payload mappings.
