# Byte vs BPE Matched Experiment

**Run date:** 2026-10-03  
**Host:** Windows 10, Intel Core i5-6300U, 2 cores / 4 logical processors  
**Software:** Python 3.13.0, PyTorch 2.14.0+cpu, NumPy 2.5.3, tokenizers 0.23.2  
**Data:** `data/train.txt` for tokenizer training and model training; `data/eval.txt` held out  
**Seed / steps:** 42 / 300 for both checkpoints  
**Shared settings:** CPU, batch 8, AdamW learning rate 0.0005, weight decay 0.1, gradient clip 1.0, context 64 tokens, 2 layers, 2 heads, width 64, dropout 0, absolute positions, same eval cadence and source files.

The only intentional configuration change was tokenizer vocabulary: byte uses 256 entries; BPE uses the train-only 2,000-entry asset. Parameter counts therefore differ (120,576 byte; 232,192 BPE). Each model started from random initialization with the same seed. This is one matched run, not a multi-seed confidence estimate.

## Results

| Metric | Byte | BPE | Reading |
|---|---:|---:|---|
| Step-300 training-loop eval loss (nats/token) | 2.4723 | 4.8122 | Not directly comparable across tokenizers because token units differ. |
| Deterministic held-out NLL (nats/token) | 2.4416 | 5.0092 | Not directly comparable for the same reason. |
| Held-out bits per UTF-8 byte | 3.5220 | 1.9548 | BPE is 44.5% lower on this held-out stream in this single run. |
| Tokens for held-out text (9,183 bytes) | 9,183 | 2,485 | BPE uses 72.9% fewer tokens. |
| Greedy generation p50 / p95 / p99 (ms, 50 alternating runs) | 61.8 / 113.7 / 142.9 | 62.2 / 147.3 / 167.5 | Same prompt, same 32-token limit; candidates alternate order; warm-up before timing. |
| Mean generated tokens/s | 463.5 | 427.8 | BPE was 7.7% slower per model token in this run. |
| Mean output characters/s | 463.5 | 1,176.4 | Approximate output-volume proxy; generated strings are not quality-equivalent. |

The benchmark script computes held-out cross entropy over deterministic, non-overlapping target windows of each model's 64-token context, normalizes total negative log likelihood by the same UTF-8 byte count, then measures 50 alternating greedy generations after three warm-ups. The high-level training loss and held-out stream loss are reported separately because they use different sampling procedures. CPU timing variance is material; this single host/run is not sufficient to claim a serving-latency improvement.

## Decision

**Keep the byte checkpoint as champion for now; do not promote BPE yet.** The matched run shows substantially lower held-out bits per byte, but BPE does not improve per-token generation throughput in this run, and its larger vocabulary nearly doubles parameter count. It is still only one seed on a small corpus, and no behavioral golden-set score has been recorded. Promotion requires at least three matched seeds, a passing behavioral golden set, and target-hardware latency/memory checks. If BPE fails those gates, retain byte tokenization.

Checkpoints are local ignored artifacts at `checkpoints/validation-fairfight/{byte,bpe}/latest.pt`. Configs are `configs/chit_byte_experiment.json` and `configs/chit_bpe_experiment.json`.

Reproduce:

```powershell
New-Item -ItemType Directory -Force checkpoints/tokenizers | Out-Null
python -m pranav.chit.tools.train_tokenizer data/train.txt checkpoints/tokenizers/chit-bpe-v1.json --vocab-size 2000
python -m pranav.chit.tools.train --config configs/chit_byte_experiment.json --output-dir checkpoints/validation-fairfight/byte --no-step-checkpoints
python -m pranav.chit.tools.train --config configs/chit_bpe_experiment.json --output-dir checkpoints/validation-fairfight/bpe --no-step-checkpoints
python -m pranav.chit.tools.evaluate_tokenizer_pair --byte-checkpoint checkpoints/validation-fairfight/byte/latest.pt --bpe-checkpoint checkpoints/validation-fairfight/bpe/latest.pt --runs 50 --tokens 32
```
