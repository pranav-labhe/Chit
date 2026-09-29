# Chit pending improvements — check-in bundle

Target branch: `main_training_teaching`

This bundle implements only the three pending areas discussed:

1. Persistent turn-by-turn session context, separate from `MemoryStore`.
2. External material extraction/chunking feeding the existing Teach API.
3. Candidate training with an explicit promotion step, plus a regression test for Knowledge → Training → Candidate → Master promotion.

No Transformer, tokenizer, MemoryStore, vector DB, Bridge replacement, automatic memory retraining, or teaching architecture replacement is included.

## New files

- `pranav/chit/session.py`
- `pranav/chit/ingest.py`
- `pranav/chit/tools/ingest.py`
- `tests/test_session.py`
- `tests/test_ingest.py`
- `tests/test_candidate_pipeline.py`

## Existing files included as complete updated copies

These are ready to copy over the same paths after review:

- `pranav/chit/api.py`
- `pranav/chit/formats.py`
- `pranav/chit/bridge.py`
- `pranav/chit/jobs.py`
- `tests/conftest.py`
- `requirements.txt`

`MODIFICATIONS.md` explains the important deltas and why the candidate promotion path is needed for knowledge bookkeeping.

The new files were syntax-checked with `py_compile`. The full repository pytest suite could not be executed because the execution environment cannot clone the GitHub repository.
