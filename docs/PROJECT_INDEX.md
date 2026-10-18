# Chit Project Index & Comprehensive Reference Manual

> **Purpose**: This document is the single authoritative guide to the Chit codebase. It is written in simple English to help you find bugs, understand how parts connect (wiring), and add features without breaking existing expectations. 

---

## 1. Executive Summary & Glossary

Chit (चित्, Sanskrit for *mind*) is a custom AI language model (a neural network) built from scratch. It is the cognitive engine inside a larger assistant system called **Atmini**.

### The Golden Rule: Brain vs. Notebook
Chit strictly separates its *brain structure* from its *memories*. 
1. **The Brain (Neural Weights)**: Stored in `checkpoints/`. This is what the model learns permanently during *training*.
2. **The Notebook (Databases)**: Stored in SQLite (`data/memory.db`, `data/knowledge.db`, `data/sessions.db`). These are facts, past conversations, and rules it looks up dynamically. 

If you want Chit to learn a new language pattern, you **train** it. If you want Chit to remember a user's name, you **save a memory**. Do not mix these up.

### Glossary of Terms
- **Champion**: The active, live AI model currently answering user queries (`checkpoints/latest.pt`).
- **Candidate**: A newly trained AI model (`checkpoints/jobs/<id>/latest.pt`) waiting to pass tests before it can become the Champion.
- **Memory**: A specific fact about a user or the world, saved in `memory.db`.
- **Knowledge / Lesson**: A curated fact or rule in `knowledge.db` waiting to be permanently trained into the AI's weights later.
- **Golden Set**: A strict 50-question test the Candidate must pass to become the Champion.
- **Test-Time Compute / Chain-of-Thought (CoT)**: Conditioning the model to produce intermediate reasoning scratchpad tokens (`Reasoning: ...`) before emitting the final answer (`Answer: ...`), eliminating deduction errors at inference time without retraining.

---

## 2. System Architecture & Data Flow Visualized

### The Chat Request Journey
When a user sends a message, here is exactly how the files talk to each other:

```mermaid
flowchart TD
    User([User types in Browser]) --> UI[ui.py\nPort 8001]
    UI -->|Proxies POST /chat| API[api.py\nPort 8000]
    API --> Bridge[bridge.py\nThe Orchestrator]
    
    Bridge <-->|Fetches history| Sessions[(sessions.db\nVia sessions.py)]
    Bridge <-->|Searches facts| Memory[(memory.db\nVia memory.py)]
    Bridge <-->|Extracts new facts| Facts[facts.py]
    
    Bridge --> Formats[formats.py\nBuilds prompt string]
    Formats --> Queue[inference.py\nTraffic Queue]
    Queue --> Runtime[runtime.py\nWrapper]
    Model -->|Streams response| User
```

### Context Budget & Prompt Trimming Hierarchy
The AI has a strict reading limit (`block_size`, typically 256 or 512 tokens). When the `Bridge` gathers history and memory, `formats.py` trims information under a clean canonical `Task: {task}` scaffold in this strict priority order to prevent context overflow:

1. **Oldest Session Turns**: Distant chat history is forgotten first.
2. **Conversation Summary**: If an extractive summary of old turns exists, it is dropped next.
3. **Lowest-Ranked Memories**: Contextual facts with low semantic relevance are dropped.
4. **Oldest Extracted Facts**: Direct core facts (like user preferences) are highly protected but dropped if desperate.
5. **Current User Input**: As an absolute last resort, the user's current message is truncated (protecting open markdown code fences and UTF-8 multi-byte boundaries).

When `think: true` is enabled, the Bridge automatically reserves additional token headroom within the prompt budget to accommodate the `Reasoning:` primer.

---

## 3. Core Algorithms & Mechanisms (The "How")

Beyond moving data, the system performs several intelligent background tasks:

- **Compound AI Bridge Architecture & Unified 7-Task Router (`bridge.py`, `formats.py`)**: Decomposes request processing into single-responsibility stages: `BridgeConfig` (ablation toggles with `enable_generic_verifier=True`, `enable_calibration=True`, `best_of_n=3`), `Router` (typed `Plan` and `select_effective_task` mapping default `task="chat"` across the 7 canonical tasks: `chat`, `knowledge`, `behavior`, `grammar`, `reasoning`, `prose`, `continue`), `ContextBuilder` (working-memory budgeting and grounded `Task: reasoning` prompts), `Generator` (safe runtime execution), `Verifier` (generic invariant checks + conditional Best-of-3 candidate selection when `not primary_passed`), and `Responder` (transparent recovery ladder: resample $\rightarrow$ extractive projection $\rightarrow$ honest abstain).
- **Autoregressive KV-Cache (`model.py`)**: `CausalSelfAttention`, `Block`, `ChitModel.forward()`, and `ChitModel.generate()` support `past_kv` and `use_cache=True` by default, caching key/value tensors after prompt prefill and slicing positional/RoPE embeddings to current positions with 100% checkpoint compatibility.
- **Record-Aligned Window Sampling & Answer-Only Loss Masking (`data.py`)**: `TextDataset` indexes `"Task: "` record boundaries (`record_starts`), sampling 70% record-aligned windows and 30% uniform random windows in `random_batch()`, and masks prompt bytes before `Chit:` or `Reasoning:` with `-100` (`answer_loss_only=True`) so cross-entropy loss focuses on answer and reasoning tokens.
- **Working-Memory Budgeting (`bridge.py`)**: For Chit's 256-byte context window, dynamically reserves token headroom ($\text{gen\_reserve} \ge 32$) to prevent sliding generation from evicting prompt tokens. Enforces slot priority truncation: Sacred User Input > User Facts > Web Evidence > Summary > History > Notebook Memories.
- **Symbolic Calculator Offload (`tools/calculator.py`)**: Automatically detects pure arithmetic (e.g. `45 * 12`, `100 / 4`, `seven times eight`) and computes exact answers using AST evaluation with zero `eval`/`exec`, returning exact mathematical answers with `source: "tool"`.
- **Isotonic Confidence Calibration & Degenerate Curve Safeguard (`tools/calibrate_confidence.py`, `bridge.py`)**: Uses Pair-Adjacent Violators Algorithm (PAVA) with upper-anchor preservation to fit isotonic regression curves over validation evaluations (`data/calibration.json`), while `Bridge._load_calibration()` rejects degenerate curves whose top anchor falls below `uncertainty_threshold`.
- **Chain-of-Thought Thinking Engine (`bridge.py`)**: When `think=true` is requested, the Bridge builds a grounded `Task: reasoning` prompt (including budgeted `Known memory:` and `User-stated facts` above `Input: ...\nReasoning:`), allowing the model to generate scratchpad tokens before `Answer:`. The Bridge decouples `metadata.thoughts` from user-facing text without polluting dialogue history, and preserves `Task: knowledge` / `Task: behavior` / `Task: grammar` if fallback generation is needed.
- **Fact Extraction (`facts.py`)**: It does *not* use AI to extract facts. It uses lightning-fast, deterministic Regular Expressions (Regex) to spot patterns like `name`, `location`, `preference`, `email`, `project`, and `goal` in user messages, rejecting common conversational false positives.
- **Background Summarization (`summarization.py`)**: It runs a deduplicated extractive summarizer. When a chat session gets too long, it condenses the oldest messages into a short summary block so the AI doesn't have to re-read the whole conversation.
- **Semantic Search (`embeddings.py` & `faiss_index.py`)**: When you save a memory, it is converted into a mathematical array (vector) using `SentenceTransformers`. When the user asks a question, the system finds the closest matching vectors using FAISS (a high-speed search library) or exact cosine similarity if FAISS isn't installed.
- **Retrieval Thresholding & Information-Theoretic Query Coverage (`bridge.py` & `memory.py`)**: Enforces `min_relevance` thresholding (default `0.35` in Bridge) to filter out low-confidence semantic noise. Lexical matching uses normalized query coverage $\frac{|Q_{\text{terms}} \cap D_{\text{terms}}|}{|Q_{\text{terms}}|}$ with vocative attenuation ($0.25\times$) for self-referential identity addressing, completely preventing false memory recalls on greetings (e.g. `"Hello Chit"`). Automatically engages deterministic greedy decoding (`temperature=0.0`) when memories or facts are present.
- **Resilient Autonomous Metasearch & Crawler (`search.py`)**: Multi-tier discovery spanning DuckDuckGo JSON, Wikipedia REST, Internet Archive, and external search engines (`CHIT_SEARCH_URL`). An SSRF-guarded deep crawler (`crawl_page`) extracts compact 60–80 character factual propositions that fit Chit's 256-byte context window without truncation.
- **Native Neural Reasoning Over Premises (`bridge.py`)**: Feeds retrieved premises directly into Chit's Transformer (`Task: reasoning\nKnown memory:\n- [Web] ...\nInput: <Query>\nReasoning:`). If the small model drifts into memorized attractors, an extractive recovery ladder projects the factual premise with source citations.
- **Generation Quality & Early Stopping (`runtime.py` & `model.py`)**: Implements token-level early stopping via boundary callback `stop_fn` to prevent wasted forward passes past stop boundaries. Employs prompt-scoped repetition penalties (`idx[b, prompt_len:]`) that penalize repeated generation tokens without penalizing prompt/memory tokens.

---

## 4. Database Schemas (The Notebook)

The system relies on SQLite for zero-ops, local dynamic storage. Here is the Entity-Relationship structure connecting conversations to memories.

```mermaid
erDiagram
    SESSIONS ||--o{ TURNS : contains
    SESSIONS {
        string id PK
        datetime created_at
    }
    TURNS {
        string id PK
        string session_id FK
        string role "User or Chit"
        string content
        int tokens
    }
    
    MEMORIES ||--o| MEMORY_EMBEDDINGS : has
    MEMORIES {
        string id PK
        string text
        float importance
        string type "fact or experience"
        datetime created_at
    }
    MEMORY_EMBEDDINGS {
        string memory_id FK
        blob vector "Mathematical meaning"
    }
    
    KNOWLEDGE_ENTRIES {
        string id PK
        string type "text, qa, reasoning"
        string content
        string state "pending or trained"
    }
```
*Note: `MEMORIES` utilizes SQLite FTS5 (Full-Text Search) for rapid keyword matching alongside semantic vector matching.*

---

## 5. Security & Authentication Model

Because Chit is a personal assistant, protecting its data is critical.
- **Backend API (Port 8000)**: Completely stateless. Every request must include the `CHIT_API_KEY` either as an `X-API-Key` header or a `Bearer` token.
- **Browser UI (Port 8001)**: Stateful. Users log in with the API key. The server verifies it and issues a strictly locked-down cookie (`chit_console_key`). This cookie is `HttpOnly` (immune to JavaScript XSS) and `SameSite=Strict` (immune to CSRF).
- **Training & Admin Access Gating**: Sensitive candidate evaluation, promotion, rollback, and reload endpoints (`/candidates`, `/candidates/{job_id}/evaluate`, `/candidates/{job_id}/promote`, `/admin/rollback`, `/admin/reload`) require the `require_training_access` dependency to prevent unauthorized manipulation of production weights.

---


## 5. UI Features & Philosophy

The Chit UI (`ui.py` & `app.js`) is the primary way to interact with the system. It strictly wraps the API.
- **Universal Page Guides**: Every UI view has a "Page Guide" button that explicitly maps friendly UI terms to their underlying JSON API payloads (e.g. mapping "Text reader" to `tokenizer`, or "Learn from scratch" to `init_checkpoint: null`).
- **Real-Time System Metrics**: The UI header features a live CPU/Mem/Disk badge polling `GET /sys_metrics` every 2 seconds.
- **Unified Training & Candidates**: The Studio UI lists training jobs and immediately surfaces their associated Golden Gate evaluations, file timestamps, and promotion buttons once completed.

## 6. Directory & Module Map (Wiring)

### Core AI Brain (The Neural Network)
| File | Purpose | Wiring | API / UI Exposure |
|---|---|---|---|
| `model.py` | Math of the AI brain (Transformer, RoPE). | Wires to `training.py` and `runtime.py`. | `GET /model` |
| `tokenizer.py` | Translates human text to AI tokens. | Used globally for text processing. | Internal only. |
| `config.py` | Enforces JSON settings schema safely. | Loaded during training jobs. | Payload validation. |

### Orchestration & Prompting (The Bridge)
| File | Purpose | Wiring | API / UI Exposure |
|---|---|---|---|
| `bridge.py` | Orchestrates Compound AI pipeline (Router, ContextBuilder, Generator, Verifier, Responder). | Connects `api.py` to `runtime` and tools. | Powers `POST /chat` and `POST /generate`. |
| `formats.py` | Executes the prompt trimming hierarchy. | Called by `bridge.py`. | Internal only. |
| `search.py` | Multi-tier metasearch and SSRF-guarded crawler. | Called by `bridge.py`. | Powers autonomous grounding. |
| `tools/calculator.py` | Exact AST symbolic arithmetic offload. | Called by `bridge.py` Router. | Exact math without neural guessing. |
| `tools/calibrate_confidence.py` | Isotonic probability calibration (PAVA). | Called by `api.py` on promotion. | `data/calibration.json`. |
| `tools/benchmark_bridge.py` | 65-case bridge fidelity & calibration benchmark. | Called by `api.py` and CLI. | `POST /candidates/{id}/benchmark`. |
| `inference.py` | Queue system protecting CPU from overload. | Called by `bridge.py` and `api.py`. | Protects generation. |
| `runtime.py` | Wrapper bundling model, tokenizer, memory. | Booted in `api.py`. | Core server engine. |

### Memory & Knowledge Databases (The Notebook)
| File | Purpose | Wiring | API / UI Exposure |
|---|---|---|---|
| `memory.py` | Searches facts via FTS5 and Vectors. | Called by `bridge.py`. | `POST /memory` |
| `faiss_index.py` | Speed-boost module for vector searches. | Plugs into `memory.py`. | Invisible speedup. |
| `embeddings.py` | Converts text to meaning vectors. | Plugs into `memory.py`. | Invisible dependency. |
| `sessions.py` | Remembers chat history. | Called by `bridge.py`. | `GET /sessions`. |
| `facts.py` | Auto-extracts facts from user messages. | Called by `bridge.py`. | Triggers during chat. |
| `summarization.py`| Shrinks old conversations into summaries. | Background in `sessions.py`. | Invisible optimization. |
| `knowledge.py` | Staging area for facts to be trained later. | Feeds `training.py`. | `GET /knowledge` |

### Training & Operations
| File | Purpose | Wiring | API / UI Exposure |
|---|---|---|---|
| `training.py` | Updates the neural network weights. | Takes `datasets.py` $\to$ updates `model.py`. | Runs during `/train`. |
| `datasets.py` / `data.py` | Reads `.txt` files based on weight %. | Feeds `training.py`. | Configured via JSON. |
| `jobs.py` | Background training queue (1 job max). | Called by `api.py`. | `GET /train/{job_id}` |
| `promotion_state.py`| Swaps Candidate for live Champion. | Used by API / CLI. | UI "Promote" buttons. |

---

## 7. How to Add Features or Fix Bugs Safely

1. **Adding a new API Endpoint**: Add the route in `api.py`. If the UI needs it, **must** update the `ROUTES` list in `ui.py`.
2. **Changing AI Answers**: Do not write code. Add a fact via `/memory` or "Teach Chit".
3. **Prompt Layout**: Edit `formats.py`.
4. **Retrieval Logic**: Edit `bridge.py`.
5. **Training**: The AI only learns from `.txt` files listed in `.json` configs. Changing `.txt` files requires running a new training job to take effect.
6. **UI Elements**: Be careful with Jinja2 whitespace in `ui/templates/index.html` (e.g. `{{ base_path | tojson }}`).

---

## 8. Checkpoint Rules: Candidate vs Champion

```mermaid
stateDiagram-v2
    [*] --> Candidate: Training Completes
    Candidate --> GoldenSetEvaluation: tools/eval_runner.py
    Candidate --> BridgeBenchmark: tools/benchmark_bridge.py
    
    GoldenSetEvaluation --> Rejected: Score < 85% or Fails Critical
    GoldenSetEvaluation --> Approved: Score >= 85% + 100% Critical + Auto-Rated
    
    Approved --> Champion: tools/promote_candidate.py (Auto-Calibrates data/calibration.json)
    Champion --> [*]: Serves API Traffic with Calibrated Confidence
```
**Safeguard:** The Champion is *never* automatically replaced unless you explicitly pass `force_promote: true` via the API. 

---

## 9. Datasets (`.txt`) and Configs (`.json`)

### Core Datasets (Unified `Task:` Headers via `scripts/upgrade_corpus_tasks.py`)
- **Small**: `data/train.txt` (118 blocks: `chat`, `prose`, `grammar`, `behavior`) - fast CPU sanity tests.
- **English Foundation (`data/english_foundation/`)**: `structural.txt` (`Task: grammar`, 7,691 blocks), `conversation.txt` (`Task: chat`, 4,189 blocks), `lexical_prose.txt` (`Task: prose`, 5,492 blocks), `project_facts.txt` (`Task: knowledge`, 10 blocks).
- **Conversation & Reasoning (`data/conversation_reasoning/`)**: `conversation.txt` (`Task: chat`, 3,073 blocks including prompt-side typo/noise greeting & identity variants with clean replies) and `reasoning.txt` / `data/reasoning.jsonl` (`Task: reasoning`, 1,196 blocks, 236 grounded with `Known memory:` / `[Web]` / `User-stated facts:`).
- **Knowledge & Behavior (`data/knowledge_behavior/`)**: `knowledge.txt` (`Task: knowledge`, 1,245 blocks, 171 grounded) and `behavior.txt` (`Task: behavior`, 1,327 blocks, 20 grounded).
- **Unified Held-Out Evaluation (`data/eval_combined.txt`)**: 574 held-out records across all 6 task families (`chat`: 240, `knowledge`: 129, `reasoning`: 91, `behavior`: 73, `grammar`: 35, `prose`: 6) with zero exact-block leakage against training files.

### Config Tiers (`configs/*.json`)
1. **Bootstrap**: `chit_cpu_learning.json`, `chit_tiny.json` (64-128 tokens).
2. **Experiments**: `chit_byte_experiment.json`, `chit_rope_512_rescue.json` (Architecture tests).
3. **Foundation**: `chit_english_foundation.json` (512 context, multi-source mixing).
4. **Champion 6L-256 Stages**: `chit_english_foundation_6l_256.json`, `chit_conversation_reasoning_6l_256.json`, `chit_knowledge_behavior_6l_256.json`, and `chit_v2_6l_256.json` (6-layer, 256-dim, 256-byte context, byte-level `vocab_size: 256`).

---

## 10. Infrastructure, Topology & CI/CD

Chit is deployed on AWS EC2 (`t4g.small` ARM64). Automated GitHub Actions handle deployment so you never have to SSH manually.

```mermaid
flowchart LR
    Push[Git Push] --> Actions[GitHub Actions]
    Actions -.->|build-and-push.yml| Image[Docker Registry]
    Actions -.->|deploy-ec2.yml| EC2
    
    subgraph EC2[AWS EC2 Instance]
        Web(Internet) --> Caddy[Caddy Reverse Proxy]
        Caddy -->|/console*| UI[ui.py : Port 8001]
        Caddy -->|/*| API[api.py : Port 8000]
        UI -.-> API
    end
```
**CRITICAL RULE**: The API server *must* run with a single worker (`--workers 1`). Memory, training, and traffic queues live in process memory. Multiple workers cause split-brain memory thrashing.

---

## 11. Testing Philosophy & Safeguards

The project contains 218 tests driven by `pytest` (including unit tests for tensor math & KV-cache equivalence, record-aligned sampling & `-100` answer-only loss masking, memory search, sessions, training lifecycle, API security, and compound bridge pipeline components).
- **Mocks & Safety (`conftest.py`)**: Intercepts database paths and redirects them to in-memory databases (`:memory:`). Running tests will never overwrite your live `memory.db`.
- **API Key Overrides**: Tests use a dummy key (`KEY = "test-ui-key"`).

---

## 12. Environment Variables (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `CHIT_API_KEY` | `change-me` | Required password for API/UI. |
| `CHIT_MEMORY_ANN` | `auto` | `auto` uses FAISS; falls back to cosine otherwise. |
| `CHIT_WITH_EMBEDDINGS` | `0` | Set `1` to install local sentence-transformers. |

---

## 13. Common Troubleshooting & Gotchas

- **"QueueFullError" (HTTP 503)**: The queue in `inference.py` is full (max 32). CPU is protected.
- **Model outputs "The the the..."**: Model collapsed. Learning rate too high or step count too low for context size.
- **Golden Set yields 0/50**: Check model `block_size`. Prompts require ~200 tokens. 64-token models fail automatically.
- **ModuleNotFoundError: pranav**: Run commands as modules from root (e.g., `python -m pytest`).

---

## 14. Operational Commands

- **Run API (8000)**: `python -m uvicorn pranav.chit.api:app --port 8000 --workers 1`
- **Run UI (8001)**: `python -m uvicorn pranav.chit.ui:app --port 8001 --workers 1`
- **Run tests**: `python -m pytest`
- **Train model**: `python -m pranav.chit.tools.train --config configs/chit_strong.json`
- **Golden Evaluation**: `python -m pranav.chit.tools.eval_runner --checkpoint checkpoints/latest.pt --eval-file data/eval.txt --golden-set data/golden_set.json --output data/eval_report.json`
- **Bridge Benchmark**: `python -m pranav.chit.tools.benchmark_bridge --checkpoint checkpoints/latest.pt`
- **Calibrate Confidence**: `python -m pranav.chit.tools.calibrate_confidence --input docs/benchmarks/bridge-refactor-final.json --output data/calibration.json`
- **Auto-Rating**: `python -m pranav.chit.tools.auto_rate --eval-report data/eval_report.json --output data/ratings.json`
- **Evaluate**: Use the 'Evaluate Model' button in the Studio UI (Calls `POST /candidates/{job_id}/evaluate`)
- **Benchmark**: Use the 'Benchmark Bridge & Calibrate' button in the Studio UI (Calls `POST /candidates/{job_id}/benchmark`)
- **Promote**: Use the 'Promote to Live' button in the Studio UI (Calls `POST /candidates/{job_id}/promote`)

## Model Candidates and Administration

These routes allow you to review completed training runs, evaluate safety, benchmark bridge quality, and safely swap the live model in production. Sensitive administrative routes require the `require_training_access` dependency.

### GET /candidates
Returns a list of all finished candidate models (`state: "succeeded"` or `"success"`), their candidate checkpoint modification timestamps (`checkpoint_timestamp`), Golden Gate safety scores, and bridge benchmark reports. Requires `require_training_access` dependency.

### POST /candidates/{job_id}/evaluate
Starts a background evaluation of a candidate model against the 50 Golden Gate behavioral prompts, and automatically triggers background bridge fidelity benchmarking. Requires `require_training_access` dependency.

### POST /candidates/{job_id}/benchmark
Triggers an on-demand bridge fidelity benchmark across 65 evaluation cases, computing arithmetic exact match, expected calibration error (ECE), repetition loop rate, cutoff rate, and P95 latency. Requires `require_training_access` dependency.

### POST /candidates/{job_id}/promote
Promotes an evaluated candidate to be the live Champion, safely hot-swapping the active model. **Requirement:** The candidate must pass the Golden Gate evaluation. Automatically re-fits isotonic probability calibration (`data/calibration.json`) so the live AI serves truthful confidence scores immediately. Requires `require_training_access` dependency.

### POST /admin/rollback
Instantly restores the previous live model (Champion) from the archive if a promoted candidate starts behaving poorly. Requires `require_training_access` dependency.
- **Parameters:** `to_sha256` (the exact hash of the previous model to restore).

### POST /admin/reload
Force-reloads the active Champion model from the disk into memory. Requires `require_training_access` dependency.
