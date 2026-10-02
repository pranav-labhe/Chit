# Chit Production Readiness Implementation Plan

## Purpose

This document turns the four-phase improvement roadmap into an incremental, testable plan for evolving Chit from a compact prototype into a reliable single-node service that can grow without breaking its existing API or checkpoint workflow. It follows the current architecture in `docs/ARCHITECTURE.md` and the implementation under `pranav/chit/`.

The plan preserves Chit's defining separation:

- **Weights** contain learned model parameters and change only through training and promotion.
- **Memory** contains durable, retrievable facts and experiences; it does not silently change weights.
- **Sessions** contain conversation history and summaries scoped to a conversation.
- **Knowledge** is a reviewed training queue, distinct from inference memory.

## Implementation snapshot (2026-10-03)

| Phase | Delivered so far | Still open |
|---|---|---|
| **0 — Foundations** | Structured request logs, liveness/readiness, operating guide, local CPU inference percentiles, and synthetic SQLite retrieval measurements. | Deployment-hardware matrix, repeated/mixed inference runs, CPU peak RSS, CUDA/VRAM, realistic retrieval provider/corpus, and production SLOs. |
| **1 — Performance and memory** | Bounded FIFO manager; SQLite canonical store, FTS5 keyword candidates, optional versioned embeddings, optional FAISS HNSW semantic candidates, and exact fallback. | Run FAISS/embedding recall@5 and p95 benchmarks on target ARM64 data/hardware; verify model provisioning and reindex procedure. Dynamic batching remains deferred pending measured benefit. |
| **2 — Model capacity** | Configurable context length and context curriculum, opt-in RoPE with legacy absolute-position checkpoint compatibility, and embedded BPE assets. One matched-seed byte/BPE experiment plus two 512-token RoPE evaluations now exist. | Rescue training improved held-out metrics but output remains repetitive; behavioral ratings are absent. Diagnose prompt/data/generation alignment and test on the target architecture. The served byte checkpoint is unchanged; do not combine BPE and RoPE in one quality comparison. |
| **3 — Conversation and retrieval** | Explicit fact extraction plus bounded, asynchronous extractive narrative summaries; inspect, refresh, clear, disable, coverage/status, and prompt budgeting. | Validate summary utility/quality with user sessions and target retention load. Summaries never replace explicit facts or a transcript backup policy. |
| **4 — Evaluation and promotion** | Standalone evaluator plus per-checkpoint training-job LM scoring; final machine-readable reports; reviewed Golden Set gates; paired bootstrap challenger policy and a strict initial-champion bootstrap; journaled atomic promotion, startup recovery, and rollback CLI. | Candidate fits the full set but collapses to repetitive output; diagnose and retrain. Obtain independent ratings only for a behaviorally credible model. Exercise promotion/rollback recovery on the host before release. |
| **8 — Hardened deployment** | Linux/amd64 Podman image built locally; pinned FAISS 1.15.1 import and hybrid retrieval smoke passed; API readiness passed. ARM64 build and exact-image rollback workflow are configured. | Build and run on actual EC2 ARM64, provision/validate embedding assets, and benchmark the real corpus/hardware. Hosted deployment could not run: AWS CLI, target variables, and SSH credentials are not available in this workspace. |
| **9 — State orchestration** | Promotion journal, atomic checkpoint replace, immutable archive, manifest hash verification, and startup recovery. Linux-container checkpoint swap/manifest/restart smoke passed. | Exercise interruption recovery, rollback, and coordinated model/config/data sync on actual target host. |

The fair-fight checkpoints and BPE tokenizer asset are local artifacts under ignored `checkpoints/`; the tokenizer was trained from `data/train.txt` only. See `docs/benchmarks/bpe-byte-fair-fight-2026-10-03.md`. Inference and retrieval baselines are in `docs/benchmarks/phase0-local-cpu-2026-10-02.md` and `docs/benchmarks/memory-scale-2026-10-03.md`. The behavioral acceptance rubric is in `docs/GOLDEN_SET.md`, with prompts in `data/golden_set.json`.

## Outcomes and design principles

The production-ready target should provide:

1. Predictable request latency and bounded resource use under concurrent traffic.
2. Memory retrieval that scales beyond a small JSON file and remains useful for exact names as well as semantic queries.
3. Explicit compatibility and migration paths for existing JSON memories and byte-tokenizer checkpoints.
4. Longer-context model variants whose resource requirements are measured and configurable.
5. Conversation continuity with transparent, inspectable summaries and a controllable retention policy.
6. Evaluation-backed model promotion with rollback to a known-good champion.
7. Operational visibility, safe shutdown, recoverability, clear errors, and user-facing documentation.
8. **Multi-user Isolation:** If deployed as a multi-user service, a strict ownership model for sessions and memories is a mandatory release gate. Isolation must be implemented and verified before stores are shared to prevent data leakage between principals.

### Non-goals for the first production release

- Multi-node distributed inference or training.
- Automatically training on private conversations or memory without explicit policy and consent.
- Claiming that a larger context or embedding retrieval alone makes model responses more accurate.
- Replacing every existing store or endpoint in one migration.

### Core engineering rules

- Keep the HTTP contract compatible where feasible; version endpoints or add fields rather than changing existing meanings.
- Put resource limits on queues, batch sizes, prompt tokens, generated tokens, embedding work, and training jobs.
- Avoid unbounded background tasks and make overload behavior explicit (backpressure or a clear `429`/`503`).
- Treat every persistent format as versioned data with a backup, dry-run, and rollback story.
- Pin and document dependencies; optional acceleration packages must not prevent CPU-only installation.
- Use deterministic evaluation inputs and record enough metadata to reproduce a promotion decision.
- Keep operator choices and user controls visible; do not make silent changes to a running model or stored data.

## Current implementation facts

- `/generate` and `/chat` submit inference through a bounded FIFO manager; the worker executes one generation at a time. Dynamic serving batches and arbitrary priorities are not implemented.
- The API uses SQLite as canonical memory, imports legacy JSON idempotently, uses FTS5 lexical candidates, and can optionally blend local embeddings with a rebuildable FAISS HNSW index. SQLite exact cosine remains the fallback. Target-hardware recall and latency have not yet been measured.
- The request benchmark measured CPU inference with p50/p95/p99. The memory benchmark measured the real SQLite search path at 1k, 5k, 10k, and 50k synthetic records. Both are local host measurements and need production hardware re-runs.
- The model supports absolute positions by default and opt-in RoPE. Context length and optional context curriculum are configurable.
- Byte checkpoints remain compatible. BPE checkpoints embed a fingerprinted tokenizer asset. The BPE/byte fair fight is one matched seed only; no promotion has occurred.
- Explicit user-fact extraction, background narrative summaries, per-checkpoint language evaluation, and reviewed promotion tooling are implemented. Training writes candidates only. Full Golden Set scoring still requires human review.
- Two 512-token RoPE candidates were trained and scored. The 2,000-step linear-decay rescue improved NLL from 2.2721 to 1.7709 nats/token and accuracy from 35.09% to 49.65%; both candidates still generate repetitive answers, and neither has independent ratings. Both are rejected; the current champion remains untouched. See `docs/benchmarks/rope-512-candidate-2026-10-03.md` and `docs/benchmarks/rope-512-rescue-2026-10-03.md`.
- Podman’s Linux/amd64 VM built the production image; FAISS 1.15.1 hybrid retrieval, service `/ready`, and a checkpoint promotion/recovery smoke passed in-container. This verifies the Linux x86_64 path, not the hosted ARM64 target. Remote deploy was unavailable because this workspace has no AWS CLI, EC2/ECR target variables, or SSH deploy credentials.
- `docs/OPERATIONS.md` documents the current single-worker process topology and runtime settings; `docs/ARCHITECTURE.md` should remain aligned with the implementation.

## Delivery strategy

Deliver in small, reviewable increments. Each milestone should have: a feature flag or safe default, migration notes, an API/documentation update, focused automated coverage, operational metrics, and a rollback path. Existing byte-tokenizer checkpoints and JSON memories must remain readable until the owner explicitly retires those formats.

Recommended rollout order:

| Stage | Deliverable | Default behavior |
|---|---|---|
| 0 | Baselines, resource budgets, observability, compatibility fixtures | No behavior change |
| 1 | Bounded inference scheduler, then dynamic batching where measured beneficial | Scheduler enabled; batching can be disabled |
| 2 | SQLite memory repository and versioned import/export | Legacy JSON import supported; keyword search retained |
| 3 | Hybrid retrieval and optional local embeddings | Keyword-only fallback remains available |
| 4 | Versioned BPE tokenizer and new model family | Byte-tokenizer checkpoints remain loadable |
| 5 | RoPE and longer-context model configuration | Existing absolute-position checkpoints remain supported |
| 6 | Session summaries and context budgeting | Summaries opt-in until quality is measured |
| 7 | Evaluation reports and champion/challenger promotion | Promotion policy explicit; rollback available |
| 8 | Hardened deployment, runbooks, and production readiness review | Stable defaults documented |

**Sequencing Note:** The order is explicitly set to introduce BPE (Stage 4) before RoPE (Stage 5). This ensures the tokenizer is frozen and the model is stable on the new vocabulary before introducing new position embeddings. Each change must be evaluated independently to isolate the impact on perplexity and generation quality.

---

## Phase 0: Baseline and production foundations

### Objectives

Establish reproducible measurements and compatibility guarantees before optimizing the system.

### Work

1. **Inventory interfaces and persisted formats**
   - Document all routes, status codes, limits, environment variables, CLI entry points, checkpoint fields, memory schema, and session schema.
   - Add compatibility fixtures for a current byte-tokenizer checkpoint and a representative `memory.json`.
   - Define a supported Python/PyTorch/OS matrix and CPU-only install path.
2. **Define workload budgets**
   - Measure p50/p95/p99 request latency, throughput, queue wait, generation time, prompt length, and peak memory on CPU and available CUDA hardware.
   - Record a representative request mix, model size, and generation length. Report results with hardware and software versions.
   - Set configurable defaults for maximum in-flight requests, queue length, queue wait, batch size, batch wait window, and memory use.
3. **Add structured operational signals**
   - Use structured logs with request/job IDs, route, duration, status, model/checkpoint ID, and sanitized error category. Never log API keys or full private prompts by default.
   - Add health/readiness distinction: process alive, model loaded, dependencies/storage ready, and service accepting work.
   - Add counters/histograms for requests, errors, queue depth/wait, generation duration/tokens, retrieval duration, training/evaluation jobs, and promotion outcomes.
4. **Document operating modes**
   - Local development, single CPU host, single GPU host, and reverse-proxy deployment.
   - Explain that process-local model/scheduler state is not shared across multiple Uvicorn workers; define supported worker topology before enabling it.

### Acceptance criteria

- Existing API and checkpoint compatibility are captured as executable fixtures.
- A baseline report can be regenerated on documented hardware.
- Health checks distinguish a live process from a ready model service.
- Logs and metrics can diagnose slow requests without exposing secrets or conversation contents.

---

## Phase 1: Performance and scalability

### 1.1 Bounded inference manager and concurrent request handling

#### Design

Introduce an `InferenceManager` (likely a dedicated module, owned by the application lifespan) as the single admission and scheduling boundary for model inference. `Bridge` remains responsible for context assembly and prompt policy; it should submit a well-defined inference request to the manager instead of owning device execution policy.

An inference request should carry a request ID, encoded prompt, generation options, priority, enqueue time, deadline/cancellation state, and a result future. Define priorities narrowly (for example, interactive chat ahead of explicitly background work) and prevent starvation with aging or fair scheduling. Do not let arbitrary callers select an unrestricted priority.

#### Implementation steps

1. Extract inference calls from endpoint-level `_lock` blocks into an interface such as `manager.generate(request)`.
2. Begin with a **bounded FIFO queue and one execution worker** per model/device. This removes thread contention from route handlers, provides backpressure and queue metrics, and protects GPU/model state while preserving serial behavior.
3. Add explicit overload responses and configurable queue capacity/wait deadlines. Ensure client cancellation removes or marks queued work and does not corrupt active generation.
4. Ensure model promotion is coordinated with the manager: load a candidate separately, atomically swap the active runtime at a safe boundary, and let in-flight requests finish on the runtime they started with.
5. Add optional micro-batching only after measurement. Gather compatible requests for a short bounded window, then batch prompts with correct padding/masks and independent stop conditions. Requests with incompatible sampling settings, context lengths, or model versions may need separate batches.
6. Keep a serial mode for debugging, tiny workloads, and rollback.
7. Add graceful shutdown: stop admission, drain within a configured timeout, then cancel/report remaining work clearly.

> **💡 Implementation Guardrail (Concurrency):** Define a clear boundary: one event-loop-owned scheduler handles the queue and state, while model computation is offloaded (e.g., via `run_in_executor`) to a dedicated device execution policy. Define a "Point of No Return" for cancellation: once a request is batched and sent to the GPU/CPU forward pass, it must complete; only queued or pending requests can be cancelled to avoid corrupting the batch state.

#### Dynamic batch generation requirements

`forward` already handles arbitrary batch dimensions, but autoregressive generation requires more than passing a larger tensor to `forward`. The serving implementation must handle:

- Different prompt lengths using padding and correct attention masks or length grouping.
- Per-request temperature, top-k, stop sequences, maximum tokens, and completion state.
- Finished rows without continuing to sample or leaking tokens into their result.
- A clear policy for random-number generation and reproducibility across batch membership.
- GPU memory bounds, batch admission, and safe fallback when an OOM occurs.
- Prompt truncation policy that preserves the system/template and most relevant recent context.

Initially group requests by compatible generation parameters and similar prompt lengths; do not add a KV cache or speculative decoding until profiling shows they are necessary. If adding a KV cache, test cache invalidation across checkpoint swaps and ensure per-request isolation.

#### API and user experience

- Preserve response shapes for successful requests.
- On overload, return a stable error code and retry guidance (`Retry-After` where meaningful); do not leave clients waiting indefinitely.
- Expose configured limits in `/model` or a capabilities endpoint without disclosing internal secrets.
- Give UI clients clear busy/queued state and allow cancellation where the transport supports it.

#### Acceptance criteria

- No endpoint directly owns a global generation lock.
- At configured concurrency, requests are either completed or rejected within a bounded time; no unbounded queue growth occurs.
- Concurrent requests return the correct independent outputs and options; session turns are appended to the correct session.
- Reload/promotion while requests are active causes no partial weights, mixed runtime state, or lost requests.
- Benchmarks show no material regression for a single request and document throughput/latency tradeoffs for concurrent traffic.
- CPU-only and CUDA execution paths are covered where hardware is available.

### 1.2 Durable memory storage and vectorized retrieval

#### Technology decision

Do not adopt FAISS, ChromaDB, Sentence-Transformers, and `tiktoken` as a bundle by default. Compare dependency size, platform compatibility, persistence, filtering, backup/restore, and operational complexity. The repository already uses SQLite successfully for sessions and knowledge, so evaluate:

- SQLite with a vector extension (only if the extension is dependable on supported platforms),
- SQLite metadata plus a small in-process exact vector index for modest corpora,
- FAISS for larger local indexes with a rebuildable index and SQLite as source of truth,
- a separately operated vector service only when scale justifies that operational burden.

Keep the canonical memory record in a durable store; derived embeddings/indexes must be rebuildable. Do not make an opaque vector index the sole copy of user data.

#### Schema and migration

Define a versioned SQLite schema. The canonical memory record is stored in a `memory` table with fields matching today's records (`id`, `type`, `content`, `importance`, `tags`, `created_at`, `source`). A separate `memory_embeddings` table stores the vectors, keyed by `(memory_id, model_version)`, containing the vector BLOB and embedding status. Use transactions, indexes for tags/time/status, WAL where appropriate, and a migration version table.

Build an idempotent migration command that:

1. Reads and validates JSON without modifying it.
2. Reports record count, malformed records, duplicate IDs, and estimated embedding work.
3. Supports dry-run and explicit destination path.
4. Writes an export/backup before commit and records a content hash.
5. Imports in batches transactionally and can be safely rerun.
6. Verifies count/content parity and search parity before switching the configured backend.
7. Keeps rollback to the JSON source until the operator confirms the migrated store.

> **💡 Implementation Guardrail (Data Integrity):** Preserve memory IDs as the primary identity. Treat content hashes as a deduplication or verification aid, but do not use them as the primary key to avoid collapsing distinct records with identical content. Use `INSERT OR REPLACE` or `UPSERT` logic cautiously to ensure metadata is not accidentally overwritten. Always implement a "Dry Run" mode that validates the data without writing to the database.

#### Embeddings and hybrid ranking

- Create a narrow `EmbeddingProvider` interface with a deterministic local provider and explicit model/version metadata.
- Prefer local inference by default to avoid sending memory contents to an external service. If remote embedding providers are later supported, require explicit configuration and clear privacy documentation.
- Batch embedding generation, cache by normalized content hash plus embedding model/version, and retry bounded transient failures.
- Normalize vectors and use cosine similarity (or equivalent normalized dot product); validate vector dimension, finiteness, and model compatibility.
- **Embedding Alignment Validation:** Before promoting to production, run an A/B test comparing the old keyword baseline vs. the new hybrid retrieval. Measure if the recalled memories actually increase the accuracy of the final response, rather than just increasing semantic similarity scores.
- Implement hybrid ranking: exact identifier/name/tag matches and keyword score combined with semantic score, with configurable weights and tag filters. Avoid a single opaque score; retain score components for debugging.
- Return stable relevance metadata only where useful to clients; never expose internal vectors.
- Re-rank with importance and recency as modest tie-breakers, rather than allowing old high-importance entries to overwhelm semantic relevance.
- Define behavior for empty queries, no embedding provider, stale vectors, and deleted/updated entries.

> **💡 Implementation Guardrail (Versioning):** The embedding configuration (model/version) should be stored in a separate embeddings table keyed by `(memory_id, model_version)`. This allows a single memory record to retain multiple vector versions during re-indexing and prevents the memory record's primary identity from depending on its embedding version.

> **⚠️ Implementation Alert (Drift):** Any update to the `EmbeddingProvider` invalidates existing vectors. Ensure that the system triggers an automatic re-index of all records in the embeddings table for the new `model_version` before promoting the provider to production.

#### Acceptance criteria

- Existing `memory.json` records migrate with IDs, tags, timestamps, and source preserved.
- Search continues to work without optional embedding dependencies.
- Hybrid search improves a fixed query suite for both exact identifiers and paraphrased concepts compared with the keyword baseline.
- Vector indexes can be rebuilt from canonical records and are tied to an explicit embedding model version.
- Migration is idempotent, measurable, and reversible before cutover.
- Search latency and memory use are reported at representative corpus sizes.

---

## Phase 2: Model capacity and tokenizer evolution

### 2.1 Context window expansion and RoPE

#### Compatibility strategy

Do not change the default `block_size` for every existing model at once. Longer context increases attention compute and memory substantially, and old checkpoints have absolute position embedding tensors that are structurally incompatible with RoPE. Introduce an explicit architecture/position-encoding field in model config and checkpoint metadata. Preserve a legacy model implementation/loader for existing checkpoints.

#### Implementation steps

1. Add a RoPE-capable attention path with correct even-dimension handling, causal masking, and offset support needed by any future KV cache.
2. Add configuration validation for RoPE dimensions, base/scaling method, and maximum supported context.
3. **Implement Curriculum Learning for Context:** To mitigate distribution shift and potentially address the "Lost in the Middle" phenomenon, train new models by gradually increasing sequence lengths (e.g., 128 $\rightarrow$ 256 $\rightarrow$ 512) rather than jumping to the max budget immediately. This effect must be explicitly validated via position-sensitive evaluation tests to confirm the model can actually utilize the extended context.
4. Benchmark block sizes 128, 256, 512, and 1024 across model sizes and target hardware; publish tokens/second, peak memory, and training cost.
5. Update `TextDataset`, evaluation, prompt rendering, API limits, and training data validation to use the selected model's true token count rather than assuming bytes once BPE exists.
6. Add context budgeting in the bridge: reserve output tokens, retain system/template instructions, include recent turns, and then rank/truncate optional memories. Report truncation in metadata or diagnostics.
7. Train new RoPE checkpoints from scratch or through a separately validated conversion experiment; never silently reinterpret old absolute embeddings.

> **💡 Implementation Guardrail (Tensor Math):** RoPE implementation is error-prone. Ensure you use `torch.polar` or complex-number rotations correctly. Use "Unit Tests for Tensors": create a tiny $2 \times 2$ matrix and manually calculate the rotation to verify your implementation before applying it to the full model. If the loss spikes or becomes `NaN`, the first place to check is the RoPE rotation logic.

#### Acceptance criteria

- Legacy absolute-position checkpoints load unchanged.
- RoPE outputs have correct shapes, finite loss/gradients, causal behavior, and stable save/load behavior.
- Quality and resource comparisons are recorded at each supported context length.
- API input validation and prompt construction agree on the actual model context budget.

### 2.2 BPE tokenizer as a new model family

#### Technology decision

Choose one tokenizer source of truth. `tiktoken` is a practical implementation when using an established encoding, but it is not by itself a general-purpose training pipeline for arbitrary custom BPE vocabularies. If a custom vocabulary is required, choose and pin a trainer/runtime deliberately. Avoid maintaining overlapping `vocab.json`, `merges.txt`, and package-specific assets unless the chosen tokenizer format requires them.

#### Implementation steps

1. Define a tokenizer protocol (`encode`, `decode`, vocabulary size, stable name/version, special-token handling, asset fingerprint).
2. Store tokenizer identity, configuration, and vocabulary/merge asset hashes in checkpoints. Package or reference immutable assets so inference never depends on mutable files from the current working directory.
3. Introduce byte and BPE tokenizer implementations side by side. Byte checkpoints remain supported indefinitely through their existing tokenizer metadata.
4. **Embedding Stability & Sparsity:** Since BPE significantly increases `vocab_size`, the embedding matrix becomes a dominant parameter block. Choose the final vocabulary size during tokenizer training rather than pruning post-hoc to avoid invalidating token IDs. Use specific weight initialization for rare tokens to prevent "cold" embeddings from causing erratic generation in the compact model.
5. Measure compression ratio, tokenization speed, Unicode round-trip behavior, prompt lengths, and training throughput on representative multilingual/user content.
6. Define special tokens and escaping so user text cannot accidentally impersonate internal chat boundaries or stop markers.
7. Build corpus preparation and a full-retraining workflow, including data split reproducibility, tokenizer training metadata, and checkpoint lineage.
8. Validate that all generation, stop, context, dataset, evaluation, and API limits are expressed consistently in tokens; where the public API currently says “bytes,” preserve/document that legacy behavior or version it.
9. Update docs and model metadata endpoints to tell clients which tokenizer/model family is active.

> **💡 Implementation Guardrail (Unicode/Edge Cases):** Tokenization is a minefield. Always test with "The Chaos Set": include emojis, right-to-left (RTL) text, zero-width joiners, and malformed UTF-8 sequences. Define a precise round-trip contract: identify which inputs are guaranteed `decode(encode(text)) == text` and define a stable fallback behavior (e.g., `<UNK>` or byte-replacement) for malformed inputs that cannot be round-tripped. Use a library like `tiktoken` as a reference for correct BPE behavior.

> **⚠️ Implementation Alert (Symmetry):** Do not change the tokenizer (BPE) and position embeddings (RoPE) simultaneously. This is a high-variance operation. Freeze the tokenizer and train to stability before introducing RoPE.

#### Acceptance criteria

- Byte and BPE checkpoints load only with their matching tokenizer and produce clear compatibility errors otherwise.
- Unicode, malformed input, special tokens, and decode behavior are covered by fixed test vectors.
- BPE training is explicitly a new training lineage; no claim of weight compatibility with the 256-token model.
- Existing API clients retain documented behavior through migration.

---

## Phase 3: Conversational context and retrieval

### 3.1 Durable session summaries and state extraction

#### Summary policy

Summaries are derived context, not an authoritative transcript. To prevent "Information Decay" caused by recursive summarization, the system will prioritize **Structured Fact Extraction** over narrative summaries. The model's own summary can omit or distort facts, so use bounded extraction prompts, identify uncertainty, and never let a summary override explicit user corrections.

#### Implementation steps

1. Extend the session schema with summary text, a structured `facts` JSON field (for entities, preferences, and hard constraints), summary version, covered-through turn sequence, updated timestamp, and optional status/error fields. Add an idempotent SQLite migration.
2. Define configurable thresholds by token budget and turn count; `max_turns` alone is not a good trigger because messages vary in size.
3. When thresholds are crossed, enqueue a bounded background task to:
   - a) Extract a list of key-value facts from the prefix of turns.
   - b) Generate a concise narrative summary for general context.
4. Avoid blocking a user request on summary generation; avoid duplicate jobs per session and handle concurrent appends.
5. Summarize only a stable prefix of turns. Record the exact sequence range covered, include any newer turns normally. If summarization fails, continue with available recent history and expose a retryable status.
6. Pass the `facts` list and the narrative summary separately to prompt rendering, with clear delimiters and token-budget allocation.
7. Add user controls to inspect, refresh, clear, and disable summaries. Deleting a session deletes summaries and turns consistently.
8. Define privacy/retention controls and clarify whether session data is ever eligible for knowledge training (default: no implicit inclusion).

> **⚠️ Implementation Alert (Cold Start):** If the compact model's extraction quality is low, use a frozen "Teacher Model" (e.g., Llama-3 or GPT-4) to generate high-quality initial fact-extractions for the training set to bootstrap the system. This process should be optional, performed offline, and include explicit requirements for licensing, privacy, provenance, and quality review. Avoid relying on a specific teacher model as a hard dependency.

#### Acceptance criteria

- Concurrent appends do not cause turns to be omitted or summarized twice incorrectly.
- Summary coverage boundaries are explicit and no turns are lost from the source transcript because a summary was created.
- Prompt budget remains within model limits for long sessions.
- Summary failure does not make chat unavailable.
- Users can inspect and clear stored session context through documented controls.

### 3.2 Memory-augmented generation / RAG

1. Keep retrieval behind `runtime.recall`/a retrieval service so the bridge does not know storage details.
2. Use hybrid memory retrieval from Phase 1, filtered by tenant/user/session scope. As defined in the production readiness outcomes, strict isolation is a mandatory release gate for any multi-user deployment to prevent data leakage between principals.
3. **Dynamic Context Filtering:** Instead of a fixed "Top-K" retrieval, implement a confidence threshold. This threshold must be calibrated against the retrieval evaluation set to optimize the trade-off between recall and noise, as hybrid ranking scores may not be linear cosine similarities. If no retrieved memories meet the calibrated threshold, the system should omit memory context rather than introducing noise that a compact model might struggle to ignore.
4. Preserve source IDs for traceability and allow clients to see which memories were used when the API contract permits.
5. Support correction/deletion and ensure tombstones propagate to derived vector indexes.
6. Add a fixed retrieval evaluation set with expected relevant records, exact-match cases, paraphrases, false-positive cases, and tag filters.
7. Treat retrieved memory as untrusted content: delimit it, do not execute instructions contained in it, and maintain the system/task instructions' precedence.

#### Acceptance criteria

- Retrieval is scoped correctly and memory IDs in response metadata correspond to the actual context used.
- Prompt construction is bounded by tokens and has tested behavior for empty, irrelevant, or oversized memory results.
- Evaluation reports precision/recall or ranking metrics and includes exact identifiers as well as semantic queries.

---

## Phase 4: Evaluation, promotion, and operations

### 4.1 Evaluation runner and checkpoint quality reports

#### Metrics

- **Perplexity**: compute from a clearly defined token-level cross-entropy over a deterministic held-out split; report loss and `exp(loss)` with handling for overflow.
- **Accuracy**: next-token accuracy may be included as a secondary diagnostic, but it is not a substitute for task quality. 
- **Behavioral Golden Sets:** Maintain a versioned suite of Q&A pairs with expected semantic answers. Measure "Success Rate" (did the model provide the correct fact?) rather than just token probability.
- **Serving quality**: maintain a small versioned prompt suite for regressions in formatting, stop behavior, safety boundaries, memory use, and conversational consistency. Automated text quality metrics should not be treated as ground truth by themselves.
- Record dataset hash, tokenizer/model IDs, evaluation code version, seed, hardware, step, metrics, and timestamp.

#### Implementation steps

1. Create a standalone `eval_runner.py` usable from CLI and job manager, with deterministic inputs and machine-readable JSON output.
2. Separate evaluation configuration from training configuration: dataset, tokenization, sample count, batch size, seed, device, and maximum time/resource budget.
3. Reuse training loss evaluation where appropriate but ensure a complete reproducible held-out evaluation path; avoid selecting a checkpoint based on noisy, tiny random batches alone.
4. Support evaluation cancellation, progress reporting, and clear failures for incompatible tokenizer/data/checkpoint.
5. Store evaluation artifacts alongside each candidate checkpoint and expose progress/results through job status APIs.
6. Version evaluation suites and require explicit acknowledgment when comparing candidates evaluated on different suite/dataset versions.

#### Acceptance criteria

- Same checkpoint and evaluation manifest produce repeatable metrics within documented floating-point tolerance.
- Reports include all provenance needed to interpret a score.
- Evaluation is bounded and cannot consume all inference resources without scheduler policy.
- A failed evaluation cannot accidentally pass a candidate.

### 4.2 Champion/challenger promotion and rollback

#### Promotion policy

Use a configurable promotion policy rather than a hard-coded “significantly better” threshold. It should define primary metric direction, minimum improvement, allowed regression bounds for secondary metrics, evaluation suite/version, and behavior for ties or missing metrics. 

**Statistical Significance:** To avoid promoting models based on random noise, use bootstrap resampling or p-value checks to ensure the improvement in Behavioral Golden Sets is statistically significant before promotion. This requires a fixed, versioned evaluation set and a defined comparison method.

**Generalization Guardrails:** To prevent overfitting to the Golden Set, promotion requires *both* a significant improvement in behavioral metrics *and* a stability check (no significant increase in perplexity) on a separate, stable and versioned held-out set.

Account for metric noise by repeated evaluation or confidence intervals when sample size warrants it.

> **💡 Implementation Guardrail (ML Metrics):** Do not treat a 0.1% improvement in loss as a "win." ML metrics are noisy. Always look at the *trend* across multiple checkpoints and the *distribution* of errors. Behavioral success rates must be mapped to a clear scoring rubric (e.g., binary pass/fail or Likert scale) and may require periodic human review to validate the automatic score. When in doubt, prefer the "Champion" over a "Challenger" that only wins by a tiny margin.

#### Implementation steps

1. Separate candidate checkpoints from the served champion. Training jobs write immutable candidate artifacts; they must not overwrite the active champion directly.
2. Validate candidate loadability, tokenizer compatibility, architecture support, finite weights/metrics, and evaluation manifest before promotion.
3. Compare only like-for-like evaluations under the configured policy. Emit an auditable promotion/rejection record with reasons.
4. Atomically update a small champion manifest pointing to an immutable checkpoint; retain at least the previous champion and its evaluation report.
5. Load the challenger in isolation, warm it if needed, and swap runtime through the inference manager. If load or swap fails, keep serving the existing champion.
6. Provide an authenticated rollback operation and a CLI equivalent. Record actor, timestamp, previous/current IDs, and reason.
7. Add a deployment option for manual approval of promotion; default behavior should be explicit in config and docs.
8. Treat catastrophic health/latency regression as a reason to roll back independently of offline loss improvement.

#### Acceptance criteria

- A worse or unevaluated candidate cannot replace champion under automatic mode.
- Promotion is atomic and leaves a rollback target.
- Interrupted promotion and process restart recover the last valid champion.
- Promotion decisions and rollback are visible in job/model status and logs.

### 4.3 Production operations and user-friendly API

- **Configuration:** validate startup configuration once; report invalid environment variables clearly. Document every limit and default in one reference.
- **Readiness:** do not report ready until storage and active model are available; report degraded state when optional embeddings are unavailable but keyword fallback is active.
- **Errors:** define stable error envelopes/codes for invalid input, missing model/session, overload, cancellation, incompatible checkpoint, and training failures.
- **API usability:** publish OpenAPI examples for chat, sessions, memory, jobs, migration, and evaluation; include curl/Python examples and pagination semantics.
- **Idempotency:** consider request IDs/idempotency keys for operations that create sessions, add knowledge, launch training, or promote models.
- **Rate/resource limits:** configure request body sizes, per-request token caps, queue caps, training concurrency, and per-client rate limits at the trusted proxy/API boundary.
- **Security:** keep API keys out of browser code and logs; use constant-time comparison; separate inference access from training/promotion administration; document TLS/reverse proxy and secret rotation. Verify auth configuration behavior in deployment tests.
- **Multi-user isolation:** if the service will serve multiple users, add principal/tenant ownership to sessions and memories before launch; do not bolt isolation on after shared personal data exists.
- **Storage durability:** document backup/restore for SQLite databases, memory exports, champion manifests, and checkpoint artifacts; test restore, not just backup creation.
- **Shutdown/restart:** graceful draining for inference and jobs, robust startup recovery for queued/running jobs, and explicit policy for interrupted training.
- **Supply chain:** pin direct dependencies, use optional extras for embeddings/vector acceleration, review licenses/model terms for embedding assets, and generate a reproducible lock or deployment artifact.
- **Capacity guidance:** provide a sizing table and benchmark method rather than claiming universal concurrency numbers.
- **User experience:** return actionable validation messages, expose model/tokenizer/context capabilities, preserve session continuity, and explain when context was truncated or a memory backend is degraded.

---

## Cross-cutting testing and quality strategy

Tests are required as part of implementation even when work is split across milestones. Keep unit, integration, migration, API contract, and load/benchmark validation distinct.

### Model and tokenizer

- Shapes, causal masking, batch independence, variable prompt lengths, finish/stop behavior, and numerical stability.
- Checkpoint round-trip for every supported architecture/tokenizer family.
- Unicode, malformed input, special-token boundaries, and deterministic fixture cases.

### Scheduler and API

- Queue bounds, overload, cancellation, deadline, fairness, graceful shutdown, runtime swap, and concurrent session writes.
- Successful response compatibility and stable overload/error response contracts.
- Multi-request isolation for temperature/top-k/stop/max-token options.

### Storage and migration

- Transaction rollback, duplicate/import idempotency, data parity, indexes, WAL/restart behavior, and backup restore.
- JSON migration fixtures with unusual Unicode, optional source, tags, and malformed rows.
- Vector rebuild, embedding version mismatch, failed embedding, deletion propagation, and keyword-only fallback.

### Summaries and retrieval

- Summary boundary correctness, append races, summarization failure fallback, deletion, and token budgeting.
- Retrieval ranking suite for exact IDs, paraphrases, irrelevant queries, tags, and privacy scopes.
- Prompt injection-like content in memory remains quoted data and does not override prompt instructions.

### Training/evaluation/promotion

- Reproducible eval manifests, failed/incompatible eval, candidate rejection, promotion success, rollback, and interrupted promotion recovery.
- Ensure a model with improved validation loss but unacceptable task-suite regression is handled according to policy.

### Performance and deployment

- Benchmark single-request latency as well as concurrent throughput and p95/p99 latency under bounded load.
- Test CPU-only installation and optional dependency absence.
- Test supported server worker topology and document process-level limitations.
- Exercise clean startup, missing/corrupt checkpoint, database unavailable, disk full, graceful shutdown, and restore procedures.

## Suggested repository structure after implementation

Names are provisional; keep modules small and avoid premature abstractions.

```text
pranav/chit/
  inference.py            # bounded manager, scheduler, batching policy
  embeddings.py            # embedding provider protocol and implementations
  memory.py                # stable memory repository API and hybrid retrieval
  migrations/              # versioned storage migrations or migration registry
  evaluation.py            # reusable metrics and evaluation manifests
  eval_runner.py           # CLI entry point (or tools/eval.py)
  sessions.py              # session and summary persistence
  training.py              # optimization loop; candidate artifacts and eval hooks
```

Avoid splitting files only to match this list if the implementation remains cohesive.

## Configuration additions to consider

Configuration names must be finalized with the existing environment-variable and JSON-config conventions. All defaults should be conservative and validated.

- Inference: `max_queue_size`, `queue_timeout_seconds`, `max_batch_size`, `batch_wait_ms`, `max_inflight_generations`, scheduler mode.
- Memory: backend, database/index path, embedding provider/model/version, hybrid score weights, embedding batch size, semantic threshold, fallback mode.
- Model: architecture type, position encoding, context limit, tokenizer identity/assets, generation safety limits.
- Sessions: summary enabled flag, token threshold, turn prefix size, summary model/policy, retention days.
- Evaluation/promotion: evaluation suite, dataset hash, promotion mode, primary metric, minimum improvement, allowed regressions, retained champion count.

Do not duplicate configuration in environment variables, JSON, and API overrides without a clear precedence rule. Return effective non-secret configuration in diagnostics.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Dynamic batching increases single-request latency or produces incorrect stop behavior | Start with bounded serial scheduler; enable batching behind a flag; compare output isolation and latency benchmarks |
| Optional vector dependencies fail on a platform or inflate installs | Keep canonical SQLite data and keyword fallback; package acceleration as optional extras; test clean CPU installation |
| Embedding model is slow, costly, or leaks private text | Prefer local embeddings; batch/cache; explicit privacy configuration; bounded queues and transparent fallback |
| JSON-to-SQLite migration loses records or metadata | Dry-run, backup, hash/count parity, idempotent import, dual-read validation, reversible cutover |
| Larger context exhausts memory and slows training | Benchmark per hardware tier; configure per-model limits; do not raise default until measured |
| BPE checkpoints are incompatible with existing weights/data/API assumptions | Version tokenizer/model family; retain byte loader; require full retraining and migration documentation |
| Summaries omit or distort earlier facts | Preserve source turns per retention policy; expose summary; track covered range; allow correction/clear; fallback gracefully |
| Offline loss improvement harms real responses | Add versioned task suite and regression bounds; manual promotion option; rollback and health checks |
| Multiple workers duplicate queues/models or training jobs | Document single-process topology or introduce external coordination before enabling multiple workers |
| More controls make the product difficult to use | Provide safe defaults, clear capability/status responses, helpful errors, and a small set of documented presets |

## Definition of production-ready

Chit is ready for a production deployment only when the deployment's chosen profile satisfies all of the following:

- Supported install and deployment steps are reproducible.
- API authentication, administrative access, secret handling, and user data scope are documented and verified.
- Inference admission is bounded and observable; overload and shutdown behavior are known.
- Persistent stores have tested backup, migration, and restore procedures.
- Every served checkpoint has compatible model/tokenizer metadata and a recoverable promotion history.
- Evaluation results and promotion decisions are reproducible and auditable.
- Context, retrieval, and generation resource limits are explicit and visible to clients/operators.
- The service has been load-tested on its target hardware and its capacity limits are documented.
- Operational runbooks cover degraded dependencies, failed jobs, rollback, disk pressure, and recovery.

Production readiness is profile-specific: a local CPU deployment and a shared GPU service have different capacity and isolation requirements. The project should state which profile each release supports.

## Release checklist

- [ ] All migrations have dry-run, backup, parity verification, and rollback instructions.
- [ ] Existing byte checkpoints and API clients are covered by compatibility tests.
- [ ] Optional dependencies are pinned, licensed, and tested absent/present.
- [ ] API and configuration docs match actual defaults and limits.
- [ ] Structured logs and metrics contain no secrets or unintended prompt data.
- [ ] Load, latency, memory, and recovery results are attached to the release.
- [ ] Champion checkpoint and previous rollback checkpoint are verified.
- [ ] User-facing docs explain model/tokenizer, context, memory, session, and retention behavior.
- [ ] Deployment and incident runbooks are reviewed against an actual restore/rollback exercise.

---

## Phase 9: Deployment & State Orchestration

### Objectives
Ensure that the "Brain-Body" alignment is maintained during updates. Prevent crashes or erratic behavior caused by mismatched versions of code, weights, and configuration files during EC2 deployments.

### Work

1. **Define Atomic Promotion Sequence**
   Establish a strict order of operations for updates to prevent the service from loading incompatible state:
   - **Step 1: Config Sync** $\rightarrow$ Push new `.json` configs to define architecture changes (e.g., `vocab_size`, `block_size`).
   - **Step 2: State Sync** $\rightarrow$ Push new checkpoints and data files to the EC2 volume.
   - **Step 3: Schema Migration** $\rightarrow$ Execute the Phase 1.2 migration script on the target instance to update the SQLite DB.
   - **Step 4: Image Deploy** $\rightarrow$ Pull and restart the Docker container with the new code.

2. **Versioned Config Loading**
   Modify `config.py` and the `Bridge` to support versioned config paths. Instead of a static filename, allow the deployment workflow to specify a config version (e.g., `CHIT_CONFIG_VERSION=v2`), enabling a safe side-by-side rollout of new architectures.

3. **Startup Compatibility Check**
   Implement a "State Guard" in the application startup sequence. The service must verify that:
   - The loaded checkpoint's metadata matches the active `config.json`.
   - The SQLite memory schema version is compatible with the current code version.
   - If a mismatch is detected, the service should fail fast with a `CRITICAL` error rather than starting in a degraded or unstable state.

4. **Sync Verification Pipeline**
   Integrate the `sync-data-ec2.yml` workflow with a verification step. After syncing, the workflow should trigger a lightweight health check endpoint that reports the hashes of the synced weights and configs to ensure the "Body" is ready before the "Brain" (image) is updated.

### Acceptance criteria

- Deployments follow the defined sequence without manual intervention.
- Incompatible config/weight pairs are detected at startup, preventing "Brain-Body Mismatch" crashes.
- Deployment workflows can target specific config versions for a controlled rollout.
- The system can recover from a failed sync by rolling back to the previous known-good config/weight pair.
