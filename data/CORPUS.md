# Chit corpus and review prompts

The active assistant preset reads `train.txt` and `eval.txt` from this directory. `train.txt` contains
the retained Chit/Atmini seed material plus request/response examples. These cover communication,
multi-turn context, Markdown, practical problem solving, uncertainty, and English/Hindi/Sanskrit work.
`eval.txt` is held out and contains reference responses for behavioral review.

`prompts.txt` retains continuation starters and adds a separate, open-ended challenge list. It is not
automatically included in training; use the challenge prompts to review Markdown comprehension,
clarification, support, and problem solving after training.
`reasoning.jsonl` remains source material for the existing knowledge-teaching tool/API.

New examples in this change were written directly for this project; no external model, AI service, or
third-party corpus was used to create them. Repository data is governed by the project `LICENSE`.
Record the source and license before adding third-party text, and keep its attribution with the corpus.

The configured data-generation limit is 200 MiB per generated dataset or split source. That is a
storage/input ceiling, not a useful target for this CPU training schedule: training only processes a
bounded number of random byte windows per run. Add reviewed material in stages and increase training
steps only when throughput and memory measurements on the target instance support it. Training now
stores each corpus byte in one byte of host memory instead of expanding the full dataset to 64-bit ids.
