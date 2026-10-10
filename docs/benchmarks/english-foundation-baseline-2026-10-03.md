# English foundation baseline — 2026-10-03

**Status:** Baseline only; no behavior score available  
**Checkpoint:** `checkpoints/latest.pt`  
**Checkpoint SHA-256:** `46283b7cc30533572035e1b72c366b436eded6c868521162b0f777b610b8d663`  
**English suite:** `data/english_foundation/eval_suite.json`, draft 0.4  
**Suite SHA-256:** `2e8981d9e4af309294839fcec1ae9015b2cc715e7261be85ddff98552b3cf6be`

## Result

The checkpoint has a 64-byte model context. With the production `Task: chat` template, no memory, and the suite-provided history only, **1 of 120 prompts fit without truncation**. The evaluator therefore emitted no behavioral score and kept the gate closed. This is a context-capacity mismatch, not a 1/120 performance score.

The candidate preset `configs/chit_english_foundation.json` uses the existing 512-byte assistant context. Evaluate a candidate with the same suite after training. The suite content itself still requires independent review and approval by two reviewers before it can be used as a release gate.

## Reproduction

```powershell
python -m pranav.chit.tools.english_eval `
  --checkpoint checkpoints/latest.pt `
  --suite data/english_foundation/eval_suite.json `
  --max-new-tokens 96 `
  --output checkpoints/evaluations/english-foundation-baseline.json
```

The complete report is in the local evaluation artifact at `checkpoints/evaluations/english-foundation-baseline.json`.
