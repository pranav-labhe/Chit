# Current Byte Champion Evaluation

**Checkpoint:** `checkpoints/latest.pt`  
**SHA-256:** `46283b7cc30533572035e1b72c366b436eded6c868521162b0f777b610b8d663`  
**Model context:** 64 byte tokens  
**Evaluation set:** `data/eval.txt` (9,183 UTF-8 bytes) and Golden Set v1 (`data/golden_set.json`, 50 cases).

## Held-out language-model metrics

| Metric | Result |
|---|---:|
| Next-token NLL | 5.2869 nats/token |
| Perplexity | 197.7291 |
| Bits per UTF-8 byte | 7.6266 |
| Next-token accuracy | 31.37% |

The language-model metrics use deterministic, non-overlapping 64-token target windows. They do not substitute for task quality.

## Golden Set status

**No valid behavioral score is available.** With the production `Task/Memory/User/Chit` prompt template and no truncation, **0 of 50 prompts fit** in this checkpoint's 64-token context (full prompt lengths range from 81 to 193 byte tokens). The evaluator therefore generated no answers and marked all cases not scorable. This is a context-capacity incompatibility, not a 0/50 semantic score.

The behavior gate remains closed until a candidate can accept every case without truncation, after which two reviewers must score the outputs against the rubric. The machine-readable report is a local ignored artifact at `checkpoints/evaluations/byte-champion-2026-10-03.json`.

Reproduce with:

```powershell
python -m pranav.chit.tools.eval_runner --checkpoint checkpoints/latest.pt --eval-file data/eval.txt --golden-set data/golden_set.json --output checkpoints/evaluations/byte-champion-2026-10-03.json
```
