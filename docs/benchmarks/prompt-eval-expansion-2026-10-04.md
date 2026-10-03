# Prompt and evaluation corpora refresh — 2026-10-04

## Files

| File | Purpose | Size after refresh |
| --- | --- | ---: |
| `data/prompts_1mb.txt` | Standalone prompt bank for manual or inference-time review; not a training source | 1,048,759 bytes (7,325 unique prompts) |
| `data/eval_1mb.txt` | Held-out next-token evaluation corpus paired with prompts in the prompt bank | 1,048,609 bytes (3,529 cases) |
| `data/eval_100kb.txt` | Smaller, whole-record subset of `eval_1mb.txt` | 102,232 bytes (353 cases) |
| `data/train_1mb.txt` | Existing training corpus; left unchanged in this refresh | 1,048,576 bytes |

The repository's normal presets still use `data/train.txt` and `data/eval.txt`. The new selectable
recipes are `configs/chit_1mb.json` and `configs/chit_1mb_eval_100kb.json`; both train from
`train_1mb.txt` and differ only in their held-out evaluation file. Neither recipe trains on an eval
file. The eval file is read during a training job for next-token loss measurement.

## Generation and review limits

`scripts/build_prompt_eval_1mb.py` uses fixed seed `20261004` and combines varied values across nine
task families: arithmetic, table-based comparison, time-bounded planning, supportive conversation,
data-science interpretation, grammar correction, project architecture facts, checklist extraction,
and clarification when information is missing. It writes one prompt per blank-delimited prompt block
and `Task: chat` reference-response records to the eval corpus. Every eval prompt also occurs in the
prompt bank. The 100 KiB alternative contains whole records from the 1 MiB eval file; the small file
is slightly below the byte target so no record is cut or filler bytes are added.

The generated corpora contain distinct prompt and response blocks and the generator excludes exact
block matches with `train_1mb.txt`. Template families and familiar vocabulary still recur by design,
so uniqueness does not mean every item is independent or human-authored. Arithmetic and table answers
are constructed from their values; open-ended supportive, planning, and data-science references are
illustrative targets and require human review before being treated as gold-standard behavior. The
evaluation file measures next-token prediction; it does not replace the frozen Golden Set or a
human-reviewed behavioral evaluation.

## Baseline archive

Pre-session snapshots are retained under `docs/benchmarks/dataset-baselines/`:

- `eval-pre-session.txt`
- `prompts-pre-session.txt`
- `train-pre-expansion.txt`
- `english-conversation-pre-expansion.txt`
- `english-lexical-prose-pre-expansion.txt`
- `english-structural-pre-expansion.txt`
- `english-project-facts-pre-expansion.txt`
- `root-train-pre-expansion.txt`, `root-eval-pre-expansion.txt`, and `root-prompts-pre-expansion.txt` (legacy root files)

The root-level files are not configured as training sources. The 1 MiB files in this report were
separate data files and are not represented by those earlier baseline snapshots.
