# English foundation curriculum

Version 1 is a project-authored starter curriculum for English structural fluency, assistant turn format, conversational intent, explicit and ambiguous reference, and English lexical use in context. The 2026-10-04 expansion adds varied synthetic examples.

## Sources

| File | Category | Initial weight | Content |
| --- | --- | ---: | --- |
| `structural.txt` | language patterns | 0.6 | Grammar, sentence form, and meaning-preserving transformations |
| `conversation.txt` | conversational templates | 0.3 | Social intent, response protocol, and context/reference examples |
| `lexical_prose.txt` | language patterns | 0.6 | Natural prose and word-in-context examples |
| `project_facts.txt` | project facts | 0.1 | Reviewed Chit behavior and architecture facts |

Weights are normalized over the configured source list. The language sources share the aggregate 0.6 target (split equally here); the configured values are relative sampling weights, not percentages of bytes.

The expanded corpus sizes and item counts are recorded in `manifest.json`. `conversation.txt` contains 4,189 examples (1,048,766 bytes), `lexical_prose.txt` contains 5,492 passages (1,048,737 bytes), and `structural.txt` contains 7,691 examples (1,048,623 bytes). The original examples are preserved; expanded entries are synthetic combinations of varied themes and patterns from `data2.py`. These additions have not received independent linguistic review. The generator reads Python literal pools safely without importing `data2.py` (which depends on the unavailable base `data` module and has no output entry point).

Assistant examples use `Task: chat`, `User:`, and `Chit:` markers, matching the production prompt conventions. Prose-only entries are complete standalone passages. `manifest.json` records file hashes, UTF-8 sizes, and item counts. Baseline copies from immediately before this expansion are in `docs/benchmarks/dataset-baselines/` with the `*-pre-data2-expansion-2026-10-04.txt` names. Keep external material out until source, license, attribution, and privacy review are recorded.

## Use

The candidate preset `configs/chit_english_foundation.json` trains from these sources and evaluates on the existing held-out `data/eval.txt`. It does not overwrite `data/train.txt` or `data/eval.txt`, and it does not promote a checkpoint automatically.

This starter corpus is not the final capability dataset. `eval_suite.json` is a separate 120-case draft (30 per category), checked for exact prompt-text overlap with the configured training sources, and is not part of any training source. It still requires independent linguistic review before its scores can justify release. No Golden Set or challenge prompts are intentionally included in training sources.
