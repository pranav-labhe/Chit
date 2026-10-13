# Chit Operating Guide

## Supported installation profile

The project metadata currently requires Python 3.10 or newer. Runtime dependencies are declared in `requirements.txt`: PyTorch 2.4 through 2.x, NumPy 1.26 through 2.x, FastAPI, Pydantic 2, and Uvicorn. CPU and CUDA availability depends on the PyTorch wheel installed for the host. The optional BPE extra uses Hugging Face `tokenizers`; the byte tokenizer remains the zero-extra default.

The Linux ARM64 production image uses the pinned FAISS CPU extra; FAISS GPU
packages are not used in this CPU image. The image build workflow verifies the
FAISS import under Linux ARM64 emulation. The embedding model itself is kept
outside the image and must be provisioned locally if semantic search is enabled.

Install and run from the repository root:

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
uvicorn pranav.chit.api:app --host 127.0.0.1 --port 8000
```

For custom byte-level BPE tokenizer training, install `python -m pip install -e '.[bpe]'`.

## Process topology

The supported topology is one Uvicorn worker per model process. The inference queue, active runtime, and training job registry are process-local. Multiple Uvicorn workers would each load a model and create independent queues and job managers; do not enable multiple workers until coordination and capacity planning are implemented. Put TLS, authentication, and any client-level rate limiting at a trusted reverse proxy when exposing the service beyond localhost.

## Runtime settings

| Setting | Default | Purpose |
|---|---|---|
| `CHIT_CHECKPOINT` | `checkpoints/latest.pt` | Served checkpoint |
| `CHIT_API_KEY` | unset | Protects authenticated API routes when configured |
| `CHIT_ALLOW_UNAUTHENTICATED_TRAINING` | unset/false | Explicit local-development opt-in for training and knowledge routes when no API key is configured |
| `CHIT_MEMORY_PATH` | `data/memory.json` | Legacy JSON import source; retained as a recovery copy |
| `CHIT_MEMORY_DB` | Same path as `CHIT_MEMORY_PATH` with `.db` suffix | SQLite memory database |
| `CHIT_EMBEDDING_MODEL_PATH` | unset | Optional local Sentence-Transformers directory; no remote download is attempted |
| `CHIT_EMBEDDING_MODEL_VERSION` | fingerprint of local model assets | Stable embedding version ID; set explicitly to avoid hashing large model assets at startup |
| `CHIT_EMBEDDING_SEMANTIC_THRESHOLD` | unset | Optional calibrated cosine threshold; leave unset until retrieval evaluation selects a value |
| `CHIT_MEMORY_ANN` | `auto` | Use FAISS HNSW when the optional package and local embedding provider are available; `off` forces the SQLite exact fallback |
| `CHIT_KNOWLEDGE_DB` | `data/knowledge.db` | Knowledge training queue |
| `CHIT_SESSIONS_DB` | `data/sessions.db` | Conversation sessions |
| `CHIT_SESSION_TTL_DAYS` | `30` | Remove sessions idle longer than this at startup; `0` disables pruning |
| `CHIT_MAX_SESSION_TURNS` | `200` | Stored message limit per session |
| `CHIT_HISTORY_TURNS` | `8` | Recent messages considered for prompts |
| `CHIT_INFERENCE_QUEUE_SIZE` | `32` | Maximum waiting inference requests; active work is additional |
| `CHIT_INFERENCE_QUEUE_TIMEOUT` | `30` seconds | Maximum time an inference request may wait in the queue before execution starts |
| `CHIT_CONFIG_DIR` | `configs` | Training configuration directory |
| `CHIT_JOBS_DIR` | `checkpoints/jobs` | Training job artifacts |
| `CHIT_MAX_TRAIN_STEPS` | `100000` | Per-job training step upper bound |
| `CHIT_MAX_DATASET_MB` | `200` | Generated dataset size limit |
| `CHIT_DATA_DIR` | `data` | Source directory for data-splitting APIs |
| `CHIT_SEARCH_URL` | unset | Optional external metasearch endpoint (e.g. SearXNG/Brave format `https://engine/search?q={query}&format=json`) for Tier 4 retrieval |

Training and knowledge routes are disabled when no `CHIT_API_KEY` is set unless the local-development opt-in is explicitly set. Never enable that opt-in on a shared or internet-facing service.

## Autonomous Search & Web Crawler Operations

Chit executes unblocked web searches across DuckDuckGo JSON, Wikipedia REST, and Internet Archive. When deep crawling external pages (`crawl_page`), strict operational limits apply:
- **SSRF Guard**: Automatically blocks non-HTTP/HTTPS schemes, localhost, loopback (`127.0.0.0/8`), link-local metadata services (`169.254.0.0/16`), and private RFC-1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- **Resource Constraints**: Capped at 2.5 seconds timeout per external host and reads a maximum of 128 KB to prevent tarpits and large binary downloads.
- **Custom Search Provider**: If configured, `CHIT_SEARCH_URL` queries an external metasearch aggregator.

## Memory migration and recovery

The API uses SQLite as its canonical memory store. On first startup, if the target DB is empty and the configured JSON file exists, it copies the source to `<memory-file>.pre-sqlite` (if that backup does not already exist) and imports records while preserving IDs. The JSON source is not modified. For a controlled migration, run a dry-run first:

```powershell
python -m pranav.chit.tools.migrate_memory data/memory.json data/memory.db
python -m pranav.chit.tools.migrate_memory data/memory.json data/memory.db --apply
```

The import is idempotent for identical IDs and contents; conflicting content under an existing ID fails. Embedding rows are derived data and may be rebuilt from canonical memory records. Back up SQLite with the SQLite backup API or while using a consistent snapshot; do not assume copying a live WAL database file alone is a valid backup.

To enable semantic retrieval locally, install `python -m pip install -e '.[embeddings,ann]'`, point `CHIT_EMBEDDING_MODEL_PATH` at a pre-downloaded local model, then build its versioned vector rows with `python -m pranav.chit.tools.reindex_memory data/memory.db path\to\embedding-model --version model-revision-id`. On Linux images, the Containerfile installs the pinned `faiss-cpu` extra; on Windows, the exact cosine fallback remains available. When FAISS is present, a rebuildable HNSW index is materialized beside the SQLite database and used for semantic candidate retrieval. FTS5 retrieves keyword candidates for exact names and IDs. SQLite remains canonical; losing the FAISS files only requires rebuilding the index. Keep embeddings local and review their model license/privacy terms before indexing user data.

For a container with semantic embeddings enabled, build with `--build-arg CHIT_WITH_EMBEDDINGS=1`, mount a locally provisioned model directory at `/app/models`, and set `CHIT_EMBEDDING_MODEL_PATH=/app/models/<model>`. The default image includes FAISS but does not download or configure an embedding model automatically.

## Model and tokenizer compatibility

Byte-tokenizer checkpoints remain the default and are loaded when older checkpoints omit tokenizer metadata. BPE checkpoints carry the serialized tokenizer asset and its SHA-256 fingerprint, so inference does not depend on a mutable tokenizer file after training. Train a tokenizer using only the training corpus, then set `tokenizer.name` to `bpe-tokenizers-json-v1`, `tokenizer.model_file` to the resulting asset, and `model.vocab_size` to the command's reported vocabulary size. BPE training is a new model lineage and cannot reuse byte-tokenizer weights.

Absolute position embeddings remain the default. RoPE is an opt-in model configuration; old checkpoints without the position-encoding field are interpreted as absolute-position checkpoints. Increasing context length changes compute and memory requirements and does not by itself guarantee better long-context recall.

## Health, queue, and request identifiers

`GET /health` is a process liveness endpoint and reports model availability plus current inference queue statistics. `GET /model` reports active model configuration and configured queue limits. Inference overload returns HTTP 429 with a stable `inference_overloaded` code and `Retry-After: 1`. Requests may provide an `X-Request-ID`; otherwise the API generates one and returns it in the response. Logs include route, status, request ID, and duration, but omit prompts and API keys.

## Backups

Back up `checkpoints/`, `data/sessions.db`, `data/knowledge.db`, the configured memory SQLite DB, and model/tokenizer training inputs. For SQLite databases, use SQLite's backup API or stop writes before copying. Test restore into a clean directory before relying on a backup. Keep the previous known-good checkpoint when changing the served model.

## Validation tools

- `python -m pranav.chit.tools.benchmark_bridge` measures bridge pipeline fidelity across 65 evaluation cases (recording math exact match, expected calibration error, loop rate, cutoff rate, and p95 latency).
- `python -m pranav.chit.tools.calibrate_confidence` fits isotonic regression probability calibration over validation runs, serializing mappings to `data/calibration.json`.
- `python -m pranav.chit.tools.benchmark_inference` measures sequential and bounded-queue CPU/CUDA inference latency. Results are host-specific; it is not a production SLO test.
- `python -m pranav.chit.tools.benchmark_memory` creates temporary synthetic SQLite corpora and measures exact hybrid-search latency without modifying project memory.
- `python -m pranav.chit.tools.evaluate_tokenizer_pair` compares held-out bits per byte and alternating greedy-generation timings for matched byte/BPE checkpoints.
- `data/golden_set.json` is the frozen 50-case behavioral acceptance set. Follow `docs/GOLDEN_SET.md` for the 85% overall threshold and critical-case gate. Keep its prompts and references out of training and tokenizer corpora.

## Candidate Review, Benchmarking & Zero-Orphan Promotion

To prevent manual command-line steps from being forgotten after training, candidate evaluation and promotion natively manage bridge fidelity and confidence calibration:

1. **Automatic Benchmarking on Evaluation**: Calling `POST /candidates/{job_id}/evaluate` (or clicking 'Evaluate Model' in the Studio UI) runs the Golden Gate safety test and automatically launches `benchmark_bridge` in the background, writing results to `checkpoints/jobs/<job_id>/bridge_benchmark.json`.
2. **On-Demand Benchmark**: Calling `POST /candidates/{job_id}/benchmark` (or clicking 'Benchmark Bridge & Calibrate' in the Studio UI) benchmarks the candidate at any time.
3. **Auto-Calibration on Promotion**: When promoting an approved candidate with `POST /candidates/{job_id}/promote`, the server hot-swaps the model weights and immediately re-fits `data/calibration.json` using the candidate's benchmark data. The newly promoted Champion immediately serves truthful confidence scores with zero manual steps.

Current local benchmark reports are under `docs/benchmarks/`. Re-run them on the target deployment hardware and representative data before setting user-facing latency promises or promoting a model.
