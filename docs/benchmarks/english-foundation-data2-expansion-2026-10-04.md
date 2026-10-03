# English foundation data2 expansion — 2026-10-04

Expanded the three configured English foundation training sources to approximately 1 MiB each, preserving all prior records and adding varied, meaningful synthetic examples based on the literal pools in `C:\Python\data2.py`. The generator is `scripts/generate_english_foundation_from_data2.py`.

`data2.py` is an extension module (`from data import *`) with no corpus-writing entry point, and the base `data` module was unavailable. The generator therefore safely reads its Python literal pools through AST parsing rather than importing or executing it. This uses the available themes, language patterns, and conversational content as source material while preserving each file's format.

| File | Previous bytes / items | Expanded bytes / items | SHA-256 |
| --- | ---: | ---: | --- |
| `data/english_foundation/conversation.txt` | 10,920 / 80 | 1,048,766 / 4,189 | `1f142a6ad3530cb6ac50dcfd0aff59d667ab4dd93ac0a0cb4c19846c431f6051` |
| `data/english_foundation/lexical_prose.txt` | 5,710 / 50 | 1,048,737 / 5,492 | `04a0831f65ca5937af2078d4606f27e697ebdd04dbfc93c8207e1e6493bb2397` |
| `data/english_foundation/structural.txt` | 11,491 / 83 | 1,048,623 / 7,691 | `85453c4a3660e624cdb34cc01c869247bbe471b739593fe69259da80c2efeb80` |

Pre-expansion copies are archived in `docs/benchmarks/dataset-baselines/` as `conversation-pre-data2-expansion-2026-10-04.txt`, `lexical_prose-pre-data2-expansion-2026-10-04.txt`, and `structural-pre-data2-expansion-2026-10-04.txt`. `project_facts.txt` and the held-out evaluation suite were not changed. See `data/english_foundation/manifest.json` for current inventory and hashes. The generated additions are synthetic and need independent linguistic review before treating quality as validated.
