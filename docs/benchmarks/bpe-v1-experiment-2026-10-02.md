# BPE v1 Challenger Experiment

**Date:** 2026-10-02  
**Training corpus:** `data/train.txt` only  
**Held-out corpus:** `data/eval.txt`  
**Tokenizer:** ByteLevel BPE, 2,000 entries, asset SHA-256 `404663d12fd362649704d97252b0590b099292438e20fe3792ec1aea1461ce43`  
**Model:** fresh initialization, 2 layers, 2 heads, 64 embedding width, 64-token context, absolute positions  
**Training:** 300 steps on CPU; candidate saved separately at `checkpoints/bpe-v1/latest.pt`.

## Results

- The BPE tokenizer round-tripped all 9,183 bytes of held-out text without loss.
- Held-out text encoded to 2,485 BPE tokens versus 9,183 byte tokens, a 72.9% token-count reduction on this corpus.
- The challenger reached training-loop eval loss 4.8122 nats/token at step 300.
- A deterministic stream evaluation measured 1.955 bits/byte for this challenger and 7.627 bits/byte for the existing byte checkpoint. This is only an exploratory signal: the checkpoints have different training step counts (300 and 2,500), and BPE changes the effective context measured in bytes. It is not a controlled promotion comparison.

## Promotion status

The BPE checkpoint is a separate challenger. It was not promoted to `checkpoints/latest.pt`; the byte checkpoint remains the served champion. Before promotion, run repeated same-data/same-token-budget training trials, compare held-out bits per byte and generation quality, and record latency and memory costs. Do not mix RoPE/context changes into that comparison.

Recreate the tokenizer and challenger with:

```powershell
python -m pip install -e '.[bpe]'
New-Item -ItemType Directory -Force checkpoints/tokenizers | Out-Null
python -m pranav.chit.tools.train_tokenizer data/train.txt checkpoints/tokenizers/chit-bpe-v1.json --vocab-size 2000
python -m pranav.chit.tools.train --config configs/chit_bpe_experiment.json --output-dir checkpoints/bpe-v1 --no-step-checkpoints
```

The tokenizer asset and model checkpoint are local artifacts under ignored `checkpoints/`; the experimental configuration and reproducible code remain in the repository.
