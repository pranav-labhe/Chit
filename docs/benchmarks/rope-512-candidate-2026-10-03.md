# RoPE 512-Token Candidate Evaluation

**Decision:** Do not promote. The candidate clears the prompt-capacity prerequisite, but the generated Golden Set answers exhibit obvious repetitive collapse and it has no independent human ratings.

## Reproduction details

| Item | Value |
|---|---|
| Checkpoint | `checkpoints/candidates/rope-512/latest.pt` (local ignored artifact) |
| SHA-256 | `d0cc2d7025553f004c7a7a4a47e445401f4ae6ae2dac98132dc235825eca1c13` |
| Training | 500 steps, seed 314159, CPU, byte tokenizer, base training corpus |
| Model | 2 layers, 2 heads, 64 embedding dimensions, RoPE, context curriculum 128/256/512 |
| Evaluation runtime | Windows x64, Python 3.13, PyTorch 2.14 CPU |
| Held-out data | `data/eval.txt`, SHA-256 `10345e29d7fe2dcfd0e1e41f10584cbdc66d281f3218b713c6dae5bd53479ede` |
| Golden Set | v1, 50 cases, SHA-256 `74fd7cfa24706cab99e599428ce5379e710927e3981c1a86ec292e9a40316993` |

## Results

| Metric | Result |
|---|---:|
| Golden prompts that fit without truncation | 50 / 50 |
| Held-out NLL | 2.2721 nats/token |
| Perplexity | 9.6996 |
| Bits per UTF-8 byte | 3.2776 |
| Next-token accuracy | 35.09% |
| Independent Golden Set reviews | 0 |
| Promotion gate | **Closed** |

Although all prompts fit, sampled responses repeatedly produce variants of `The the the...` rather than answers. This is direct qualitative evidence that context capacity and held-out language-model metrics alone are insufficient behavioral acceptance criteria. The candidate must not replace the byte champion.

## Next experiment

Diagnose the generation collapse before spending compute on longer training: inspect prompt/completion formatting and stopping behavior, measure repetition across deterministic seeds/temperatures, and add a small smoke evaluation that flags high repeated-token rates. Then train a revised candidate while preserving this checkpoint and report for comparison. Any eventual promotion still requires a complete scorable Golden Set, the required independent reviews, and held-out regression checks.

The full machine-readable response artifact is `checkpoints/evaluations/rope-512-responses.json` and is intentionally not tracked with this report.
