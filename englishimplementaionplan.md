# English Linguistic Capability — Implementation Plan

**Status:** Ready for implementation  
**Scope:** English language foundation for Chit  
**Primary preset:** `configs/chit_assistant_cpu.json`  
**Owner-facing principle:** Improve measurable language behavior while preserving the current model, tokenizer, data, and candidate-promotion safeguards.

## 1. Purpose and expected result

Implement the English-language foundation described in the technical specification across three capabilities:

1. **Structural fluency:** produce grammatical English sentences and recognize common sentence forms, including questions, statements, commands, and simple clauses.
2. **Conversational protocol:** follow the existing `Task: chat` / `User:` / `Chit:` format, distinguish common intents such as greetings and information requests, and use explicitly supplied earlier turns to resolve simple references.
3. **Lexical mapping:** improve the model’s ability to use English words in varied contexts and respond to familiar concepts in new wording.

Deliver this as a reviewed capability dataset, repeatable training recipe, and held-out behavioral evaluation. The existing byte-level Transformer remains a next-byte predictor. Better language behavior is an empirical result of its learned statistical representations; this work must not describe training as converting it into a symbolic language parser or guarantee human-like understanding.

## 2. Repository fit and current baseline

The project already has much of the foundation this plan should extend:

- `pranav/chit/model.py`, `tokenizer.py`, `data.py`, and `training.py` implement a causal decoder-only model, default byte tokenizer, dataset windows, and AdamW training. BPE is an optional checkpoint-bound tokenizer, not a prerequisite for this work.
- `configs/chit_assistant_cpu.json` is the right starting preset: CPU, 512-byte context, 4 layers, 4 heads, 128-dimensional embeddings, 1,500 steps, and the shared `data/train.txt` / `data/eval.txt` paths.
- Assistant-style examples already exist in `data/train.txt`; the corpus has substantial prose and more than 300 `Task:` / `User:` / `Chit:` markers. `data/eval.txt` is held out and includes behavioral pairs as well as seed prose. Do not replace or overwrite either file as an unreviewed side effect.
- `data/prompts.txt` is a separate challenge prompt set; it is not implicitly part of training.
- `data/golden_set.json` is a frozen 50-case behavioral gate with category, criticality, and two-reviewer rules in `docs/GOLDEN_SET.md`.
- `pranav/chit/tools/eval_runner.py`, candidate evaluation, and explicit champion promotion already exist. Training produces a candidate; promotion is a separate reviewed operation. Preserve this workflow.
- `/chat` adds up to eight recent session messages and up to five recalled memories through the bridge. This runtime-provided context must be distinguished from language behavior learned in the weights.

Before implementation, inspect the live code and current files rather than assuming all documentation snapshots are current. In particular, use the current API and evaluation behavior from `docs/TRAINING_API.md`; do not rely on older API prose that describes successful training as immediately promoting a checkpoint.

## 3. Non-goals and guardrails

- Do not add an intent-classification network, parser, POS tagger, external LLM, or online lookup service in this scope.
- Do not change the core model architecture, default tokenizer, public API schema, session format, memory system, or knowledge lifecycle unless a measured blocker requires a separate, explicitly scoped change.
- Do not train on Golden Set prompts, answers, challenge evaluation prompts, or any final gate references. Do not tune examples or decoding against their output.
- Do not promise persistent reference resolution beyond the model’s context window or supplied session summary. A model cannot reliably use a referent that is absent from its prompt.
- Do not equate lower byte loss with grammaticality, correct intent handling, or coherent dialogue.
- Do not scrape or add third-party corpora without source, license, attribution, privacy, and redistribution review. The current corpus documentation says project-written examples are used and governed by the repository license.
- Do not promote a candidate automatically. Keep the existing two-reviewer, hash-bound candidate gate and rollback path.

## 4. Capability specification

### 4.1 Structural fluency (“How”)

Cover these English constructions with both recognition-in-context and natural completions:

- Declarative, interrogative, imperative, and exclamatory sentences.
- Simple and compound clauses; common subordinate clauses (because, although, when, if, before, after).
- Subject–verb agreement for singular/plural subjects, including intervening phrases and common irregular forms.
- Present, past, and future time references; basic tense consistency in a short answer or paragraph.
- Pronouns, determiners, articles, prepositions, auxiliaries, negation, and common contractions.
- Coordination, comparison, quantities, dates/times, and punctuation/capitalization.
- Common transformations: question to statement, statement to question, tense change, polite rewrite, concise rewrite, and correction with meaning preserved.
- Realistic variation in subject names, vocabulary, sentence length, and order. Avoid teaching a single rigid template as “grammar.”

Examples should reward correct, clear English and preserve the user’s requested meaning. Do not turn the dataset into isolated grammar drills only: include ordinary prose so the patterns connect naturally.

### 4.2 Conversational protocol (“Who”)

- Keep the production-compatible prompt layout and speaker names: `Task: chat`, optional context, `User: ...`, then `Chit:`.
- Teach the model to answer as Chit, avoid emitting a second `User:` turn, and stop at the configured assistant turn marker.
- Cover social openings (hello, thanks, goodbye), direct questions, requests, corrections, follow-up questions, and underspecified requests.
- Include explicit multi-turn examples in which the second user message uses an unambiguous pronoun or demonstrative whose referent appears in the immediately preceding context.
- Include contrast cases where multiple possible referents exist or no referent was provided; the preferred response asks a short clarifying question or states what is missing rather than inventing a referent.
- Include minimal pairs that separate greeting from information request, e.g. “Hi” vs. “What time is it in this schedule?” Do not assume a greeting requires a lengthy answer.
- Vary tone neutrally and respectfully without making unsupported claims about a fixed persona. “Identify as Chit” means respond under the `Chit:` speaker label and answer honestly if asked what it is; it does not mean claim capabilities the system lacks.

### 4.3 Lexical mapping (“What”)

- Use varied, high-quality English prose across everyday domains, registers, and sentence structures.
- Include paraphrases, near-synonyms, antonym contrasts, word-in-context examples, and short passages whose surrounding context disambiguates common polysemous words.
- Teach relationships through use in complete sentences and brief passages, not a large disconnected glossary.
- Include common morphology (walk/walked/walking; clear/clearly/unclear) and ordinary spelling/punctuation variants where appropriate.
- Maintain a clear separation between broadly useful English language material and project-specific facts. Put reviewed Chit/Atmini facts in their own source category so the mixture can be measured and adjusted.
- Do not claim a word has been learned semantically from co-occurrence alone. Validate with held-out usage and paraphrase cases.

## 5. Dataset design

### 5.1 Source layout and provenance

Keep the current production files intact until a candidate corpus has passed review. Add a versioned source layout such as:

```text
data/english_capability/
  README.md                 # scope, curation rules, source and license policy
  manifest.json             # version, source ids, hashes, counts, split assignment
  language_patterns.txt     # reviewed grammar, paraphrase, and natural prose items
  conversation_templates.txt# reviewed one-turn and multi-turn chat examples
  project_facts.txt         # approved Chit/Atmini facts, clearly distinct from language material
  eval_grammar.txt          # private/held-out structural evaluation cases
  eval_conversation.txt     # private/held-out intent, turn-taking, and reference cases
  eval_lexical.txt          # private/held-out word-in-context and paraphrase cases
```

The exact extension/format may follow the repo’s current flat text corpus conventions. Each training item should be serialized in the same format consumed by `TextDataset`; assistant exchanges use the existing prompt template. Keep the manifest machine-readable even if the underlying corpus is plain text.

For each source group, record:

- Stable example ID; capability tags; language (`en`); split; source description; authorship/license; and optional reviewer/status.
- UTF-8 byte size, item count, SHA-256, date added, and generator/curator if project-authored.
- Template family ID, so near-duplicate variants can be kept in one split and not leak between training and evaluation.
- For held-out behavior items: prompt, expected properties, acceptable answer characteristics, disallowed failure, and criticality; never put exact answers into training.

Do not generate the final held-out items by mechanically copying and swapping names from the training set. Use template-family grouping and semantic review to prevent leakage.

### 5.2 Coverage and quality targets

Build a first reviewed tranche sized for controlled CPU experiments, not for a 200 MiB upload ceiling. Initial target: **1,500–3,000 training examples**, with a balanced distribution approximately:

| Source family | Initial share | Target count (at 2,000) | Main coverage |
| --- | ---: | ---: | --- |
| Natural English prose and word-in-context | 35% | 700 | Connective language, vocabulary in context, varied clause patterns |
| Structural grammar and meaning-preserving transformations | 30% | 600 | Agreement, tense, questions/statements, clauses, corrections |
| Conversational protocol and intent | 25% | 500 | Greetings, questions, requests, turn boundaries, clarifications |
| Project-specific facts and identity | 10% | 200 | Correct Chit/Atmini facts, distinct from general language examples |

These are starting ratios, not a permanent policy. The actual mixed training implementation must sample by source category (Section 6), because raw line proportions alone do not ensure that categories appear evenly in random byte windows. Keep examples diverse in length; report both example counts and UTF-8 byte counts. Avoid letting repeated copies of short template examples dominate byte windows.

Review checklist for every batch:

1. Correct and natural English; no accidental malformed examples presented as targets.
2. Target answers satisfy every stated constraint and preserve meaning.
3. Speaker and turn markers are consistent with `render_chat_prompt` and stop behavior.
4. Pronoun targets are supported by visible context; ambiguous cases explicitly allow/expect clarification.
5. No exact or near duplicate across train/eval; no Golden Set or challenge-set leakage.
6. License/source/provenance is recorded; private user conversation data is excluded unless separately authorized and privacy-reviewed.
7. Project facts agree with the current canonical project docs; outdated facts are removed or versioned.

### 5.3 Training and evaluation splits

- Preserve `data/eval.txt` as the existing assistant preset’s held-out evaluation file. Any migration or replacement must be a separately reviewed, hashed change.
- Create additional English capability evaluation suites that are not appended to `train.txt` or `knowledge.db`.
- Split by source/template family, not individual rows, to reduce paraphrase leakage.
- Keep `data/golden_set.json` frozen and independent. Run it as the project-wide behavior/promotion gate, not as a curriculum source.
- Keep challenge prompts from `data/prompts.txt` as a separate qualitative suite; record results separately from scored curated evaluation.
- Before training, run duplicate/near-duplicate checks, byte counts, split overlap checks, UTF-8 validation, and context-fit checks. The existing `GET /data` may inspect only the selected config’s two files; add a dataset audit command/report for category and split integrity rather than assuming `/data` covers these conditions.

## 6. Training approach

### 6.1 Phase A — Baseline and diagnostic

1. Record a baseline from the current champion and an unmodified fresh `chit_assistant_cpu` scratch candidate where feasible.
2. Freeze exact Git revision, config, corpus hashes, tokenizer/checkpoint hashes, seed, hardware, decoding settings, and evaluator version.
3. Run existing `eval_runner.py` on the held-out text and Golden Set. If prompts do not fit the model’s context, classify them as **not scorable** and fix context setup or candidate capacity; never count truncation as a pass.
4. Add and run the English-specific evaluation suite before using it for model selection. The baseline report establishes per-category failure modes.

### 6.2 Phase B — Linguistic priming

Train a fresh candidate (`init: scratch`) on reviewed language material: structural patterns, conversational templates, and natural prose. Do not include project-specific fact repetition in this phase beyond the minimal Chit prompt-format examples needed to learn the serving protocol.

Use `configs/chit_assistant_cpu.json` as the architecture/optimizer starting point. Do not assume its existing 1,500 steps is sufficient for a larger dataset. Run a small compute ladder (for example 300, 750, then 1,500 steps) and compare held-out bits per byte plus behavioral categories. Set a maximum run budget based on measured CPU throughput/RAM; do not increase `max_steps` solely because training loss remains high.

Acceptance for priming is diagnostic rather than a release gate: training completes without NaN/Inf, held-out English loss improves or remains stable relative to the baseline, no major behavioral category regresses, and generated output passes basic repetition/collapse checks. A language-model loss reduction alone does not count as capability completion.

### 6.3 Phase C — Mixed-stream integrated learning

The current training loop reads one configured train text and draws random contiguous token windows. Concatenating several corpus files can cause byte-window sampling to follow byte share and cross item boundaries; it does not implement a guaranteed per-batch source ratio. Choose one of these approaches after a small benchmark:

**Preferred implementation (if source-aware sampling is maintainable):** extend training data/config to define named source files or source spans and target sampling weights. Each batch draws windows from source groups using configured probabilities, while preserving random windows within each source. Store source hashes, weights, and actual sampled counts in job/checkpoint metadata. Validate weighted frequencies over a long deterministic sampling run.

**Minimal implementation (if API compatibility and schedule scope favor no sampler refactor):** build a deterministic, reviewed mixed-stream dataset with controlled category byte proportions; keep each example separated with explicit boundaries, shuffle item order with a recorded seed, and train on the resulting file. Document that this approximates a ratio by bytes and does not guarantee every batch’s ratio. Avoid repeated-example oversampling that produces obvious loops.

Starting mixed-source weights: language patterns/prose **60%**, conversational templates **30%**, project facts **10%**. Measure the distribution of sampled windows and evaluate all three capability groups. Adjust weights only using the development suite, not the frozen Golden Set. Keep the final held-out suites untouched.

Do not fine-tune only on new facts: the spec’s core risk is language/turn-taking regression during fact learning. Compare a scratch integrated candidate against a primed candidate fine-tuned with the mixed stream. If fine-tuning (`init: current`/`auto`) materially harms grammar, lexical, or conversation scores, reject it; do not hide the regression by changing the gate after seeing outputs.

### 6.4 Checkpoint lifecycle

- Submit jobs with `promote: false` (or the current API’s candidate-only semantics); retain run manifests and per-job datasets.
- Evaluate the candidate with `python -m pranav.chit.tools.eval_runner` and produce response exports for the English suite and frozen Golden Set.
- Have two independent reviewers score behavioral cases using explicit criteria. Resolve disagreements and preserve raw candidate outputs.
- Use existing `promote_candidate.py` requirements for champion comparison, matching data hashes/tokenizer family, held-out regression limits, and rollback manifest. Do not weaken them for this feature.
- Only a candidate that passes existing promotion requirements plus the English gate below is eligible for manual promotion.

## 7. Capability validation (“The Gate”)

### 7.1 English test suite construction

Create a separately versioned suite with at least **120 held-out cases** for the first release candidate, balanced across:

| Category | Minimum cases | Example task types |
| --- | ---: | --- |
| Grammar and sentence structure | 30 | Agreement completion, tense consistency, question/statement recognition, grammatical rewrite |
| Conversational protocol and intent | 30 | One-turn greeting, thanks, direct request, correction, concise response and correct turn ending |
| Contextual continuity | 30 | Clear pronoun resolution across one or two visible turns, contrast against ambiguous/missing referent |
| Lexical use and paraphrase | 30 | Word-in-context, short paraphrase, synonym/contrast in context, novel wording of a familiar relationship |

Use a held-out case format comparable to `data/golden_set.json`: stable ID, category, prompt/context, acceptance criteria, must-avoid, critical flag, and version. If the existing evaluator schema is too specific, add a general suite adapter without changing Golden Set behavior. Store no answer string as a brittle exact-match requirement unless the task itself requires an exact transformation; score criteria, not style imitation.

### 7.2 Metrics and scoring

Report independently (never combine into a single loss metric):

- **Grammar:** percentage passing, with subcounts for agreement, tense, clause/sentence form, and meaning-preserving transformation. A pass must be grammatical and preserve task meaning.
- **Protocol/intent:** percentage passing for speaker/turn behavior and correct broad response type (greeting vs. information/request). Fail if it emits unintended speaker markers or ignores the request.
- **Continuity:** percentage correct when the referent is explicit; for ambiguous/no antecedent, percentage that asks or appropriately states uncertainty. Report these two subsets separately.
- **Lexical/paraphrase:** percentage with contextually appropriate word use and semantic preservation on novel wording.
- **Generation health:** empty-output rate, repeated 3-gram/byte-loop rate, premature stop rate, and prompt/context truncation count.
- **Language-model signal:** held-out bits per byte from the existing evaluator; compare only with identical held-out bytes and tokenizer-aware metrics.

Run deterministic greedy decoding (`temperature=0`) with the production assistant prompt template and identical generation budget for compared candidates. Where temperature or sampling is part of intended production behavior, report a separate sampled stress run and do not substitute it for the reproducible gate. Disable memory and use fresh sessions so the test measures weights and prompt format rather than accidental retrieval/history.

### 7.3 Pass criteria

An English capability candidate is eligible for promotion only when all are true:

1. At least **85% overall** pass on the English suite (at least 102/120 on the minimum-sized suite).
2. At least **80% in each of the four categories**.
3. At least **90%** on unambiguous contextual continuity, and at least **80%** on ambiguous/missing-antecedent cases that require clarification/uncertainty.
4. **Zero critical failures**: fabricated antecedents, wrong speaker/turn behavior, confidently incorrect response where the test requires clarification, or output collapse that makes the answer unusable.
5. Every case is scorable with full prompt context; any truncation blocks the gate until capacity or test setup is corrected.
6. No regression that violates the existing Golden Set gates or the candidate-promotion comparison requirements.
7. Two independent reviewers score every generated case. Set version/hash, checkpoint hash, tokenizer hash, corpus manifest, config, seed, runtime version, and raw outputs are retained.

The 85% threshold is an initial release floor, not a claim of general English competence. Expand the suite and raise thresholds as more cases, reviewers, and operating experience become available. Passing this limited set demonstrates only measured behavior on those distributions.

### 7.4 Test case examples (illustrative only)

These examples are specifications for case families, **not final held-out prompts**:

- Agreement: “The box of pencils ___ on the desk.” Expected: singular agreement; score grammaticality, not just a token string.
- Tense: context says an event happened yesterday; request a one-sentence recap. Fail tense drift that changes event timing.
- Intent: “Hi!” should receive a brief greeting; “Hi, what is the capital named in this paragraph?” is an information request.
- Explicit reference: prior turn names one book, then “Where did she put it?” where the antecedent is clear from the full supplied context. Score only facts supported by that context.
- Ambiguous reference: prior turn mentions two objects, then “Can you move it?” Expected: clarify which object; do not select one arbitrarily.
- Lexical context: a polysemous word appears in a short disambiguating sentence and the model must paraphrase the intended sense.

## 8. Implementation work breakdown

### Workstream 1 — Data audit and capability inventory

1. Inventory current `data/train.txt`, `data/eval.txt`, `data/prompts.txt`, `data/golden_set.json`, and all configs that point to them.
2. Count examples and bytes by capability, language, template family, and split; flag duplicates, malformed protocol examples, and contexts that exceed 512 bytes.
3. Record a baseline manifest and evaluation report. Identify missing English forms from Section 4.
4. Decide whether to preserve the current `data/eval.txt` exactly or create a new versioned eval file; record hashes before any edit.

**Deliverables:** inventory report, gap list, baseline report, source/license policy.

### Workstream 2 — Corpus authoring and review

1. Create the `data/english_capability/` layout and schema/manifest.
2. Author the first 1,500–3,000 examples, prioritizing gaps shown by inventory and baseline.
3. Keep project facts in their own source group and review them against canonical docs.
4. Assign template families and split before tuning/training. Run exact and normalized duplicate checks; manually review near duplicates.
5. Have a second reviewer audit grammar, answer quality, protocol format, and provenance.

**Deliverables:** versioned corpus sources, manifest, review record, train/eval integrity report.

### Workstream 3 — Data pipeline and weighted mixed sampling

1. Prototype the deterministic mixed-stream file approach using the existing `TextDataset` and current trainer.
2. Measure actual source/category window representation under random window sampling; do not infer it from raw item counts.
3. If byte-proportion mixing fails to meet the desired exposure or creates boundary artifacts, implement source-aware sampling behind explicit config fields while preserving default config behavior.
4. Validate reproducibility from seed and source hashes; persist mixture configuration and realized counts in checkpoint/job metadata.
5. Keep API training payload strict and bounded. Add request/config validation only if source-aware fields are exposed through the API; a local-only experiment need not expand the public API.

**Deliverables:** repeatable dataset builder or sampler, audit output, backward-compatible config, tests for boundaries/weights/determinism.

### Workstream 4 — Evaluation runner and reports

1. Define a versioned English-suite JSON schema and reviewer rubric.
2. Integrate evaluation with existing `eval_runner.py` or add a focused tool that reuses `ChitRuntime`, `render_chat_prompt`, checkpoint loading, tokenizer metadata, and deterministic generation.
3. Reject or mark not-scorable any prompt that exceeds checkpoint context; never silently truncate critical context.
4. Export raw output, per-case token/context lengths, hashes, category summaries, and generation-health metrics.
5. Accept hash-bound two-reviewer ratings and calculate category and gate results. Keep existing Golden Set calculations and candidate promotion rules unchanged.

**Deliverables:** held-out suite, evaluator, sample report, reviewer template, regression checks.

### Workstream 5 — Training experiments and candidate selection

1. Train baseline and priming candidates with fixed seeds/settings and no promotion.
2. Run the training compute ladder on the target CPU; record wall time, peak memory where available, train/eval loss, generation-health metrics, and behavioral results.
3. Train mixed-stream candidates using the documented ratios; run multiple seeds for finalists if resource budget allows.
4. Compare against the current champion and against the primed candidate; inspect category-level regressions and raw outputs.
5. Promote only through the existing explicit reviewed process, retaining champion manifest and rollback ability.

**Deliverables:** experiment matrix, candidate evaluation reports, selected mixture/config rationale, promotion/rollback record if approved by gates.

## 9. Proposed tests

Do not add brittle tests that claim model quality based on a single generated string. Add deterministic tests for infrastructure and use reviewed model-output evaluation for capability claims.

### Data and split tests

- Manifest schema, hash, UTF-8 decode, category counts, source attribution, and stable split reproducibility.
- No duplicate/template-family leakage across train and each held-out set; Golden Set IDs/prompts/references stay excluded.
- Every conversation example uses valid protocol markers and item boundaries; examples over context budget are flagged.
- Source weights are validated (nonnegative and sum to one within tolerance); sampled source frequencies converge within a documented tolerance under fixed seed and sufficient draws.
- Mixed stream has separators and cannot accidentally merge an assistant answer into a following user prompt.

### Training/runtime tests

- Existing byte/BPE checkpoint and default configs remain backward compatible.
- Training metadata records dataset/source hashes, weights, seed, and realized examples/windows for the candidate.
- A mini training run remains deterministic enough for the project’s stated reproducibility level and handles cancellation/failure without changing the champion.
- Evaluation uses the same `render_chat_prompt` and stop markers as production assistant mode; memory is disabled for the controlled benchmark.

### Evaluation tests

- A prompt that exceeds context is marked not scorable and cannot pass.
- Report hashes bind suite, checkpoint, tokenizer, and corpus/config identifiers.
- Category thresholds and zero-critical-failure conditions are computed correctly, including missing cases/reviewer disagreements.
- Raw outputs and scoring are retained; exact-match is not imposed where paraphrases are valid.
- Existing Golden Set and candidate promotion tests continue to pass without reduced thresholds.

## 10. Risks and mitigations

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Small model/corpus capacity | Current assistant preset is about 0.9M parameters and 512 byte tokens; fluent generalization may remain limited. | Stage corpus and compute, report full prompt fit, expand model/context only with measured evidence and separate benchmark. |
| Byte-tokenizer cost | English text is many tokens/bytes, so examples and chat context consume capacity quickly. | Track UTF-8 byte lengths, keep evaluation prompts realistic, and test optional BPE as a separate matched experiment rather than mixing tokenizer changes into this plan. |
| Template overfitting | Thousands of near-identical templates can teach surface forms without generalization. | Group by template family, vary syntax meaningfully, use held-out paraphrases, and review novelty. |
| Catastrophic forgetting | Fact-heavy fine-tuning can weaken English patterns. | Maintain language-heavy replay in mixed stream; compare against primed checkpoint and reject category regression. |
| Boundary artifacts in flattened text | Random byte windows can cross between unrelated examples. | Use explicit separators and source-aware sampling if byte-mix prototype shows boundary issues; add boundary tests. |
| Loss/generation mismatch | Lower NLL can coexist with repetitive or unhelpful answers. | Keep behavioral scoring and generation-health diagnostics as separate gates. |
| Evaluation leakage | Tuning against held-out prompts invalidates the gate. | Freeze suite hashes; use a distinct development set for iteration; only version the final suite through reviewed additions. |
| Identity overclaim | Training “persona” examples may encourage unsupported claims. | Define persona as speaker/communication convention and factual identity response; include uncertainty and capability boundaries. |
| Ambiguous pronouns | A model may hallucinate a referent. | Evaluate explicit, ambiguous, and absent antecedents separately; require clarification in ambiguous cases. |
| CPU budget | Longer corpora do not automatically improve a fixed-step run; training remains compute-limited. | Benchmark wall time and memory; use staged runs and bounded budgets; report examples/windows seen. |
| Corpus rights/privacy | External or private text can create legal/privacy and reproducibility issues. | Prefer project-authored licensed material; record provenance and exclude private transcripts absent a reviewed policy. |

## 11. Decisions to make before implementation

Resolve these in the implementation issue/PR before changing data or training behavior:

1. **Training path:** source-aware sampler (preferred when maintainable) or deterministic materialized mixed stream for the first iteration.
2. **Corpus versioning:** whether the new English sources produce a new assistant preset/data path or are built into the current `data/train.txt`; default recommendation is a versioned input/preset so current reproducibility is preserved.
3. **Eval ownership:** maintain the existing held-out eval unchanged and add an English suite, or version both after baseline hashes and reviewers approve the split. Do not silently overwrite the current eval set.
4. **Initial hardware budget:** confirm the target CPU/RAM and acceptable wall-clock per candidate before selecting final step count/model size.
5. **Gate reviewer availability:** name two reviewers and define an adjudication process before collecting candidate outputs.

These decisions do not block the read-only inventory, baseline capture, corpus schema, or evaluation-suite design.

## 12. Completion checklist

- [ ] Current corpus/config/checkpoint baselines and hashes recorded.
- [ ] English capability inventory identifies gaps in structure, dialogue, continuity, and lexical use.
- [ ] Reviewed, provenance-tracked, versioned corpus meets agreed coverage and split rules.
- [ ] Mixed-stream approach is deterministic, audited by sampled windows, and does not change legacy behavior by default.
- [ ] English held-out suite has at least 120 cases, four balanced categories, explicit ambiguity tests, and no train leakage.
- [ ] Evaluator uses production prompt formatting, disables memory, detects context overflow, and emits hash-bound raw outputs/reports.
- [ ] Candidate is evaluated for language-model loss, behavioral pass rates, generation collapse, and per-category regressions.
- [ ] Two independent reviews are complete; all critical failures are resolved; English and existing Golden Set gates pass.
- [ ] Candidate promotion uses the repository’s current approval and rollback flow; no automatic promotion is introduced.
- [ ] Docs record dataset version, mixture, config, limitations, results, and the fact that measured success is bounded to the tested distributions.

## 13. Definition of done

This task is complete when a reproducible, reviewed English capability corpus and mixed training recipe exist; a fresh candidate can be trained without altering the live champion; the English suite and existing project gates produce auditable, hash-bound results; and at least one candidate meets every defined gate before any promotion is proposed.

The outcome should be described as **improved measured English generation and context use on the tested distributions**. It should not be described as proof that Chit has human-like understanding or has ceased to be a next-byte predictive model.
