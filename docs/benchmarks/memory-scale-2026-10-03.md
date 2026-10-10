# SQLite Memory Search Scale Baseline

**Run date:** 2026-10-03  
**Host:** Windows 10, Intel Core i5-6300U, 2 cores / 4 logical processors  
**Software:** Python 3.13.0, NumPy 2.5.3  
**Path measured:** `SQLiteMemoryStore.search`, including SQLite record reads, embedding rows, content-hash validation, Python candidate assembly, exact NumPy cosine ranking, and hybrid ordering. Percentiles use linear interpolation (`numpy.percentile`).

The synthetic fixture uses 384-dimensional normalized random float32 vectors and 15 measured searches per corpus after three warm-ups. A fixed unit query vector makes runs repeatable. Results measure search latency and storage scale; random vectors do not measure semantic recall quality.

## Results

| Records | p50 | p95 | p99 | Mean | DB bytes |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 78.9 ms | 99.6 ms | 106.2 ms | 82.2 ms | 2,400,256 |
| 5,000 | 174.3 ms | 313.0 ms | 335.3 ms | 192.1 ms | 11,853,824 |
| 10,000 | 346.9 ms | 619.1 ms | 621.1 ms | 394.4 ms | 23,666,688 |
| 50,000 | 1,817.7 ms | 2,293.8 ms | 2,352.9 ms | 1,907.3 ms | 118,308,864 |

## Latency trigger and decision

Adopt **100 ms p95 warmed search latency** as the initial retrieval budget. Begin ANN integration before expected corpus growth reaches 5,000 records: the repeat at 5,000 records measured 313 ms p95, and 10,000 records measured 619 ms p95. An earlier run measured 302 ms and 577 ms, respectively. The two 1k p95 measurements varied substantially (45 ms and 100 ms), so use production-hardware repeated runs before setting smaller-corpus guarantees. ANN evaluation is required before operating at 5k+ records. Keep SQLite canonical and make the ANN index rebuildable. Validate recall@k against exact search before routing production queries to an approximate index.

**ANN rollout gate:** candidate search must reach recall@5 of at least 0.95 versus exact top-5 and p95 latency below 100 ms at both 10k and 50k records on supported deployment hardware. Verify index rebuild after database restore, correct behavior after memory insert/delete, and exact-search fallback if the derived index is missing or stale. These are proposed acceptance thresholds; confirm them against the actual application SLO before production rollout.

This is a local synthetic benchmark, not an SLO guarantee for other hosts or embedding providers. Re-run with the production embedding model, realistic tags and content lengths, concurrent writes, and a representative deployment disk before finalizing the service budget.

Reproduce with:

```powershell
python -m pranav.chit.tools.benchmark_memory --sizes 1000 5000 10000 50000 --dimension 384 --repeats 15 --seed 42
```
