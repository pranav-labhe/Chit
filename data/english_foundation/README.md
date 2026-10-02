# English foundation curriculum

Version 1 is a project-authored starter curriculum for English structural fluency, assistant turn format, simple conversational intent, explicit and ambiguous reference, and English lexical use in context.

## Sources

| File | Category | Initial weight | Content |
| --- | --- | ---: | --- |
| `structural.txt` | language patterns | 0.6 | Grammar, sentence form, and meaning-preserving transformations |
| `conversation.txt` | conversational templates | 0.3 | Social intent, response protocol, and context/reference examples |
| `lexical_prose.txt` | language patterns | 0.6 | Natural prose and word-in-context examples |
| `project_facts.txt` | project facts | 0.1 | Reviewed Chit behavior and architecture facts |

Weights are normalized over the configured source list. The language sources share the aggregate 0.6 target (split equally here); the configured values are relative sampling weights, not percentages of bytes.

All 223 examples in this initial tranche are written for the project. The files use `Task: chat`, `User:`, and `Chit:` markers where they represent assistant interaction, matching the existing production prompt conventions. Prose-only entries are complete standalone passages. `manifest.json` records file hashes, UTF-8 sizes, and item counts. Keep later external material out until source, license, attribution, and privacy review are recorded.

## Use

The candidate preset `configs/chit_english_foundation.json` trains from these sources and evaluates on the existing held-out `data/eval.txt`. It does not overwrite `data/train.txt` or `data/eval.txt`, and it does not promote a checkpoint automatically.

This starter corpus is not the final capability dataset. `eval_suite.json` is a separate 120-case draft (30 per category), checked for exact prompt-text overlap with the configured training sources, and is not part of any training source. It still requires independent linguistic review before its scores can justify release. No Golden Set or challenge prompts are intentionally included in training sources.
