# Phase 0 Inference Baseline (Local CPU)

**Collected:** 2026-10-02  
**Host:** Windows 10, Intel Core i5-6300U (2 cores / 4 logical processors)  
**Runtime:** Python 3.13.0, PyTorch 2.14.0+cpu  
**Checkpoint:** `checkpoints/latest.pt` (byte tokenizer; 2 layers, 2 heads, 64 embedding width, context 64)  
**Workload:** identical prompt, greedy decoding, 32 generated tokens, one warm-up, 100 measured requests.

## Results

| Mode | Throughput | p50 latency | p95 latency | p99 latency | Mean latency |
|---|---:|---:|---:|---:|---:|
| Sequential requests | 11.06 req/s | 85.6 ms | 129.9 ms | 162.4 ms | 90.4 ms |
| 100-request concurrent burst through bounded FIFO queue | 13.28 req/s | 3496.3 ms | 7203.9 ms | 7446.8 ms | 3545.5 ms |

The queue completed all 100 requests and rejected none. This is a single-host smoke baseline, not a production SLO or a statistically robust benchmark. It shows the serial worker modestly improved throughput for this burst while request latency grew with queue position. It does not establish that dynamic batching will improve this host's user experience.

## Limits and next measurements

- Only the local CPU path was available; CUDA latency and peak VRAM were not measured.
- The benchmark tool currently reports CUDA peak allocated memory only. CPU peak RSS, repeated-run variance, mixed prompt lengths, realistic request concurrency, queue rejection, and memory-retrieval latency still need measurement.
- The application memory fixture contains one record. Exact cosine search is O(N), but there is no representative corpus here to justify an approximate index or determine its recall/latency tradeoff.
- Repeat on supported deployment hardware with a representative model/checkpoint and workload before setting production SLOs or enabling micro-batching. Preserve raw benchmark JSON with each run.

Reproduce with:

```powershell
python -m pranav.chit.tools.benchmark_inference --checkpoint checkpoints/latest.pt --requests 100 --tokens 32
```
