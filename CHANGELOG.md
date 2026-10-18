# Changelog

## Latest Changes

### Added
- **Unified `Task:` Vocabulary & Router Auto-Selection (`pranav/chit/formats.py`, `api.py`, `ui.py`, `bridge.py`)**:
  - Locked in 7 canonical tasks across runtime, API, and training corpus: `VALID_TASKS = ("chat", "knowledge", "behavior", "grammar", "reasoning", "prose", "continue")`.
  - Updated `render_reasoning()` to emit `Task: reasoning\n[Known memory / Facts]\nInput: ...\nReasoning: ...\nAnswer: ...`.
  - Validated `task` against `VALID_TASKS` in `ChatRequest` and added `task` (default `"chat"`) to `GenerateRequest` (`POST /generate`).
  - Implemented `Router.select_effective_task()` in `bridge.py`: when `c.task == "chat"` (default), automatically selects `reasoning` (if `think=True`), `behavior` (missing info/conflict/policy queries), `grammar` (grammar/tense/rewrite requests), `knowledge` (when memories/facts/search are present or query asks about Chit/Atmini architecture), or `chat`. Explicit non-default tasks are preserved verbatim.
  - Fixed Think-mode fallback `prompt_task` to re-run `select_effective_task(..., is_thinking=False)` so fallback generation preserves `Task: knowledge` / `Task: behavior` / `Task: grammar` when memories or web snippets are present.
- **In-Place Training Corpus Overhaul & Combined Evaluation Set (`scripts/upgrade_corpus_tasks.py`, `data/`)**:
  - Upgraded all source training files in-place without merging files and while preserving exact original block counts:
    - `data/conversation_reasoning/conversation.txt`: 3,073 blocks (`Task: chat`, max dup $\le 2$, including prompt-side typo/noise greeting & identity variants with clean replies).
    - `data/conversation_reasoning/reasoning.txt` & `data/reasoning.jsonl`: 1,196 blocks (`Task: reasoning`, max dup $\le 2$, 236 grounded blocks with `Known memory:` / `[Web]` / `User-stated facts:`).
    - `data/knowledge_behavior/knowledge.txt`: 1,245 blocks (`Task: knowledge`, max dup $\le 2$, 171 grounded blocks — 407 grounded blocks combined across `knowledge.txt` + `reasoning.txt`).
    - `data/knowledge_behavior/behavior.txt`: 1,327 blocks (`Task: behavior`, max dup $\le 2$, 20 grounded blocks).
    - `data/english_foundation/structural.txt`: 7,691 blocks (`Task: grammar`, max dup $= 1$).
    - `data/english_foundation/project_facts.txt`: 10 blocks (`Task: knowledge`, max dup $= 1$).
    - `data/english_foundation/conversation.txt`: 4,189 blocks (`Task: chat`, max dup $= 1$).
    - `data/english_foundation/lexical_prose.txt`: 5,492 blocks (`Task: prose`, max dup $= 1$).
    - `data/train.txt` (118 blocks) & `data/train_1mb.txt` (1,813 blocks): tagged every block with its matching `Task:` header (`chat`, `knowledge`, `behavior`, `grammar`, `prose`), max dup $= 1$.
  - Built `data/eval_combined.txt` (574 held-out blocks across `chat`: 240, `knowledge`: 129, `reasoning`: 91, `behavior`: 73, `grammar`: 35, `prose`: 6) with zero exact-block leakage against all training files, and pointed `configs/chit_conversation_reasoning_6l_256.json` and `configs/chit_knowledge_behavior_6l_256.json` `eval_file` to `data/eval_combined.txt`.
- **Grounded `Task: reasoning`, Best-of-3 Candidate Selection & Calibration Safeguard (`pranav/chit/bridge.py`, `calibrate_confidence.py`)**:
  - Updated `ContextBuilder.build_reasoning_prompt()` to format `Task: reasoning` with budgeted `Known memory:` and `User-stated facts` above `Input: ...\nReasoning:`.
  - Enabled `enable_generic_verifier: bool = True`, `enable_calibration: bool = True`, and `best_of_n: int = 3` by default in `BridgeConfig`.
  - Implemented Best-of-3 candidate selection in `Bridge.process()`: when the primary greedy candidate fails verification or confidence checks (`not primary_passed`), samples up to `best_of_n - 1` (2) additional candidates at `temperature=0.35, top_k=10` and ranks valid candidates by calibrated confidence, completeness, and content-word overlap. Clean primary responses bypass extra generations for zero latency overhead.
  - Added degenerate calibration curve rejection in `Bridge._load_calibration()` (`mapping[-1]["calibrated"] >= uncertainty_threshold`) and upper-anchor preservation in `calibrate_confidence.py`.
- **Autoregressive KV-Cache, Record-Aligned Window Sampling & Answer-Only Loss Masking (`pranav/chit/model.py`, `data.py`)**:
  - Added KV-cache (`past_kv`, `use_cache: bool = True`) to `CausalSelfAttention`, `Block`, `ChitModel.forward()`, and `ChitModel.generate()`, caching key/value tensors after prompt prefill and slicing rotary/positional embeddings to current sequence positions while keeping 100% checkpoint compatibility.
  - Upgraded `TextDataset` (`pranav/chit/data.py`) to index `"Task: "` record boundaries (`record_starts`), sampling 70% record-aligned windows and 30% uniform random windows in `random_batch()`.
  - Implemented answer-only cross-entropy loss masking (`answer_loss_only: bool = True`), setting `y = -100` on prompt header/context bytes before `Chit:` or `Reasoning:` when an answer marker is present in the window (with full-window supervision for `Task: prose` and continuation windows).
- **Compound AI Bridge Re-Architecture (`pranav/chit/bridge.py`)**:
  - Decomposed the monolithic Bridge into single-responsibility components: `BridgeConfig` (ablatable configuration flags), `Router` (typed `Plan`), `ContextBuilder` (working-memory budgeting reserving $\ge 32$ tokens in 256-byte context), `Generator` (safe runtime execution), `Verifier` (generic quality invariants), and `Responder` (transparent recovery ladder preserving `raw_text`).
  - Added slot priority truncation: Sacred User Input > User Facts > Web Evidence > Summary > History > Notebook Memories.
  - Added rich metadata reporting: `tokens_prompt`, `tokens_reserved`, `tokens_history_dropped`, `source`, `is_incomplete`, and `plan`.
- **Exact Symbolic Calculator Offload (`pranav/chit/tools/calculator.py`)**:
  - Implemented safe AST-based arithmetic calculation (zero `eval`/`exec`) supporting binary/ternary operations, nested parentheses, and English word equivalents (`plus`, `minus`, `times`, `divided by`).
  - Strict safeguards: operand magnitude limit $|n| \le 10^7$, division-by-zero handling, and conservative rejection of dates (`2026-10-12`), phone numbers, and hypothetical clauses.
  - Emits exact result with `source: "tool"` and `confidence = None`.
- **Isotonic Confidence Calibration (`pranav/chit/tools/calibrate_confidence.py`)**:
  - Implemented Pair-Adjacent Violators Algorithm (PAVA) to fit an isotonic regression curve over validation runs, saving mappings to `data/calibration.json`.
  - Maps raw sequence probabilities to empirical accuracy (`is_calibrated = True`), bringing Expected Calibration Error (ECE) below 0.15.
- **65-Case Bridge Fidelity Benchmarking Suite (`pranav/chit/tools/benchmark_bridge.py`)**:
  - Evaluates 50 frozen Golden Gate behavioral cases plus 15 dedicated math, long-context, and web probes.
  - Records 7 key metrics: `arithmetic_exact_match`, `expected_calibration_error`, `loop_rate`, `truncated_before_stop_rate`, `replacement_char_rate`, `canned_reply_rate`, and `p95_latency_ms`.
- **Zero-Orphan Candidate Lifecycle in Studio UI & API (`api.py`, `ui.py`, `app.js`)**:
  - Added `POST /candidates/{job_id}/benchmark` endpoint for on-demand bridge benchmarking.
  - Auto-triggers background bridge benchmarking during candidate evaluation (`POST /candidates/{job_id}/evaluate`).
  - Automatically re-fits isotonic confidence calibration to `data/calibration.json` upon candidate promotion (`POST /candidates/{job_id}/promote`).
  - Rendered Bridge Quality badges with hover tooltips, plain-English explainer callout, dedicated `[ 📊 Benchmark Bridge & Calibrate ]` button, and 3-second task polling in Studio UI.
- **Test Suite Expansion**:
  - Added `tests/test_bridge_compound.py` and updated `tests/test_training_api.py`, bringing test suite to 211 passing tests.
- **Resilient Multi-Tier Autonomous Metasearch & Deep Crawler (`pranav/chit/search.py`)**:
  - Implemented an unblocked, zero-dependency cascade across DuckDuckGo Instant Answer JSON API (`api.duckduckgo.com`), Wikipedia REST APIs (`en.wikipedia.org/w/api.php` and `/api/rest_v1/page/summary/`), Internet Archive Open Search API (`archive.org/advancedsearch.php`), and configurable `CHIT_SEARCH_URL` (SearXNG/Brave).
  - Implemented an autonomous deep page crawler (`crawl_page`) with built-in SSRF protection (blocking private RFC-1918 subnets, loopback `127.0.0.0/8`, link-local `169.254.0.0/16`), hard 2.5s timeouts, 128 KB streaming read bounds, and DOM cleaning.
  - Implemented factual relevance ranking budgeting external evidence down to an ultra-compact 60–80 character factual proposition matching Chit's 256-byte context window.
  - Added polymorphic `SearchResult(str)` carrying `.url`, `.title`, `.domain`, and `.snippet`.
- **Native Neural Reasoning Over Retrieved Premises (`pranav/chit/bridge.py`)**:
  - Conditioned Chit's Transformer on sensory premises using the native trained format: `Input: [Retrieved Premise P]. [User Query Q]\nReasoning:`.
  - Enabled Chit's attention heads to natively generate deduction tokens and scratchpad thoughts over the retrieved premises.
  - Implemented a cognitive supervisor truth gate anchoring generations to factual premises when the 4.87M parameter neural model drifts into memorized training attractor states.
- **Information-Theoretic IR Query Coverage & Vocative Attenuation (`pranav/chit/memory.py`)**:
  - Eliminated false memory recalls on greetings and conversational pleasantries (e.g. `"Hello Chit"`) without brittle hardcoded wordlists.
  - Formulated relevance as normalized query coverage $\frac{|Q_{\text{terms}} \cap D_{\text{terms}}|}{|Q_{\text{terms}}|}$ rather than un-normalized raw match counts.
  - Implemented self-referential entity vocative attenuation ($0.25\times$ scale) when the assistant's name is merely an address rather than an informational query, dropping greeting relevance below the 0.35 threshold while preserving substantive queries (e.g. `"Who is Chit?"`).
- **First-Principles Information-Theoretic Grounding Gate & Distribution Alignment (`pranav/chit/bridge.py`)**:
  - Eliminated all heuristic keyword blacklists and ad-hoc regex arithmetic parsers (`_parse_simple_arithmetic`).
  - Implemented universal set-theoretic content token overlap verification ($\mathcal{W}(O) \cap (\mathcal{W}(Q) \cup \mathcal{W}(P)) \neq \emptyset$) using closed-class functional word filtration (`_extract_content_tokens`).
  - Aligned the reasoning prompt with Chit's native trained schema `Input: {query}\nReasoning:`, routing retrieved web evidence through native memory conditioning (`Known memory:\n- [Source]: {snippet}`) to prevent positional context overflow and attention dispersion.
  - Implemented deterministic Grounded Fact Projection with source provenance metadata when the small model drifts into memorized training attractor states.
- **Frontend Attribution & Accessibility Polish (`app.js`)**:
  - Filtered `memory_ids` to exclude `"web-search"`, ensuring the UI breadcrumb *"Chit used N saved memories"* only displays for genuine SQLite records from `memory.db`.
  - Added clickable web domain badges (e.g. `[en.wikipedia.org]`, `[archive.org]`) on assistant bubbles.
  - Guarded control help accessibility observers against thought container descendants.
  - Populated human-authored `controlHelp` entries across advanced console controls.


### Added
- **Generate API Web Search & Thinking Support**: Added `search: bool = False` and `think: bool = False` to `GenerateRequest` (`POST /generate`), forwarding them to `Bridge.process()`. In assistant mode, returns rich metadata (`confidence`, `web_grounded`, `sources`, `is_uncertain`, `is_incomplete`, `metadata`). In `mode: continue`, enforces validation rejecting `search` and `think` with HTTP 422.
- **Chat Upfront Web Search Toggle**: Added interactive `🌐 Web` toggle switch (`#searchToggle`) in `index.html` chat actions alongside `#thinkToggle`, allowing users to force live web search grounding before sending messages.
- **Generate Screen Web Search & Evidentiary Metadata**: Added `#genSearch` and `#genThink` options in Generate screen, along with the evidentiary container `#genMeta` displaying search grounding pills, confidence badges (`conf-high` / `conf-low`), and uncertainty warning notices.
- **Generate API Test Suite**: Expanded `tests/test_generate_api.py` with tests verifying `search` and `think` in assistant mode, rich schema fields, and 422 rejection in continue mode.

## 0.3.2

### Added
- **Autonomous Internet Search (Self-RAG)**: Implemented an autonomous retrieval loop in `Bridge.process()`. When Chit encounters unknown entities or facts where generation confidence is low ($C < 0.40$) and local memory has no match, it autonomously queries the web, injects top-budgeted snippets into `Known memory: - [Web] ...`, and regenerates a grounded answer with deterministic greedy decoding ($T=0.0$).
- **Zero-Dependency Web Retrieval Engine**: Created `pranav/chit/search.py` implementing `search_web()` using Python standard library `urllib.request`. Uses a dual strategy: DuckDuckGo Instant Answer JSON API with graceful fallback to DuckDuckGo HTML snippet parsing, strictly protected with timeouts and fail-safe exception handling.
- **Dynamic Context Budgeting**: Implemented `budget_snippet()` with clean whitespace and word-boundary slicing, budgeting web snippets to fit within tight context limits (`min(120, max(60, int(block_size / 3)))`) without truncation artifacts.
- **Direct Search API & Schema Exposure**: Added `search: bool = False` to `ChatRequest` and exposed `web_grounded: bool` and `sources: list[str]` in `ChatResponse` (`POST /chat`), enabling clients to force search grounding on demand.
- **Interactive Web UI Grounding & Search Trigger**: Wired the `🌐 Search Web` action button in `app.js` to trigger grounded search on demand, and rendered a dedicated `web-grounded-header` pill (`🌐 Grounded via Web Search`) on assistant bubbles when search was used.
- **Retrieval Test Suite**: Created `tests/test_retrieval.py` with 11 comprehensive tests covering instant JSON answers, HTML fallback parsing, network failure resilience, snippet budgeting, Bridge Self-RAG loops, high-confidence bypasses, and API schema validation.

## 0.3.1

### Added
- **Inference Confidence Calibration**: Grounded mathematical sequence confidence scoring in `ChitModel.generate()` using the geometric mean of token-level softmax probabilities $C = \exp(\frac{1}{N} \sum_{t=1}^N \log P(x_t \mid x_{<t}))$ at $T=1.0$ before temperature or penalty adjustments.
- **Generation Completeness Detection**: Implemented terminal punctuation boundary checks (`.`, `!`, `?`, `"`, `'`, `\n`) combined with `finish_reason == "length"` in `Bridge.process()` to detect mid-sentence truncation (`is_incomplete`).
- **Uncertainty Calibration & Retrieval Trigger**: Calibrated uncertainty threshold $\tau = 0.40$ (`is_uncertain`), populating `needs_retrieval` when Chit encounters out-of-distribution prompts or low certainty, serving as the trigger for upcoming Web Retrieval.
- **Dual API Exposure & Response Schema**: Exposed `confidence`, `is_incomplete`, and `is_uncertain` at the top level of `POST /chat` as well as within `metadata`, accompanied by the new typed `ChatResponse` model in `api.py`.
- **Web UI Badging & Retrieval Affordance**: Rendered confidence badges (`conf-high` / `conf-low`), amber warning notices for truncated/uncertain answers, and an interactive `🌐 Search Web` action trigger in `app.js` and `style.css`.
- **Confidence Test Suite**: Added `tests/test_confidence.py` with 12 comprehensive unit tests covering token probability tracking, finish reasons, CoT confidence, and backward compatibility.

## 0.3.0

### Added
- **Native Chain-of-Thought Thinking Engine**: Enabled test-time compute via `think: true` on `/chat` and task `"reasoning"`. Intermediate thought extraction in `Bridge.process()` decouples scratchpad tokens from user-facing text, populating `metadata.thoughts` and `metadata.thought_tokens` without polluting conversation dialogue history.
- **Collapsible Thought Process UI**: Added a sleek `💭 Think` toggle switch in the browser console toolbar and a collapsible `<details class="thought-container">` widget directly above assistant responses in the chat view.
- **Thinking Engine Test Suite**: Created `tests/test_thinking.py` covering reasoning triggers, fallback handling, clean session history retention, and task incompatibility validation.

## 0.2.1

### Security
- **Training Access Gating**: Gated sensitive `/candidates`, `/candidates/{job_id}/evaluate`, `/candidates/{job_id}/promote`, `/admin/rollback`, and `/admin/reload` endpoints with `require_training_access` dependency to prevent unauthorized model evaluation and promotion.

### Fixed
- **Auto-Rater Output Key**: Resolved `KeyError: 'output'` in `auto_rate.py` by supporting both `response` and legacy `output` keys, handling unscorable prompts safely without `AttributeError`.
- **UI Proxy Methods**: Allowed `PATCH` HTTP method in UI proxy (`/_ui/proxy`) for complete API coverage.
- **Memory Store Query Hygiene**: Eliminated duplicate `want = set(tags or [])` in `memory.py` and cached `self.all()` results in fallback vector searches to eliminate redundant second full-table scans.
- **Knowledge Store Add Many**: Eliminated redundant post-insert `SELECT *` query in `add_many()` in `knowledge.py`, constructing `AddResult` directly in memory.

### Performance
- **Autoregressive Early Stopping**: Implemented token-level boundary callbacks (`stop_fn`) in `ChitModel.generate()` and `ChitRuntime.generate()` to halt generation immediately upon emitting stop sequences (`\nUser:`, `\nChit:`, etc.), saving wasted forward passes.

### Grounding & Retrieval
- **Prompt-Scoped Repetition Penalty**: Added `prompt_len` parameter to `ChitModel.generate()` so repetition penalties only penalize newly generated tokens (`idx[b, prompt_len:]`), allowing retrieved context, entities, and memories to remain unpenalized.
- **Retrieval Relevance Thresholding**: Wired `min_relevance=0.35` in `Bridge.process()` and `SQLiteMemoryStore.search()` to filter out low-confidence semantic noise.
- **Dynamic Greedy Decoding**: Automatically engages deterministic greedy decoding (`temperature=0.0`) when memories or facts are present in `Bridge.process()` (unless explicitly overridden).
- **Grounded Prompt Directive**: Injected `Task: {task} (answer concisely using known memory; do not speculate)` into the prompt scaffold when memories or facts exist, with automatic fallback protection against scaffold bloat on small context windows.
- **Deterministic Fact Extraction**: Expanded regex patterns in `facts.py` for name, location, email, and project, with strict anti-false-positive filtering for common conversational words.

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
