# Chit (चित्): Atmini's brain

Chit is the cognitive core of Atmini. Its work is to understand the user's message and context,
communicate clearly, ask when important information is missing, reason through a problem, and help
the user choose a next step. Atmini can add tools and actions around Chit; Chit does not take
real-world actions without an explicit capability and permission path.

## Capability stages

1. **Language foundation** — UTF-8 byte model trained from scratch; CPU and CUDA training paths.
2. **Communication** — English, Hindi, and Sanskrit examples for dialogue, questions, instructions,
   explanations, and creative work.
3. **Structured input** — Markdown headings, lists, tables, quotes, checklists, and code fences are
   retained in requests and represented in training and held-out prompts.
4. **Problem solving** — identify the goal and constraints, find the next useful step, explain a
   simple chain of reasoning, ask clarifying questions, and state what is unknown.
5. **Continuity and learning** — sessions retain conversational context; memory holds experiences;
   API-taught knowledge remains separate and can be trained deliberately.
6. **Measured growth** — review held-out behavior by language and capability, then expand the corpus,
   context, model capacity, and training throughput in stages that fit the available CPU and RAM.
7. **Atmini integration** — later connect Chit's reasoning to approved tools and actions with a
   clear user-confirmation path.

## Current repository state

- The inference path operates as a Compound AI System: an explicit Intent Router selects the most faithful `Task: <name>` header (`chat`, `knowledge`, `behavior`, `grammar`, `reasoning`, `prose`, `continue`) and creates a typed Plan, a ContextBuilder budgets working memory in Chit's 256-byte context (including grounded `Task: reasoning`), a KV-cached Generator runs inference, a Verifier tests output invariants with conditional Best-of-3 candidate selection, and a Responder handles recovery.
- Exact symbolic arithmetic is offloaded to a safe AST-based calculator tool (`source: "tool"`), eliminating neural guesswork for math queries.
- Self-assessed confidence is calibrated through isotonic regression (`data/calibration.json`) with degenerate-curve rejection safeguards, providing trustworthy probability scores.
- Memory search features SQLite FTS5 lexical matching with information-theoretic query coverage and vocative attenuation, alongside optional vector semantic embeddings.
- All training files in `data/` use unified `Task: <name>` headers (`scripts/upgrade_corpus_tasks.py`) with duplicates capped at $\le 2$ and 407 grounded memory/web/fact examples across `knowledge.txt` and `reasoning.txt`. `data/eval.txt` and `data/eval_combined.txt` (574 multi-task blocks) are held out with zero exact-block overlap.
- The byte-level training corpus is stored compactly in host memory, indexes `"Task: "` record boundaries (70% record-start / 30% uniform windows), and applies `-100` answer-only cross-entropy loss masking prior to `Chit:` / `Reasoning:`.
- Candidate evaluation in the Studio UI validates behavioral safety against the Golden Gate and benchmarks bridge fidelity across 65 probes, automatically re-calibrating the Champion upon promotion.

Keep model weights, reviewed corpus, API-taught knowledge, runtime memory, session history, and the
Atmini action layer distinct so each can be inspected and improved deliberately.
