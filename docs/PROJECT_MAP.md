# Chit Project Map

This document records the repository structure and runtime behavior reviewed on 2026-10-05. It is a guide to the implementation; when a description conflicts with the code, the current code and active configuration determine behavior.

## What Chit is

Chit is a small decoder-only Transformer trained from scratch to serve as Atmini's language model. It does not call an external language model. The default tokenizer maps each UTF-8 byte to one of 256 token IDs. BPE tokenization and RoPE positional encoding are optional model variants; they require compatible checkpoints and configuration.

The project keeps four kinds of state separate:

| State | Stored in | How it affects responses |
| --- | --- | --- |
| Model weights | `checkpoints/` (served checkpoint defaults to `checkpoints/latest.pt`) | Learned behavior used by generation |
| Memory | SQLite, normally `data/memory.db`; `data/memory.json` is a legacy import/recovery source | Relevant entries are retrieved into assistant prompts without retraining |
| Knowledge | SQLite, normally `data/knowledge.db` | Queued lessons become training data only when a knowledge-training job is requested |
| Sessions | SQLite, normally `data/sessions.db` | Per-conversation history, explicit facts, and derived summaries can be added to `/chat` context |

## Main request paths

### Chat and generation

`POST /chat` and assistant-mode `POST /generate` pass through `api.py` and `Bridge`. The Bridge builds the `Task: chat` / `Known memory:` / `User:` / `Chit:` prompt, retrieves up to five relevant memories, and calls `ChitRuntime`. `/chat` also accepts a session ID, includes recent session context when it fits, and saves the new exchange. Without a supplied session ID, `/chat` starts a session.

`/generate` is a one-shot request by default. Its `mode: "continue"` sends the raw prompt directly to the model. `/chat` has a similar `task: "continue"` path, which does not create or use a session. Generation is admitted through a bounded FIFO inference queue and runs serially per API process/device; overload can return HTTP 429.

Prompt context is constrained by the checkpoint's `block_size`. For byte-tokenizer checkpoints, one model token is one UTF-8 byte. Prompt trimming prioritizes keeping the current message and removes older context to fit.

### Training

`POST /train` loads a named JSON config, validates its architecture and data paths, and starts one background training job. The training loop samples random token windows, applies AdamW updates, evaluates held-out text, and writes checkpoints into a per-job directory. By default API jobs create candidates without replacing the served checkpoint; evaluation and explicit promotion are separate operator steps, with reviewed Golden Set gates and rollback support in the promotion tools. An explicit `force_promote: true` request bypasses those review gates after successful training, installs the candidate, and archives the previous checkpoint.

The CLI entry point is `python -m pranav.chit.tools.train`. The API and CLI have their own defaults, so pass a config explicitly when a particular curriculum is intended.

### Knowledge teaching

`POST /knowledge` queues `text`, `qa`, or `reasoning` entries in SQLite. `POST /knowledge/train` renders selected entries into a job dataset, can mix the config's base `train_file`, and adds the generated knowledge dataset as its own weighted source. A knowledge item becomes immediately retrievable only when also saved into memory (for example, via `remember: true` in the API). Otherwise it can affect generated responses after being learned by a model that is subsequently promoted.

`data/reasoning.jsonl` is **not a default training source** and is not read on each chat or generation request. It is optional bulk-import material for `python -m pranav.chit.tools.teach data/reasoning.jsonl --kind reasoning`. The `load_reasoning_examples()` helper in `pranav/chit/reasoning.py` has no other project callers found during this review.

## Default and named data recipes

The API's default `TrainRequest` config is `chit_cpu_learning`. The CLI training command also defaults to that config (its help text references a legacy `.json` filename, while the checked-in file is `configs/chit_cpu_learning.json`). That recipe uses:

- Training: `data/train.txt`
- Held-out next-token evaluation: `data/eval.txt`

The `chit_assistant_cpu` recipe also uses those two files and is the main assistant-style preset. Other named recipes explicitly select alternate corpora, such as `data/train_1mb.txt`, `data/eval_1mb.txt`, `data/eval_100kb.txt`, or the separate conversation/English foundation sources. Preset selection is what determines the files used; the presence of a data file in the repository does not make it an automatic training input.

The English foundation recipe, `configs/chit_english_foundation.json`, uses four weighted training streams: `structural.txt` (0.3), `lexical_prose.txt` (0.3), `conversation.txt` (0.3), and `project_facts.txt` (0.1). The existing `data/eval.txt` remains its held-out loss file. Source-aware sampling selects each training sequence from one source, so byte size alone does not set the source mix.

`data/prompts_1mb.txt` is a standalone challenge/review prompt bank, not an automatic training source. The 1 MiB and 100 KiB evaluation files are selected by their respective configs and are read for evaluation, not used for optimizer updates. `data/golden_set.json` is a separate behavioral acceptance set and should remain out of training inputs.

The large corpus files and saved baseline copies were inventoried by role and configuration; not every generated example was read individually. The English foundation expansion is synthetic and documented in `docs/benchmarks/english-foundation-data2-expansion-2026-10-04.md`.

## Model, data, and evaluation modules

| Area | Primary files | Responsibility |
| --- | --- | --- |
| Transformer | `pranav/chit/model.py` | Causal self-attention, MLP blocks, absolute or RoPE positions, generation, checkpoint compatibility |
| Tokenization | `tokenizer.py` | UTF-8 byte tokenizer and optional serialized BPE tokenizer |
| Dataset windows | `data.py` | Reads corpus bytes/tokens and produces next-token training batches |
| Training configuration | `config.py` | Typed, range-checked configs; rejects unknown fields |
| Training loop | `training.py` | Seeding, context curriculum, learning-rate schedule, optimizer, evaluation loss, atomic checkpoint writes |
| Job lifecycle | `jobs.py` | Background job state, cancellation, persisted job records, automatic per-checkpoint language evaluation |
| Evaluation | `tools/eval_runner.py`, `tools/english_eval.py` | Held-out bits/byte and perplexity plus generated behavioral responses and hash-bound human ratings |
| Promotion | `tools/promote_candidate.py`, `promotion_state.py`, `tools/rollback_champion.py` | Gate checks, atomic checkpoint installation, journal-based recovery, champion history and rollback |
| Dataset inspection/splitting | `datasets.py`, `tools/split.py`, `/data` API | Deduplicated train/eval splitting, backups, hashes, size and overlap checks |

Training loss measures next-token prediction; it does not by itself demonstrate useful assistant behavior. The Golden Set has 50 cases across five categories and requires independent human review under `docs/GOLDEN_SET.md`. The English foundation suite is a separate draft that also needs review.

## Memory and conversation context

`memory.py` provides a legacy JSON store and the API's SQLite store. SQLite is canonical; FTS5 supplies lexical candidates. Optional local sentence-transformer embeddings and a rebuildable FAISS HNSW index can add semantic candidates. Exact search remains available when optional dependencies or index files are absent. No remote embedding download is performed by the provider.

`sessions.py` stores ordered user/assistant turns, explicit extracted facts, and summary state. `facts.py` extracts only a narrow set of direct English statements and ignores quoted/code spans. `summarization.py` creates bounded extractive summaries in a background worker; it does not ask the small language model to invent a summary. Session facts and summaries are separate from global memory and model weights.

## API and browser console

`pranav/chit/api.py` is the FastAPI service. It owns runtime startup, authentication, memory/knowledge/session stores, training endpoints, and data endpoints. `/health` is public. When an API key is configured, ordinary protected routes require `X-API-Key`; training, knowledge, and data-management routes are disabled without a key unless the local-development opt-in is enabled.

`pranav/chit/ui.py` serves the browser console and proxies requests to the API. The browser keeps an opaque session cookie; the API key stays server-side. `ui/templates/index.html`, `ui/static/js/app.js`, and `ui/static/css/style.css` implement the screens. The UI's documented-route catalog is also a proxy allowlist. The console exposes chat, generation, memory/knowledge workflows, training controls, and API exploration; bulk JSONL teaching is documented as a CLI workflow.

Run both API and console with `python -m pranav.chit.ui`. The supported process topology is one Uvicorn worker because model, inference queue, and job registry are process-local.

## Repository layout

- `pranav/chit/`: service implementation, API, runtime, model, stores, and CLI tools.
- `configs/`: named model/training/data recipes.
- `data/`: base corpora, review corpora, source datasets, SQLite state, and corpus notes.
- `docs/`: architecture, APIs, operations, evaluation, roadmap, deployment guidance, and benchmark records.
- `tests/`: focused tests for configuration, model, tokenization, data, memory, knowledge, sessions, API, training, evaluation, and UI security.
- `scripts/`: reproducible corpus-generation helpers used for the dataset expansions.
- `Containerfile` and `compose.yaml`: CPU-oriented container build and local deployment configuration; the API and UI bind to localhost by default in Compose.

## Important implementation/documentation distinction

Some older guides describe successful training as automatically serving the new model. The current implementation creates candidate checkpoints by default and keeps the served checkpoint unchanged until reviewed promotion; the explicit `force_promote: true` request option bypasses the review gates. Consult `docs/TRAINING_API.md` and `docs/OPERATIONS.md` for the lifecycle.

## Useful starting points for future changes

1. Read the relevant config in `configs/` to establish the actual data and model path.
2. Trace its consumer through `training.py`, `api.py`, or `bridge.py` rather than inferring use from filenames.
3. Preserve the distinction between training data, evaluation data, challenge prompts, the Golden Set, knowledge, memory, and session history.
4. Update focused tests and the corresponding API/corpus/operations documentation when behavior or persisted formats change.
