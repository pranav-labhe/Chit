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

### `tests/` (Verification Suite)
| File | Focus | Key Test |
| :--- | :--- | :--- |
| **`test_model.py`** | Tensor Logic | `test_fused_attention_matches_reference` |
| **`test_sessions.py`** | History | `test_prompt_trims_oldest_turns_first` |
| **`test_training_api.py`** | Lifecycle | `test_train_promotes_and_serves_new_model` |
| **`test_ui.py`** | Security | `test_proxy_forwards_key_request_without_exposing_key` |
