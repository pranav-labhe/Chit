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
- **Telemetry**: Hardware telemetry (CPU, Memory, Disk) is monitored in real-time via `GET /sys_metrics` to provide instant visibility into system load and hardware constraints.

- **Weights (`checkpoints/`)**: The deep learning model's state. Updated only via training jobs.
- **Memory (`data/memory.db`)**: SQLite-backed experiences recalled during inference to personalize responses without retraining. `data/memory.json` remains the import and recovery format.
- **Knowledge (`data/knowledge.db`)**: A structured queue of data that the model will "learn" during the next training cycle.

---

## 2. Technical Specifications

### 🧠 Model Architecture (`model.py`)
- **Type**: Byte-level decoder-only Transformer (`vocab_size = 256`).
- **Default Config** (Champion `6l_256` preset: `block_size: 256`, `n_layer: 6`, `n_head: 4`, `n_embd: 256`; small preset: `block_size: 128`, `n_layer: 4`, `n_head: 4`, `n_embd: 128`):
    - `vocab_size`: 256 (1:1 mapping to UTF-8 bytes).
- **Tensor Flow & Autoregressive KV-Cache (`use_cache = True`)**:
    - **Input**: `idx` tensor of shape `(batch, t)`.
    - **Embedding**: Always uses `token_embedding`; absolute mode slices `position_embedding[start_pos : start_pos + t]`, while RoPE slices `cos, sin` to `[start_pos : start_pos + t]` and rotates query/key pairs inside attention.
    - **Blocks**: Each block contains:
        - **Causal Self-Attention (`CausalSelfAttention`)**: Projects input to $Q, K, V$ via one linear layer (`3 * n_embd`). Concatenates cached `past_kv = (past_k, past_v)` along the sequence dimension when `use_cache=True`. Uses `F.scaled_dot_product_attention` with `is_causal = (past_kv is None and t > 1)`. Shape: `(batch, heads, t, head_dim)`.
        - **MLP**: A two-layer network (`n_embd` $\rightarrow$ `4 * n_embd` $\rightarrow$ `n_embd`) with `GELU` activation.
- **Weight Tying**: The `lm_head` shares weights with the `token_embedding` to reduce parameter count and improve regularization.
- **Position Encoding**: Absolute embeddings remain the default for legacy compatibility; configurations may opt into RoPE. KV-cache introduces zero new parameters and maintains 100% checkpoint compatibility.

### 🔡 Tokenization (`tokenizer.py`)
- **Default**: Every UTF-8 byte is exactly one token. New checkpoints may carry a serialized byte-level BPE tokenizer and its SHA-256 fingerprint.
- **Robustness**: Uses `surrogatepass` during encoding to handle lone surrogates from malformed input, and `replace` during decoding to ensure stability.

### ⚙️ Training Loop & Record-Aligned Answer-Focused Sampling (`training.py`, `data.py`)
- **Optimizer**: `AdamW` with weight decay.
- **Record-Aligned Window Sampling (`TextDataset.record_starts`)**: Scans corpus byte buffers for `"Task: "` record boundaries. During `random_batch()`, 70% of batch items start at a random `"Task: "` boundary and 30% start at uniform random byte offsets for continuation robustness.
- **Answer-Only Loss Masking (`answer_loss_only = True`)**: For each sampled window, locates the first `"\nChit:"` or `"\nReasoning:"` marker and sets target bytes `y = -100` prior to the answer/reasoning content (`F.cross_entropy(..., ignore_index=-100)`), focusing gradient updates on response quality while keeping full-window supervision for `Task: prose` and continuation windows.
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
  - **Information-Theoretic Query Coverage**: Lexical relevance is calculated as normalized query coverage $\frac{|Q_{\text{terms}} \cap D_{\text{terms}}|}{|Q_{\text{terms}}|}$ rather than raw counts.
  - **Vocative Attenuation**: When the query is a multi-term sentence and the only overlapping term with memory is the assistant's own name (`chit`), the vocative term is scaled by $0.25$, ensuring greetings like `"Hello Chit"` score $0.125$ and drop below the $0.35$ relevance threshold while substantive queries like `"Who is Chit?"` retrieve correctly.
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
| `block_size` | 128 / 256 / 512 | `model.py` | Max sequence length the model can process (Champion `6l_256` uses 256). |
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
| **`api.py`** | **Gateway** | FastAPI Routes | Handles HTTP requests $\rightarrow$ Auth $\rightarrow$ Bridge/Store $\rightarrow$ JSON Response (`ChatResponse`). |
| **`bridge.py`** | **Orchestrator** | `Bridge`, `Router`, `ContextBuilder`, `Generator`, `Verifier`, `Responder` | Compound AI pipeline connecting API requests to `Runtime`. Manages 7-task routing, working-memory budgeting, symbolic math offload, Best-of-3 invariant verification, and calibrated confidence. |
| **`search.py`** | **Web Retrieval** | `search_web`, `crawl_page`, `budget_snippet` | Resilient multi-tier metasearch (DDG JSON, Wikipedia REST, Archive.org, external) and autonomous SSRF-guarded crawler with compact proposition extraction. |
| **`inference.py`** | **Scheduler** | `InferenceManager` | Bounds FIFO admission and serializes model execution on the device worker. |
| **`runtime.py`** | **Execution** | `ChitRuntime` | The interface for `generate` and `recall`. Bridges the Gap between Model and Memory. |
| **`model.py`** | **Brain** | `ChitModel` | Transformer-based architecture with KV-cache (`use_cache=True`), token log-probabilities, and finish reasons. |
| **`memory.py`** | **Experience** | `SQLiteMemoryStore` | SQLite source of truth, FTS5 keyword retrieval and optional FAISS HNSW hybrid search. |
| **`sessions.py`** | **Context** | `SessionStore` | SQLite transcript, fact and summary coverage/status; transactional retention. |
| **`knowledge.py`** | **Learning** | `KnowledgeStore` | SQLite-based queue for training data. Manages the "teach" $\rightarrow$ "train" pipeline. |
| **`training.py`** | **Evolution** | Training Loop | Implements the gradient descent process to update model weights. |
| **`data.py`** | **Fuel** | `TextDataset` | Handles byte or BPE tokenization, record-aligned `"Task: "` window sampling (70%/30%), and `-100` answer-only loss masking. |
| **`tokenizer.py`** | **Translator** | `ByteTokenizer`, `BpeTokenizer` | Converts text to byte IDs or versioned BPE IDs and back. |
| **`ui.py`** | **Interface** | Admin Console | A single-page proxy UI to interact with the API without exposing keys. |

### 🧩 The Compound AI System & Bridge Pipeline (`bridge.py`)
Small language models (like Chit's 4.87M parameter byte Transformer) have tight limits. Rather than forcing the neural weights to solve everything alone, Chit uses a **Compound AI System**:
$$\text{System Quality} = (\text{Model Capability} \times \text{Pipeline Fidelity}) - \text{Pipeline Damage}$$

The Bridge breaks down request handling into single-responsibility components:
1. **`BridgeConfig`**: Dataclass controlling all pipeline features (`enable_calculator=True`, `enable_generic_verifier=True`, `enable_calibration=True`, `best_of_n=3`, `reserve_generation_budget=True`, `open_chat_top_k=20`, etc.). Everything can be turned on or off for benchmarking and ablations.
2. **`Router` & Unified 7-Task Selection (`VALID_TASKS`)**:
   - Canonical task vocabulary: `("chat", "knowledge", "behavior", "grammar", "reasoning", "prose", "continue")`.
   - When `c.task == "chat"` (default), `Router.select_effective_task()` selects the most faithful `effective_task` header: `reasoning` (if `think=True`), `behavior` (missing info/conflict/policy queries), `grammar` (grammar/tense/rewrite requests), `knowledge` (when memories/facts/search are present or query asks about Chit/Atmini architecture), or `chat`. Explicit non-default tasks are preserved verbatim.
   - Maps context to an explicit typed `Plan` (`intent`, `strategy`, `decoding`, `effective_task`, `reasons`).
3. **`ContextBuilder` (Working-Memory Budgeting & Grounded Reasoning)**:
   - In Chit's 256-byte context window, sliding text generation pushes out prompt tokens, destroying causal attention.
   - Calculates a reserved generation budget:
     $$\text{gen\_reserve} = \min(\text{max\_new\_tokens}, \max(32, \min(96, \lfloor\text{block\_size} \times 0.4\rfloor)))$$
   - Caps prompt size at $\text{max\_prompt} = \text{block\_size} - \text{gen\_reserve}$, truncating context by strict priority (Sacred User Input > User Facts > Web Evidence > Summary > History > Notebook Memories).
   - `build_reasoning_prompt()` constructs grounded `Task: reasoning` prompts with budgeted `Known memory:` and `User-stated facts` above `Input: ...\nReasoning:`.
4. **`Generator`**: Interfaces cleanly with `ChitRuntime`, extracting generated text, raw log-probabilities, and finish reasons without swallowing unexpected system errors.
5. **`Verifier` & Conditional Best-of-3 Candidate Selection**:
   - Checks candidate responses against generic invariants: `is_empty`, `is_repetitive`, `has_replacement_char`, `is_truncated`, and `is_disjoint_from_evidence`.
   - When the primary greedy generation passes verification and confidence checks (`primary_passed == True`), it is returned immediately with zero extra latency. When `not primary_passed` and `best_of_n > 1`, the Bridge samples up to `best_of_n - 1` (2) additional candidates at `temperature=0.35, top_k=10` and picks the highest-scoring valid candidate ranked by calibrated confidence, completeness, and content-token overlap.
6. **`Responder` (Transparent Recovery Ladder)**:
   - If all candidates fail verification:
     - **Step 1 (Resample):** Samples at perturbed temperature.
     - **Step 2 (Extractive Projection):** If verified web or memory premise exists, projects the primary factual sentence with source citation (`source: "extractive"`).
     - **Step 3 (Honest Abstain):** If ungrounded, returns an honest clarification request (`source: "abstain"`), never a fake canned string.
   - **Full Transparency**: Always preserves `metadata["raw_text"]` with the model's original unaltered output.

### 🧮 Symbolic Calculator Offload (`tools/calculator.py`)
Small language models struggle with exact multi-digit arithmetic.
- When the `Router` detects a pure arithmetic query (e.g. `"What is 45 * 12?"` or `"100 divided by 4"`), it offloads calculation to a safe symbolic tool.
- **Safety**: Uses AST inspection with **zero `eval()` and zero `exec()`**.
- **Guards**: Bounds numbers to $|n| \le 10^7$, rejects division by zero, and guards against false positives (dates like `2026-10-12`, phone numbers, version strings).
- **Result**: Emits the exact mathematical answer with `source: "tool"` and `confidence = None`.

### 🎯 Calibrated Confidence & Probability Mapping (`tools/calibrate_confidence.py`)
- **Raw Sequence Probability**: The geometric mean of raw token probabilities:
  $$C_{\text{raw}} = \exp\left( \frac{1}{N} \sum_{t=1}^{N} \log P(x_t \mid x_{<t}) \right)$$
- **Isotonic Probability Calibration**: Fits an isotonic regression curve over evaluated validation pairs `(raw_confidence, was_correct)`, preserving high-confidence upper anchors (`1.0`), and serializes the mapping to `data/calibration.json`.
- **Runtime Safeguard**: `Bridge._load_calibration()` applies `data/calibration.json` only when its top anchor is non-degenerate (`mapping[-1]["calibrated"] >= uncertainty_threshold`) and a real checkpoint runtime (or explicit `calibration_file`) is active, preventing flat curves from forcing `is_uncertain = True` on every turn.

### 🌐 Autonomous Internet Search & Resilient Crawler
- **Multi-Tier Metasearch Cascade (`search.py`)**:
  - **Tier 1 (Instant/Entities)**: DuckDuckGo Instant Answer JSON API (`api.duckduckgo.com`, never blocked on EC2).
  - **Tier 2 (Encyclopedic)**: Wikipedia REST Search & Summary APIs (`en.wikipedia.org/w/api.php` and `/api/rest_v1/page/summary/` with custom User-Agent `ChitAssistant/0.3`).
  - **Tier 3 (Archival & Source Literature)**: Internet Archive Open Search API (`archive.org/advancedsearch.php`).
  - **Tier 4 (Configurable Provider)**: Support for `CHIT_SEARCH_URL` (SearXNG / Brave).
  - **Fallback**: DuckDuckGo HTML scraping fallback.
- **Autonomous Deep Page Crawler (`crawl_page`)**:
  - Fetches candidate web pages with browser headers under strict bounds: 2.5s hard timeout, stream reading capped at 128 KB, and built-in SSRF protection blocking private RFC-1918 subnets, loopback `127.0.0.0/8`, and link-local `169.254.0.0/16`.
  - DOM cleaning via `html.parser` and factual proposition ranker budgeting evidence into a clean 60–80 character core factual proposition to strictly prevent context overflow in Chit's 256-byte context window.
  - Polymorphic `SearchResult(str)` carrying `.url`, `.title`, `.domain`, and `.snippet`.
- **Native Neural Reasoning Over Sensory Premises (`bridge.py`)**:
  - Aligns input distribution with Chit's native trained schema: `Task: reasoning\nKnown memory:\n- [Source]: {snippet}\nInput: [User Query Q]\nReasoning:`, conditioning retrieved web premises into native memory context to prevent positional context overflow and attention dispersion within Chit's 256-byte context window.
  - Chit's attention heads attend to context and generate chain-of-thought scratchpad tokens and answers natively.
- **Direct Search Mode**: Passing `search: true` in `Context` / `ChatRequest` (or clicking `🌐 Search Web` in UI) bypasses Pass 1 and searches immediately.

### Browser Console (`ui.py`, `ui/templates/index.html`, `ui/static/`)
The browser console is a small backend-for-frontend (BFF) that sits in front of the Chit API. It runs on the UI port (8001 by default), while the API normally runs on 8000. `CHIT_UI_API_URL` can point the console at another API address. The UI can also be mounted into a host application; `CHIT_UI_BASE_PATH` supports a reverse-proxy or mounted URL prefix. Template and asset paths are resolved relative to the UI package, so serving the console does not depend on the process working directory.

The rendered page is assembled from `ui/templates/index.html`, `ui/static/css/style.css`, and `ui/static/js/app.js`. The template injects the base path and the server's route catalog as JSON. The JavaScript uses relative URLs under that prefix and does not call the Chit API directly. Its normal user workflows call small `/_ui/*` helper endpoints; guided and advanced API requests use `POST /_ui/proxy`. The server owns the API key and adds `X-API-Key` only when forwarding a request upstream. `GET /_ui/api-guide` serves the repository's `ChitAPIGuide.md` (falling back to `docs/ChitAPIGuide.md`) as plain text for optional in-console reading; it does not require a signed-in UI session.

#### Screens and user workflows
The single page keeps these screens in the browser and switches the visible view without a full page navigation. The UI unifies disconnected backend concepts:
- **Unified Training Pipeline**: The Studio screen merges `jobs.py` (running queues) and `eval_runner.py`/`promote_candidate.py` (candidate evaluation and filesystem checkpointing) into a single unified Job Card interface, exposing physical checkpoint file modification times and automated Golden Gate safety scores natively.


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
The frontend acts as an abstraction layer over the raw JSON API, maintaining contextual help content for controls and API route guides in `app.js`. 
- **Universal Page Guides**: Every UI screen features a "Page Guide" button that explicitly maps the friendly UI terms on that page to their underlying JSON API schemas and endpoints (e.g., mapping "Text reader" to `tokenizer`, or "Learn from scratch" to `init_checkpoint: null`).
- **Control Tooltips**: Help describes purpose, examples, recommended use or values, and risks where known. Dynamically injected elements (like Candidate model checkpoints) are bound to the `controlHelp` engine automatically to preserve context.
 A mutation observer also adds help affordances to controls inserted after page load. For each selected API route, the guided builder creates controls from the route's sample query and body: scalar fields become form controls, nested objects and arrays of objects become grouped fields, and arrays or null-valued fields can be edited as JSON. The builder displays a live JSON preview, validates JSON syntax and known numeric ranges, and supports adding or removing structured list items. The technical editor remains available for request shapes beyond the guided sample. After a request, the response view explains known response keys and recursively presents nested objects and arrays; the complete raw JSON remains available. The route catalog in `ui.py`, the field and response descriptions in `app.js`, the API implementation, and `ChitAPIGuide.md` are maintained separately, so API changes need coordinated updates to these descriptions and the proxy allowlist.

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
- **`calculator.py`**: Safe AST-based symbolic arithmetic calculator without `eval` or `exec`.
- **`calibrate_confidence.py`**: Isotonic regression probability calibration tool (PAVA) writing to `data/calibration.json`.
- **`benchmark_bridge.py`**: 65-case bridge pipeline fidelity evaluator (ECE, math exact match, loops, latency).
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
`User Request` $\rightarrow$ `api.py` $\rightarrow$ `bridge.py` (Router $\rightarrow$ ContextBuilder $\rightarrow$ Generator $\rightarrow$ Verifier $\rightarrow$ Responder) $\rightarrow$ `runtime.py` $\rightarrow$ `InferenceManager` (bounded admission) $\rightarrow$ `model.py` (Generate) $\rightarrow$ `sessions.py` (Save) $\rightarrow$ `User`.

- **Orchestration**: `bridge.py` decomposes execution into a typed `Plan`, checks quality invariants, offloads symbolic math, and executes a transparent recovery ladder if invariants fail.
- **Prompt Engineering**: Priority slot truncation protects the sacred user question while budgeting reserved generation headroom in Chit's 256-byte context.
- **Stop Sequences**: Inference terminates when the model generates boundaries like `\nUser:`, `\nChit:`, or `\nTask:`.

### 📚 Knowledge & Candidate Lifecycle
`Teach (/knowledge)` $\rightarrow$ `knowledge.db` $\rightarrow$ `Train (/train)` $\rightarrow$ Candidate Checkpoint $\rightarrow$ `Evaluate & Benchmark` $\rightarrow$ `Promote & Auto-Calibrate` $\rightarrow$ Active Champion (`checkpoints/latest.pt`).

## 8. Comprehensive Method Index

### `pranav/chit/`

| File | Method | Params | Description |
| :--- | :--- | :--- | :--- |
| **`api.py`** | `generate` | `r: GenerateRequest` | High-level text generation with bridge routing. |
| | `chat` | `r: ChatRequest` | Conversational generation with session history and calibration. |
| | `start_training` | `r: TrainRequest` | Initiates a weight update job. |
| | `add_knowledge` | `batch: KnowledgeBatch` | Adds data to the training queue. |
| | `split_data` | `r: SplitRequest` | Organizes raw corpus into training/eval. |
| | `system_metrics` | none | Real-time hardware telemetry (CPU, Memory, Disk). |
| | `list_candidates` | none | Lists finished training candidates with evaluation, benchmark, and timestamps. |
| | `evaluate_candidate` | `job_id: str` | Evaluates candidate against Golden Gate safety rules. |
| | `benchmark_candidate` | `job_id: str` | Runs 65-case bridge fidelity benchmark and calibration analysis. |
| | `promote_candidate` | `job_id: str` | Promotes candidate to Champion and auto-fits isotonic calibration. |
| **`bridge.py`** | `__init__` | `runtime, config, ...` | Initializes the Compound AI Bridge pipeline. |
| | `process` | `context: Context` | Executes Router $\rightarrow$ ContextBuilder $\rightarrow$ Generator $\rightarrow$ Verifier $\rightarrow$ Responder ladder. |
| **`tools/calculator.py`** | `evaluate_expression` | `expr: str` | Safe AST symbolic arithmetic evaluator (zero `eval`/`exec`). |
| **`tools/calibrate_confidence.py`** | `fit_calibration` | `pairs: list` | Fits isotonic regression mapping over confidence/accuracy pairs. |
| **`tools/benchmark_bridge.py`** | `run_benchmark` | `bridge, ...` | Runs 65-case bridge fidelity benchmark recording 7 key metrics. |
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
| **`test_bridge_compound.py`** | Compound AI Pipeline | `test_calculator_offload_binary_and_words`, `test_verifier_and_recovery_ladder` |
| **`test_model.py`** | Tensor Logic | `test_fused_attention_matches_reference` |
| **`test_sessions.py`** | History | `test_prompt_trims_oldest_turns_first` |
| **`test_training_api.py`** | Lifecycle | `test_train_promotes_and_serves_new_model` |
| **`test_ui.py`** | Security | `test_proxy_forwards_key_request_without_exposing_key` |
