# चित् behavior evaluation

`data/eval.txt` is held out by the assistant preset. It contains request/target pairs in the same
`Task: chat` format used by the assistant paths. Do not copy these pairs into `data/train.txt`.
The file also retains the original held-out prose as seed evaluation material.

## Review criteria

Review generated replies against the target and criteria below; byte-level loss is a training signal,
not a behavioral pass.

| Area | Pass criteria |
| --- | --- |
| Question answering and arithmetic | Answers the asked question correctly, includes the requested calculation when asked, and does not add unsupported facts. |
| Instructions and transformations | Follows requested count, format, tone, and operation (for example, polite rewrite or ordered steps). |
| Reasoning and missing information | The conclusion follows the supplied facts; when a necessary fact is absent, says what is missing instead of inventing it. |
| Communication and support | Understands whether the person asks for information, shares a difficulty, or needs a next step; acknowledges emotion without assuming, asks a useful question when needed, and offers practical help. |
| Markdown comprehension | Reads the content and intent of headings, checklists, tables, quotes, and code fences without treating quoted or fenced text as an instruction to itself. |
| Creative generation | Produces coherent new text that respects the requested topic, length, and form. |
| Hindi and Sanskrit | Preserves the source meaning and uses the requested target language; judge Sanskrit grammar with a qualified reviewer. |

For each held-out request, record **pass**, **partial**, or **fail**. A partial response is relevant but
misses a constraint or contains a minor error. A fail is incorrect, off-task, or invents an answer where
the reference explicitly leaves information unknown. Report results by area and language; do not combine
them into a single loss number.

## Running a review

1. Train a fresh checkpoint with `configs/chit_assistant_cpu.json`.
2. Send each held-out `User:` request to assistant-mode `/generate` (or `/chat` with a fresh session), at
   `temperature: 0` and with no memory so the prompt is reproducible.
3. Compare each reply to its following `Chit:` target using the criteria above. Do not require exact wording.
4. Save the checkpoint identifier, config, per-case ratings, and reviewer notes with the evaluation record.

`data/prompts.txt` contains the retained continuation starters plus an open-ended challenge set, including
Markdown-formatted requests and realistic situations where Chit should clarify, listen, or help plan a
next step. It is not automatically included in training. Review the challenge prompts separately and
record the same per-area ratings.

## English linguistic capability suite

`data/english_foundation/eval_suite.json` is the separate English capability suite. Its current
`draft-0.4` version has 120 author-authored cases (30 per category) covering grammar, conversation,
continuity, and lexical use. The suite has not yet completed independent linguistic review, so it is
not a release result until the automated rater approves the items and adjudicate candidate outputs. Keep all of
its prompts out of training and tokenizer corpora.

Generate a deterministic candidate response report with:

```bash
python -m pranav.chit.tools.english_eval \
  --checkpoint checkpoints/jobs/<job-id>/latest.pt \
  --suite data/english_foundation/eval_suite.json \
  --output checkpoints/jobs/<job-id>/english-responses.json
```

The report uses the production chat prompt template, no memory, and only history explicitly supplied
by the suite. It records full-prompt context fit and raw outputs. Human ratings are separate and must
bind to the exact `suite_sha256` and `checkpoint_sha256` in that report. A rating file uses this form:

```json
{
  "english_suite_sha256": "<suite hash from report>",
  "checkpoint_sha256": "<checkpoint hash from report>",
  "response_set_sha256": "<generated response hash from report>",
  "ratings": [
    {"id": "EN-GRA-001", "passed": true, "critical_failure": false,
     "reviewers": ["auto-reviewer-1", "auto-reviewer-2"]}
  ]
}
```

After the auto-rater assesses every case and disagreements are adjudicated, rerun with
`--ratings ratings.json`. The evaluator reports overall and category rates, separate explicit and
ambiguous continuity rates, critical failures, and whether the draft/release thresholds are met. To
open the gate, the suite itself must also be marked `reviewed` with `content_review.approved: true` and
the automated reviewer IDs. The gate stays closed for suites below 120 cases or prompts that do not fit the
checkpoint context. Passing this English gate does not replace the frozen Golden Set or current
candidate-promotion workflow. The initial checkpoint baseline is recorded in
[`benchmarks/english-foundation-baseline-2026-10-03.md`](benchmarks/english-foundation-baseline-2026-10-03.md).

The corpus/config checks check that held-out requests are not duplicated in training and that the seed
examples cover the intended languages and Markdown structures. They do not claim that an untrained or
existing checkpoint passes this behavioral review. Generated model-output scorecards require human
review before being treated as behavioral evidence.
