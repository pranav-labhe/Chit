# Chit corpus and review prompts

The default assistant presets read `train.txt` and `eval.txt` (or the unified held-out `eval_combined.txt`) from this directory. `train.txt` (118 blocks) contains the retained Chit/Atmini seed material plus request/response examples tagged with explicit `Task: <name>` headers (`Task: chat`, `Task: prose`, `Task: grammar`, `Task: behavior`). `eval.txt` and `eval_combined.txt` are held out and contain reference responses for behavioral review with zero exact-block overlap against training files.

## Unified `Task:` Curriculum & In-Place Overhaul (`scripts/upgrade_corpus_tasks.py`)

Every training block across all source `.txt` and `.jsonl` files starts with one of the 7 canonical task headers (`chat`, `knowledge`, `behavior`, `grammar`, `reasoning`, `prose`, `continue`), while keeping each source file separate and preserving its exact sample count (exact duplicates capped at $\le 2$ per file via 1-for-1 deterministic synthetic replacement):

| File | Blocks | Task Header(s) | Max Dup | Grounded (`Known memory:` / `[Web]` / `Facts`) |
| --- | ---: | --- | ---: | ---: |
| `data/train.txt` | 118 | `chat` (86), `prose` (24), `grammar` (5), `behavior` (3) | 1 | — |
| `data/train_1mb.txt` | 1,813 | `prose` (1,617), `chat` (186), `grammar` (5), `behavior` (3), `knowledge` (2) | 1 | — |
| `data/conversation_reasoning/conversation.txt` | 3,073 | `Task: chat` (includes typo/noise greeting & identity prompt variants with clean replies) | 2 | — |
| `data/conversation_reasoning/reasoning.txt` & `data/reasoning.jsonl` | 1,196 | `Task: reasoning` (`Input:` / `Reasoning:` / `Answer:`) | 2 | 236 |
| `data/knowledge_behavior/knowledge.txt` | 1,245 | `Task: knowledge` | 2 | 171 |
| `data/knowledge_behavior/behavior.txt` | 1,327 | `Task: behavior` | 2 | 20 |
| `data/english_foundation/structural.txt` | 7,691 | `Task: grammar` | 1 | — |
| `data/english_foundation/project_facts.txt` | 10 | `Task: knowledge` | 1 | — |
| `data/english_foundation/conversation.txt` | 4,189 | `Task: chat` | 1 | — |
| `data/english_foundation/lexical_prose.txt` | 5,492 | `Task: prose` | 1 | — |
| `data/eval_combined.txt` | 574 | Held-out multi-task eval (`chat`: 240, `knowledge`: 129, `reasoning`: 91, `behavior`: 73, `grammar`: 35, `prose`: 6) | 1 | Grounded & ungrounded |

`prompts_1mb.txt` is a standalone challenge bank for manual or inference-time review; it is not
automatically included in training. `train_1mb.txt` and the matched `eval_1mb.txt` can be selected
with the `chit_1mb` recipe. The `chit_1mb_eval_100kb` recipe uses the same training corpus with the
smaller `eval_100kb.txt` review corpus. The stage presets `chit_conversation_reasoning_6l_256` and
`chit_knowledge_behavior_6l_256` evaluate against `data/eval_combined.txt`. Evaluation files are held out:
training reads them to measure next-token loss, but does not update weights from them.

The large prompt/evaluation sets are generated reproducibly by
`scripts/build_prompt_eval_1mb.py` (seed `20261004`) and standardized in-place by
`scripts/upgrade_corpus_tasks.py` (seed `20261018`) across distinct task families: arithmetic,
structured comparisons, practical planning, supportive conversation, data-science reasoning, grammar,
documented Chit architecture, checklist reading, and clarification under missing information.
`reasoning.jsonl` remains synchronized with `data/conversation_reasoning/reasoning.txt` for the knowledge-teaching tool/API.

The large prompt/evaluation examples are synthetic and generated locally; no external model, AI
service, or third-party corpus was used. Repository data is governed by the project `LICENSE`. Record the source and license before adding
third-party text, and keep its attribution with the corpus.

The configured data-generation limit is 200 MiB per generated dataset or split source. Training stores each corpus byte in one byte of host memory, indexes `"Task: "` record boundaries (`record_starts`) so 70% of training windows align to a complete record start (and 30% sample uniform byte offsets), and masks prompt bytes before `Chit:` or `Reasoning:` with `-100` so cross-entropy loss focuses on answer and reasoning tokens.
