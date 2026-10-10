# Chit corpus and review prompts

The default assistant presets read `train.txt` and `eval.txt` from this directory. `train.txt` contains
the retained Chit/Atmini seed material plus request/response examples. These cover communication,
multi-turn context, Markdown, practical problem solving, uncertainty, and English/Hindi/Sanskrit work.
`eval.txt` is held out and contains reference responses for behavioral review.

`prompts_1mb.txt` is a standalone challenge bank for manual or inference-time review; it is not
automatically included in training. `train_1mb.txt` and the matched `eval_1mb.txt` can be selected
with the `chit_1mb` recipe. The `chit_1mb_eval_100kb` recipe uses the same training corpus with the
smaller `eval_100kb.txt` review corpus. Evaluation files are held out: training reads them to measure
next-token loss, but does not update weights from them. The 100 KiB file contains whole records drawn
from the 1 MiB evaluation set. The legacy `prompts.txt` remains a separate continuation-starter file.

The large prompt/evaluation sets are generated reproducibly by
`scripts/build_prompt_eval_1mb.py` (seed `20261004`) from distinct task families: arithmetic,
structured comparisons, practical planning, supportive conversation, data-science reasoning, grammar,
documented Chit architecture, checklist reading, and clarification under missing information. The
script keeps each prompt unique, matches evaluation prompts to reference-response cases, and checks
against exact training-block overlap. These are synthetic examples, not human-reviewed ground truth.
`reasoning.jsonl` remains source material for the existing knowledge-teaching tool/API.

The large prompt/evaluation examples are synthetic and generated locally; no external model, AI
service, or third-party corpus was used. They have not been human-reviewed as gold-standard answers.
Repository data is governed by the project `LICENSE`. Record the source and license before adding
third-party text, and keep its attribution with the corpus.

The configured data-generation limit is 200 MiB per generated dataset or split source. That is a
storage/input ceiling, not a useful target for this CPU training schedule: training only processes a
bounded number of random byte windows per run. Add reviewed material in stages and increase training
steps only when throughput and memory measurements on the target instance support it. Training now
stores each corpus byte in one byte of host memory instead of expanding the full dataset to 64-bit ids.
