# EXP-003 — Core ML sentence encoder on the ANE (latency, energy, attribution)

**Question:** if we put a real embedding encoder on the Neural Engine, does it
go faster *and* use less energy — and can we prove the ANE did the work?

**Model:** `sentence-transformers/all-MiniLM-L6-v2` — 22.7M params, 384-dim.
**Conversion:** PyTorch → Core ML `mlprogram`, fixed shape `(1, 128)`, `FLOAT16`.

```bash
cd /Volumes/data/local_ai_stack
.venv-conv/bin/python bench/convert_encoder_coreml.py --seq 128
.venv-conv/bin/python bench/bench_encoder.py                    # latency A/B
xcrun xctrace record --template 'Core AI' --no-prompt --time-limit 90s \
  --output enc_ALL.trace --launch -- $PWD/.venv-conv/bin/python bench/bench_encoder.py --only ALL --iters 300
python3 bench/ane_report.py enc_ALL.trace "ALL"
sudo HF_HOME=$PWD/models/hf .venv-conv/bin/python bench/power_ab.py --seconds 15
```

**Run:** 2026-09-20 · macOS 27.0 · coremltools 9.0 · torch 2.7.0

## 1. Conversion fidelity
`cosine(torch, coreml) = 0.999983` — float16 rounding only.

**Blocker and fix (important):** coremltools 9.0 fails with
`TypeError: only 0-dimensional arrays can be converted to Python scalars`, reported as
`ERROR - converting 'int' op (located at: 'model/embeddings/44')`.
**Root cause (proven by A/B, see FAILURES.md F-01):** the trigger is **NumPy ≥ 2.4**,
not torch or transformers. Holding torch 2.7.0 / coremltools 9.0 / transformers 4.57.6
constant, numpy 2.5.3 fails and numpy < 2.4 **converts the unpatched model fine**.
NumPy now raises instead of warning when converting an ndim > 0 array to a scalar, and
coremltools' `int()` lowering materialises a 1-element array. Already tracked upstream:
[coremltools#2633](https://github.com/apple/coremltools/issues/2633),
[#2755](https://github.com/apple/coremltools/issues/2755).
**Treatments:** pin `numpy < 2.4` (verified working), or apply the trace-friendly
`BertEmbeddings.forward` replacement in `bench/convert_encoder_coreml.py::patch_embeddings`
(keeps all real weights; validated at cosine 0.999983).
Minimal reproduction for upstream: `bench/repro_int_op.py`.

## 2. Latency across placements (60 iters, identical inputs)

| compute_units | mean | p95 | throughput |
| --- | --- | --- | --- |
| `CPU_ONLY` | 1.68 ms | 1.72 ms | 597 emb/s |
| `CPU_AND_GPU` | 2.08 ms | 3.49 ms | 480 emb/s ← *slower than CPU* |
| **`ALL`** (CPU+GPU+**ANE**) | **0.73 ms** | 0.77 ms | **1363 emb/s** |
| **Speedup** | **2.28×** | | |

Embeddings agree across placements: cosine ≥ 0.99996.

## 3. ANE attribution — A/B on `ane-hw-intervals`

| Run (300 inferences) | ANE intervals | ANE busy | Labels |
| --- | --- | --- | --- |
| **ALL** | **261** | **503.79 ms** | *Neural Engine Prediction* |
| **CPU_ONLY** (control) | **0** | **0.00 ms** | — |

Per-inference: excluding one **361.41 ms** interval (the ANE program
load/compile on first use), 260 intervals total 142.38 ms → **≈0.55 ms of ANE
work per inference ≈ 75% of the 0.73 ms wall time**.

## 4. Energy — A/B on `powermetrics` (15 s per case, idle machine)

| Metric | **ALL** | **CPU_ONLY** | Ratio |
| --- | --- | --- | --- |
| Throughput | **1410 emb/s** | 611 emb/s | 2.31× |
| **Energy per embedding** | **2.06 mJ** | **11.45 mJ** | **5.6× less** |
| ANE power (mean) | 2463 mW | 6 mW *(idle)* | — |
| CPU power (mean) | 439 mW | **6983 mW** (peak 9483) | 16× lower |
| GPU power (mean) | **0.0 mW** | 2.4 mW | work went to the ANE |

**Three independent confirmations the ANE did the work:** 261 vs 0 hardware
intervals · GPU at 0.0 mW · 2.31× throughput.

**Headline:** the efficiency win (**5.6×**) is much larger than the speed win
(**2.3×**) — the ANE finishes so fast it spends less total energy while drawing
2.5 W. CPU-only pegs the CPU at ~7 W average / 9.5 W peak (heat/throttle risk).

**Corpus translation:** 10k chunks ≈ 7 s · 100k ≈ 73 s · 1M ≈ 12 min (ANE),
versus ≈17 s / 168 s / 28 min (CPU-only).

## 5. Dynamic shapes did *not* break ANE placement
The `RangeDim(1..128)` variant still hit **0.76 ms / 2.20× speedup**. So padding
to a fixed length is not mandatory. ⚠️ Benchmarked **only at length 128**; other
lengths untested, and its ANE intervals were not separately traced.

## Caveats
- float16 conversion ⇒ cosine 0.99998, not bit-exact.
- The `patch_embeddings` monkey-patch is a **maintenance liability**: any future
  HF model may need the same treatment.
- `ane-hw-intervals` is machine-wide; attribution is valid because the CPU-only
  control was clean (0 intervals).
- Power rails are whole-system; the run was on an idle machine.

## Artifacts
- `raw/enc_ALL.trace`, `raw/enc_CPU_ONLY.trace` — the A/B ANE traces
- `raw/coreai.trace` — first ANE trace (Apple `fm` turn)
- `raw/power_ALL.txt`, `raw/power_CPU_ONLY.txt` — raw `powermetrics` output
- Models: `models/minilm128.mlpackage`, `models/minilm128_dynamic.mlpackage`
- Scripts: `bench/convert_encoder_coreml.py`, `bench/bench_encoder.py`,
  `bench/power_ab.py`, `bench/ane_report.py`
---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| minilm-coreml-ane | all-MiniLM-L6-v2 (Core ML) | ANE (compute_units=ALL) | fp16 | 128 | throughput | 1363.0 | embeddings/s | 0.73 | per embedding (mean) | ours |
| minilm-coreml-conversion-cosine | sentence-transformers/all-MiniLM-L6-v2 | — | FLOAT16 | 128 | cosine similarity (torch vs coreml) | 0.999983 | cosine | — | — | ours |
| minilm-coreml-cpu-only-latency-mean | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | mean latency | 1.68 | ms | 1.68 | per embedding | ours |
| minilm-coreml-cpu-only-latency-p95 | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | p95 latency | 1.72 | ms | 1.72 | per embedding | ours |
| minilm-coreml-cpu-only-throughput | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | throughput | 597 | emb/s | — | — | ours |
| minilm-coreml-cpu-and-gpu-latency-mean | sentence-transformers/all-MiniLM-L6-v2 | GPU | FLOAT16 | 128 | mean latency | 2.08 | ms | 2.08 | per embedding | ours |
| minilm-coreml-cpu-and-gpu-latency-p95 | sentence-transformers/all-MiniLM-L6-v2 | GPU | FLOAT16 | 128 | p95 latency | 3.49 | ms | 3.49 | per embedding | ours |
| minilm-coreml-cpu-and-gpu-throughput | sentence-transformers/all-MiniLM-L6-v2 | GPU | FLOAT16 | 128 | throughput | 480 | emb/s | — | — | ours |
| minilm-coreml-all-latency-mean | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | mean latency | 0.73 | ms | 0.73 | per embedding | ours |
| minilm-coreml-all-latency-p95 | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | p95 latency | 0.77 | ms | 0.77 | per embedding | ours |
| minilm-coreml-all-throughput | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | throughput | 1363 | emb/s | — | — | ours |
| minilm-coreml-all-speedup-vs-cpu | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | speedup | 2.28 | x mean-latency ratio vs CPU_ONLY | — | — | ours |
| minilm-coreml-placement-cosine-agreement | sentence-transformers/all-MiniLM-L6-v2 | — | FLOAT16 | 128 | cosine agreement across placements (minimum) | 0.99996 | cosine (lower bound) | — | — | ours |
| minilm-coreml-all-ane-intervals | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | ANE hardware intervals | 261 | count | — | — | ours |
| minilm-coreml-all-ane-busy | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | ANE busy time | 503.79 | ms total ANE busy | 503.79 | total ANE busy across 300 inferences | ours |
| minilm-coreml-cpu-only-ane-intervals | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | ANE hardware intervals | 0 | count | — | — | ours |
| minilm-coreml-cpu-only-ane-busy | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | ANE busy time | 0.0 | ms total ANE busy | 0.0 | total ANE busy across 300 inferences | ours |
| minilm-coreml-all-ane-busy-excl-first | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | ANE busy time excluding first-load interval | 142.38 | ms total ANE busy | 142.38 | total across 260 inferences, excluding one first-use ANE program load/compile interval | ours |
| minilm-coreml-all-ane-first-load-interval | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | first-use ANE program load/compile interval | 361.41 | ms | 361.41 | one-off interval (ANE program load/compile on first use) | ours |
| minilm-coreml-all-ane-work-per-inference | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | ANE work per inference (derived) | 0.55 | ms | 0.55 | per inference | ours |
| minilm-coreml-all-ane-share-of-wall | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | ANE share of wall time (derived) | 75 | % of 0.73 ms wall time | — | — | ours |
| minilm-coreml-all-power-throughput | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | throughput | 1410 | emb/s | — | — | ours |
| minilm-coreml-cpu-only-power-throughput | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | throughput | 611 | emb/s | — | — | ours |
| minilm-coreml-power-throughput-ratio | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | throughput ratio | 2.31 | x ratio (ALL vs CPU_ONLY) | — | — | ours |
| minilm-coreml-all-energy-per-embedding | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | energy per embedding | 2.06 | mJ | — | — | ours |
| minilm-coreml-cpu-only-energy-per-embedding | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | energy per embedding | 11.45 | mJ | — | — | ours |
| minilm-coreml-energy-per-embedding-ratio | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | energy per embedding ratio | 5.6 | x less than CPU_ONLY | — | — | ours |
| minilm-coreml-all-ane-power-mean | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | ANE power (mean) | 2463 | mW | — | — | ours |
| minilm-coreml-cpu-only-ane-power-mean | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | ANE power (mean) | 6 | mW (idle) | — | — | ours |
| minilm-coreml-all-cpu-power-mean | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | CPU power (mean) | 439 | mW | — | — | ours |
| minilm-coreml-cpu-only-cpu-power-mean | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | CPU power (mean) | 6983 | mW | — | — | ours |
| minilm-coreml-cpu-only-cpu-power-peak | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | CPU power (peak) | 9483 | mW | — | — | ours |
| minilm-coreml-all-gpu-power-mean | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | GPU power (mean) | 0.0 | mW | — | — | ours |
| minilm-coreml-cpu-only-gpu-power-mean | sentence-transformers/all-MiniLM-L6-v2 | CPU | FLOAT16 | 128 | GPU power (mean) | 2.4 | mW | — | — | ours |
| minilm-coreml-cpu-power-ratio | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | CPU power ratio | 16 | x lower than CPU_ONLY | — | — | ours |
| minilm-coreml-dynamic-latency-mean | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | mean latency | 0.76 | ms | 0.76 | per embedding | ours |
| minilm-coreml-dynamic-speedup-vs-cpu | sentence-transformers/all-MiniLM-L6-v2 | ANE | FLOAT16 | 128 | speedup | 2.2 | x mean-latency ratio vs CPU_ONLY | — | — | ours |
