# English foundation curriculum

Version 1 is a project-authored starter curriculum for English structural fluency, assistant turn format, conversational intent, explicit and ambiguous reference, and English lexical use in context. The 2026-10-04 expansion adds varied synthetic examples.

## Sources

| File | Category | Task Header | Initial weight | Content |
| --- | --- | --- | ---: | --- |
| `structural.txt` | language patterns | `Task: grammar` | 0.6 | Grammar, sentence form, and meaning-preserving transformations (7,691 examples) |
| `conversation.txt` | conversational templates | `Task: chat` | 0.3 | Social intent, response protocol, and context/reference examples (4,189 examples) |
| `lexical_prose.txt` | language patterns | `Task: prose` | 0.6 | Natural prose and word-in-context passages (5,492 passages) |
| `project_facts.txt` | project facts | `Task: knowledge` | 0.1 | Reviewed Chit behavior and architecture facts (10 examples) |

Weights are normalized over the configured source list. The language sources share the aggregate 0.6 target (split equally here); the configured values are relative sampling weights, not percentages of bytes.

The expanded corpus sizes and item counts are recorded in `manifest.json`: `conversation.txt` contains 4,189 examples (`Task: chat`), `lexical_prose.txt` contains 5,492 passages (`Task: prose`), `structural.txt` contains 7,691 examples (`Task: grammar`), and `project_facts.txt` contains 10 examples (`Task: knowledge`), with zero exact duplicates (`max_dup = 1`). The original examples are preserved; expanded entries are synthetic combinations of varied themes and patterns from `data2.py` and standardized in-place by `scripts/upgrade_corpus_tasks.py`.

Assistant examples use their domain-specific `Task: <name>`, `User:`, and `Chit:` markers (`Task: grammar`, `Task: chat`, `Task: knowledge`), while prose passages start with `Task: prose`, matching the production prompt conventions and record-aligned window sampler. `manifest.json` records file hashes, UTF-8 sizes, and item counts. Baseline copies from immediately before the 2026-10-04 expansion are in `docs/benchmarks/dataset-baselines/` with the `*-pre-data2-expansion-2026-10-04.txt` names. Keep external material out until source, license, attribution, and privacy review are recorded.

## Use

The candidate preset `configs/chit_english_foundation.json` trains from these sources and evaluates on the held-out `data/eval.txt` (or `data/eval_combined.txt` in multi-stage presets). It does not overwrite `data/train.txt` or `data/eval.txt`, and it does not promote a checkpoint automatically.

This starter corpus is not the final capability dataset. `eval_suite.json` is a separate 120-case draft (30 per category), checked for exact prompt-text overlap with the configured training sources, and is not part of any training source. It still requires independent linguistic review before its scores can justify release. No Golden Set or challenge prompts are intentionally included in training sources.
