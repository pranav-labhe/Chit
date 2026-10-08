# Architecture & Project Digest

```
POST /generate ──┐
                 ├──► Bridge ──► ChitRuntime ──► ChitModel (Transformer weights)
POST /chat ──────┘       │
                         ├──► MemoryStore (recalled at inference)
                         └──► SessionStore (recent conversation context)

POST /knowledge ──► KnowledgeStore ──(POST /knowledge/train)──► training job
                                                                    │
                        promoted checkpoint ◄───────────────────────┘
```

## 1. System Overview
Chit (चित्) is a compact neural brain designed for fast, context-aware text generation. It separates static knowledge (weights) from dynamic experiences (memory) and structured learning (knowledge base).

### Core Cognitive Pillars
- **Weights (`checkpoints/`)**: The deep learning model's state. Updated only via training jobs.
- **Memory (`data/memory.db`)**: SQLite-backed experiences recalled during inference to personalize responses without retraining. `data/memory.json` remains the import and recovery format.
- **Knowledge (`data/knowledge.db`)**: A structured queue of data that the model will "learn" during the next training cycle.

---

## 2. Technical Specifications

### 🧠 Model Architecture (`model.py`)
- **Type**: Byte-level decoder-only Transformer.
- **Default Config**:
    - `vocab_size`: 256 (1:1 mapping to UTF-8 bytes).
    - `block_size`: 128 tokens.
    - `n_layer`: 4 blocks.
    - `n_head`: 4 heads.
    - `n_embd`: 128 dimensions.
- **Tensor Flow**:
    - **Input**: `idx` tensor of shape `(batch, t)`.
    - **Embedding**: Always uses `token_embedding`; absolute mode adds `position_embedding`, while RoPE rotates query/key pairs inside attention.
    - **Blocks**: Each block contains:
        - **Causal Self-Attention**: Projects input to $Q, K, V$ via one linear layer (`3 * n_embd`). Uses `F.scaled_dot_product_attention` with a causal mask. Shape: `(batch, heads, t, head_dim)`.
        - **MLP**: A two-layer network (`n_embd` $\rightarrow$ `4 * n_embd` $\rightarrow$ `n_embd`) with `GELU` activation.
- **Attention**: Uses `F.scaled_dot_product_attention` (Fused kernel) with a causal mask for efficient generation.
- **Weight Tying**: The `lm_head` shares weights with the `token_embedding` to reduce parameter count and improve regularization.
- **Position Encoding**: Absolute embeddings remain the default for legacy compatibility; configurations may opt into RoPE.

### 🔡 Tokenization (`tokenizer.py`)
- **Default**: Every UTF-8 byte is exactly one token. New checkpoints may carry a serialized byte-level BPE tokenizer and its SHA-256 fingerprint.
- **Robustness**: Uses `surrogatepass` during encoding to handle lone surrogates from malformed input, and `replace` during decoding to ensure stability.

### ⚙️ Training Loop (`training.py`)
- **Optimizer**: `AdamW` with weight decay.
- **Loss Function**: `F.cross_entropy` computed over the flattened logits and targets.
- **Weight Init**: Uses normal distribution ($\mu=0, \sigma=0.02$) for all linear and embedding layers.
- **Learning Rate**: Implements linear warmup followed by either a constant rate or a cosine decay schedule.
- **Safeguards**: Includes `clip_grad_norm_` to prevent gradient explosions and checks for `NaN/Inf` loss (raises `FloatingPointError`).
- **Atomic Saves**: Checkpoints are written to temporary files and renamed to prevent corruption.
- **Checkpointing**: Stores model weights, optimizer state, `model_config`, and training metadata (step, best eval loss).

---

## 3. Storage Schemas

### 📄 Memory Store (`memory.db`)
SQLite is the canonical store for memory records; legacy `memory.json` is imported with IDs and metadata preserved and retained for recovery. A `memory_embeddings` table stores rebuildable vectors keyed by memory ID and embedding model version.
- **Search Algorithm**: SQLite FTS5 supplies keyword candidates; with a local embedding provider, normalized vectors are searched through a rebuildable FAISS HNSW index on supported deployments. Exact cosine is the fallback when FAISS is absent or disabled. Hybrid scoring preserves keyword evidence, semantic score, importance, recency, and hard tag filters.
- **Storage**: Objects contain `id`, `type`, `content`, `importance`, `tags`, `created_at`, and optional `source`.

### 🗄️ SQLite Databases
#### `sessions.db` (Conversations)
- **Storage**: SQLite with `WAL` (Write-Ahead Logging) mode, `DEFERRED` isolation, and `foreign_keys=ON` for referential integrity between sessions and turns.
- **`sessions`**: `id`, timestamps, derived narrative summary and coverage/status, explicit facts JSON and controls.
- **`turns`**: `seq (PK)`, `session_id (FK)`, `role (user/assistant)`, `content`, `created_at`.
- **Management**:
    - **Pruning**: Sessions idle for more than `CHIT_SESSION_TTL_DAYS` are deleted at startup.
    - **Trimming**: Overflow exchanges remain until the background summary commits, then covered old turns are pruned and the newest `max_turns` remain.

#### `knowledge.db` (Learning Queue)
- **`knowledge`**: `id (PK)`, `kind (text/qa/reasoning)`, `payload (JSON)`, `content_hash (Unique)`, `tags (JSON)`, `source`, `status (pending/trained)`, `created_at`, `trained_at`, `trained_job_id`.

---

## 4. Security & Constraints

### 🔐 Authentication & Authorization
- **API Key**: Every request except `/health` requires the `X-API-Key` header.
- **Training Access**: Training and knowledge routes are disabled by default unless `CHIT_API_KEY` is set or `CHIT_ALLOW_UNAUTHENTICATED_TRAINING=1` is enabled for local development.
- **Proxy Security**: `ui.py` acts as a server-side proxy; it manages user sessions with `HttpOnly` cookies and forwards the API key to the backend without exposing it to the browser.

### 📏 System Constraints
| Constraint | Value | Source | Description |
| :--- | :--- | :--- | :--- |
| `block_size` | 128 | `model.py` | Max sequence length the model can process. |
| `max_turns` | 200 | `sessions.py` | Max conversation history kept per session (oldest dropped). |
| `history_turns` | 8 | `api.py` | Number of most recent messages sent as context. |
| `max_train_steps` | 100,000 | `api.py` | Upper bound for any single training run. |
| `max_dataset_mb` | 200MB | `api.py` | Maximum size for the generated `train.txt` file. |
| `max_knowledge_batch`| 500 | `api.py` | Max entries allowed in a single `add_knowledge` call. |

---

## 5. Module Deep-Dive

### 🧠 Core Logic (`pranav/chit/`)

| Module | Role | Key Components | Logic Flow |
| :--- | :--- | :--- | :--- |
| **`api.py`** | **Gateway** | FastAPI Routes | Handles HTTP requests $\rightarrow$ Auth $\rightarrow$ Bridge/Store $\rightarrow$ JSON Response. |
| **`bridge.py`** | **Orchestrator** | `Bridge` Class | Connects API requests to the `Runtime`. Manages token limits and temperature. |
| **`inference.py`** | **Scheduler** | `InferenceManager` | Bounds FIFO admission and serializes model execution on the device worker. |
| **`runtime.py`** | **Execution** | `ChitRuntime` | The interface for `generate` and `recall`. Bridges the Gap between Model and Memory. |
| **`model.py`** | **Brain** | `ChitModel` | Transformer-based architecture. Handles the actual tensor math (Forward pass). |
| **`memory.py`** | **Experience** | `SQLiteMemoryStore` | SQLite source of truth, FTS5 keyword retrieval and optional FAISS HNSW hybrid search. |
| **`sessions.py`** | **Context** | `SessionStore` | SQLite transcript, fact and summary coverage/status; transactional retention. |
| **`knowledge.py`** | **Learning** | `KnowledgeStore` | SQLite-based queue for training data. Manages the "teach" $\rightarrow$ "train" pipeline. |
| **`training.py`** | **Evolution** | Training Loop | Implements the gradient descent process to update model weights. |
| **`data.py`** | **Fuel** | `TextDataset` | Handles byte or BPE tokenization and configurable training windows. |
| **`tokenizer.py`** | **Translator** | `ByteTokenizer`, `BpeTokenizer` | Converts text to byte IDs or versioned BPE IDs and back. |
| **`ui.py`** | **Interface** | Admin Console | A single-page proxy UI to interact with the API without exposing keys. |

### Browser Console (`ui.py`, `ui/templates/index.html`, `ui/static/`)
The browser console is a small backend-for-frontend (BFF) that sits in front of the Chit API. It runs on the UI port (8001 by default), while the API normally runs on 8000. `CHIT_UI_API_URL` can point the console at another API address. The UI can also be mounted into a host application; `CHIT_UI_BASE_PATH` supports a reverse-proxy or mounted URL prefix. Template and asset paths are resolved relative to the UI package, so serving the console does not depend on the process working directory.

The rendered page is assembled from `ui/templates/index.html`, `ui/static/css/style.css`, and `ui/static/js/app.js`. The template injects the base path and the server's route catalog as JSON. The JavaScript uses relative URLs under that prefix and does not call the Chit API directly. Its normal user workflows call small `/_ui/*` helper endpoints; guided and advanced API requests use `POST /_ui/proxy`. The server owns the API key and adds `X-API-Key` only when forwarding a request upstream. `GET /_ui/api-guide` serves the repository's `ChitAPIGuide.md` (falling back to `docs/ChitAPIGuide.md`) as plain text for optional in-console reading; it does not require a signed-in UI session.

#### Screens and user workflows
The single page keeps these screens in the browser and switches the visible view without a full page navigation:

| Screen | Purpose and API relationship |
| :--- | :--- |
| **Chat** | Sends conversational turns to `/chat`; a conversation ID keeps its history separate. |
| **Conversations** | Lists, reopens, and deletes sessions through `/sessions`. |
| **Generate** | Sends a one-shot request or text continuation to `/generate`, with response length and optional sampling controls. |
| **Brain** | Searches, creates, and deletes immediately retrievable memories. Memory recall is separate from model training. |
| **Teach Chit** | Adds text or question-and-answer lessons to `/knowledge`; optionally saves the same content as a memory. Lessons enter the training queue and do not alter weights until training runs. |
| **Studio** | Loads available training recipes from `/train/configs`, explains the selected configuration, starts training, and tracks/cancels jobs. Configuration details are read from the server's configured JSON files and combined with active model information. |
| **Training library** | Inspects training data and previews or applies a train/review split. Applying a split changes files in the server's configured data folder. It also shows the model and service state. |
| **Troubleshooting (and Administration)** | Includes rollback and reload capabilities for the live model, in addition to diagnostics.  Collects health, readiness, model, data, training, and selected-recipe evidence; can generate a sample response and record the user's readability feedback in the current page. It diagnoses likely causes but is not an automatic model-quality evaluation. |
| **API reference** | Lets the user choose an operation, edit its fields in a guided builder, see the live JSON request, send it through the proxy allowlist, and read field-by-field explanations of the response or errors. Raw JSON editing and the complete Markdown guide are optional supporting views. |

The UI distinguishes **memory** (available for retrieval during inference) from **knowledge** (queued as training material). Training produces a candidate checkpoint by default. `force_promote: true` on `POST /train` explicitly bypasses automated evaluation gates and installs a successful candidate; the UI exposes this request option with a confirmation. Saving a lesson alone does not update model weights. The selected Studio recipe explanation includes relevant architecture, context, data-source weights, tokenizer compatibility, and training settings when the server configuration provides them.

#### Help and API explanations
The frontend maintains contextual help content for controls and API route guides in `app.js`. Help describes purpose, examples, recommended use or values, and risks where known; a fallback explanation is used when a control has no specific entry. A mutation observer also adds help affordances to controls inserted after page load. For each selected API route, the guided builder creates controls from the route's sample query and body: scalar fields become form controls, nested objects and arrays of objects become grouped fields, and arrays or null-valued fields can be edited as JSON. The builder displays a live JSON preview, validates JSON syntax and known numeric ranges, and supports adding or removing structured list items. The technical editor remains available for request shapes beyond the guided sample. After a request, the response view explains known response keys and recursively presents nested objects and arrays; the complete raw JSON remains available. The route catalog in `ui.py`, the field and response descriptions in `app.js`, the API implementation, and `ChitAPIGuide.md` are maintained separately, so API changes need coordinated updates to these descriptions and the proxy allowlist.

#### Authentication, proxying, and request boundaries
1. The user submits the API key to the UI login endpoint. The UI compares it with the configured API key and keeps it server-side in a process-local session store.
2. The browser receives only a random opaque session identifier in an `HttpOnly`, `SameSite=Strict` cookie. The cookie is marked `Secure` when the request is HTTPS and scoped to the configured base path. Session expiry slides on access; the default lifetime is 12 hours, with a configured minimum of 60 seconds.
3. The UI checks the request origin on login, logout, and proxy operations. The proxy accepts only listed method/path patterns, rejects path traversal and URL-like path characters, forwards JSON and query parameters, and returns the upstream status, content type, and body. Browser caching is disabled for proxy responses.
4. A pooled `httpx.AsyncClient` is created and closed with the UI application lifespan. Redirect following is disabled. Upstream timeouts map to 504; connection failures map to 502.

Sessions live only in the UI process. A UI restart clears them, and multiple workers or replicas do not share session state; users must sign in again after restart or when a request reaches a process without that session. The browser polls live status at a 30-second interval while the page is visible and authenticated, and pauses polling while hidden. The frontend keeps troubleshooting response metadata in page memory only; it does not persist the prompt text as diagnostic history.

The manual route catalog is both the API reference data source and a security allowlist. Both the guided builder and advanced editor are restricted to the catalog's supported methods and paths rather than making the browser a general-purpose URL proxy. The builder derives its starting JSON from catalog examples, so it explains and edits those common request shapes; it does not replace API-side validation or guarantee that arbitrary optional fields are covered by the guided form. The actual API key is never injected into the HTML or JavaScript. The legacy `_HTML` string in `ui.py` is not the served page; `index` renders the template and static assets listed above.

#### UI configuration
| Setting | Default | Purpose |
| :--- | :--- | :--- |
| `CHIT_UI_API_URL` | `http://127.0.0.1:8000` | Upstream Chit API base URL. |
| `CHIT_UI_HOST` | `0.0.0.0` | Interface for the UI server. |
| `CHIT_UI_PORT` | `8001` | UI listening port. |
| `CHIT_API_PORT` | `8000` | API port used when the combined serving entry point starts both servers. |
| `CHIT_UI_BASE_PATH` | empty | Optional URL prefix for mounting or reverse-proxy deployment. |
| `CHIT_UI_SESSION_TTL_SECONDS` | `43200` | Sliding session lifetime; values are clamped to at least 60 seconds. |
| UI upstream timeout | `300` seconds | Maximum wait for an upstream request. |

### Source-aware language training
Training configs may optionally provide `data.sources`, a list of `{path, weight}` streams. When
present, each sequence in a training batch selects one stream by normalized weight and samples its
window only from that file. This supports mixed capability curricula without windows crossing
unrelated file boundaries. If `data.sources` is absent or empty, training retains the legacy
`data.train_file` behavior. The candidate checkpoint records configured weights and observed sampled
window counts in metadata. The English foundation preset uses separate grammar/prose, conversation,
and project-fact files; it does not replace the shared train/eval files.

### 🛠️ Tools & Utils (`pranav/chit/tools/`)
- **`train.py`**: CLI for triggering training.
- **`teach.py`**: CLI for adding knowledge.
- **`split.py`**: Utility to split corpus into train/eval sets.
- **`generate.py`**: CLI for raw model inference.
- **`migrate_memory.py`**: Dry-run or import the legacy memory JSON into SQLite.
- **`reindex_memory.py`**: Build versioned local memory embeddings.
- **`train_tokenizer.py`**: Train an optional byte-level BPE tokenizer asset.
- **`benchmark_inference.py`**: Compare serialized and bounded-queue latency/throughput.

---

## 6. Architectural Constraints & Bottlenecks

### ⚡ Computational Bottlenecks
- **Inference Scheduling**: `InferenceManager` provides bounded FIFO admission and serial execution on one dedicated worker per process/device. Dynamic batching remains disabled until profiling and correctness work justify it.
- **Memory Search Complexity**: Linux deployments with FAISS use HNSW semantic candidates and SQLite FTS5 lexical candidates. SQLite remains canonical and exact cosine/keyword fallback remains available. Recall@5 and p95 latency still need target-hardware evaluation before setting production SLOs.

### 💾 Storage Constraints
- **Memory Persistence**: SQLite transactions and WAL replace full JSON rewrites. The JSON source is retained through migration for recovery.
- **Session Window**: The sliding window approach in `sessions.py` ensures constant-time history retrieval but leads to loss of long-term conversational context beyond `max_turns`.

---

## 7. Data Flow & Lifecycles

### 🔄 Inference Flow (`/chat` or `/generate`)
`User Request` $\rightarrow$ `api.py` $\rightarrow$ `bridge.py` (Prompt Engineering) $\rightarrow$ `runtime.py` $\rightarrow$ `memory.py` (Recall) $\rightarrow$ `InferenceManager` (bounded admission) $\rightarrow$ `model.py` (Generate) $\rightarrow$ `sessions.py` (Save) $\rightarrow$ `User`.

- **Orchestration**: `bridge.py` maps a `Context` (input, history, memories) to a `ChitDecision` (text, metadata, recalled memory IDs).
- **Prompt Engineering**: Uses `render_chat_prompt` to wrap raw inputs into a formatted template.
- **Stop Sequences**: Inference terminates when the model generates boundaries like `\nUser:`, `\nChit:`, or `\nTask:`.

### 📚 Knowledge Lifecycle
`Teach (/knowledge)` $\rightarrow$ `knowledge.db` $\rightarrow$ `Train (/knowledge/train)` $\rightarrow$ `training.py` $\rightarrow$ `checkpoints/latest.pt` $\rightarrow$ `Runtime` (Served).

## 8. Comprehensive Method Index

### `pranav/chit/`

| File | Method | Params | Description |
| :--- | :--- | :--- | :--- |
| **`api.py`** | `generate` | `r: GenerateRequest` | High-level text generation. |
| | `chat` | `r: ChatRequest` | Conversational generation with session history. |
| | `start_training` | `r: TrainRequest` | Initiates a weight update job. |
| | `add_knowledge` | `batch: KnowledgeBatch` | Adds data to the training queue. |
| | `split_data` | `r: SplitRequest` | Organizes raw corpus into training/eval. |
| **`bridge.py`** | `__init__` | `runtime, max_memories, ...` | Initializes the API-to-Runtime bridge. |
| **`data.py`** | `random_batch` | `ds, batch_size, device` | Provides shuffled data for training. |
| **`model.py`** | `forward` | `idx, targets` | The core Transformer forward pass. |
| **`runtime.py`** | `remember` / `recall` | `*a, **k` | Interface for the model's long-term experience. |
| **`sessions.py`** | `__init__` | `path, max_turns` | Initializes conversation state store. |
| **`ui.py`** | `proxy` | `payload: ProxyRequest` | Forwards UI requests to API with server-side keys. |
| | `api_guide` | none | Serves the plain-English API guide as text for the optional in-console guide view. |
| | `login` / `logout` | login request / session cookie | Starts or clears the browser's UI session. |
| | `ui_session` | session cookie | Reports whether the browser has an active UI session. |
| | `ui_session_title` | session ID | Loads a display title for a conversation via the API. |
| | `ui_memories` | search query | Supplies memory search results for the Brain screen. |
| | `ui_knowledge_stats` | none | Supplies counts for the learning pipeline. |
| | `ui_train_status` | optional job ID | Combines API health and job details for progress display. |
| | `ui_train_configs` / `ui_train_config` | optional config name | Lists allowed recipes and returns selected configuration details. |
| | `ui_start_train` / `ui_train_jobs` | training request / none | Starts training or lists training jobs for Studio. |

### `tests/` (Verification Suite)
| File | Focus | Key Test |
| :--- | :--- | :--- |
| **`test_model.py`** | Tensor Logic | `test_fused_attention_matches_reference` |
| **`test_sessions.py`** | History | `test_prompt_trims_oldest_turns_first` |
| **`test_training_api.py`** | Lifecycle | `test_train_promotes_and_serves_new_model` |
| **`test_ui.py`** | Security | `test_proxy_forwards_key_request_without_exposing_key` |
