# LADDER — from silicon ceiling to task quality

Publishable-bar view of the ledger. Every number below is a `measurements.json` row
reference — `[row-id]`, resolved against the ledger, never hand-typed. Where no row
exists, the slot says **GAP** and points at the experiment that would fill it; numbers
that live only in experiment reports are cited by file, never re-typed here as if
measured. Machine keys: `Apple M4 (h16g)` = the original 16 GB base-M4 Mac,
`Apple M5 Max (h17g), 128 GB` = the Mac Studio under test (fingerprint `bda452aabd60bf26`;
note 2026-10-05: the OS CoreAI delegate on this machine reports its architecture code as
`h17c`, not `h17g` — AOT builds must target `h17c`, see EXP-023 retry correction; the key
label stays as published for row-reference stability).

**Thesis of this ladder** [INFERENCE — scope: two machines (base M4 16 GB, M5 Max 128 GB),
burst-mode microbenchmarks and the ANE recipes tested here; TOPS are ceiling numbers, not
task performance]: on Apple silicon the raw compute ceiling increasingly belongs to the
GPU (M5 Max fp16 GEMM [m5max-s2-gemm8192-fp16-mps] is ~4600× the M4 ANE burst bandwidth
datapoint [granite-embedding-97m-fp16-v3-fp16-pooling-ane-effective-ane-bandwidth] and
~5× the M5 ANE int8 burst ceiling [m5max-s3-peak-int8-d128]), while the ANE's durable,
reproducible advantage is **energy per operation and load time** — which is exactly the
axis the official stack does not put graphs on (rung 3). Speeding a model up on the ANE
does not move task-quality ranks; the port exists to change the power envelope.

## Rung 1 — raw ceiling (bandwidth, GEMM, ANE dispatch)

| Measurement | M4 | M5 Max |
| --- | --- | --- |
| GPU read / triad / copy / write, GB/s | GAP (suite never run on M4) | [m5max-s1-gpu-read] 561.6 · [m5max-s1-gpu-triad] 555.1 · [m5max-s1-gpu-copy] 380.5 · [m5max-s1-gpu-write] 196.0 |
| CPU read / write / triad, GB/s | GAP | [m5max-s1-cpu-read] 273.5 · [m5max-s1-cpu-write] 101.4 (low band; bimodal, trap R9) · [m5max-s1-cpu-triad] 203.7 |
| Native tensor-copy path, GB/s | GAP | [m5max-s1-tensor-copy] 42.6 — 13× below the buffer path; the gap IS the finding |
| GPU fp16 / fp32 / bf16 / int8 GEMM, GFLOPS | GAP | [m5max-s2-gemm8192-fp16-mps] 60750 · [m5max-s2-gemm8192-fp32-mps] 14619 · [m5max-s2-gemm8192-bf16-msl] 12161 · [m5max-s2-gemm8192-int8-mps] 7691 |
| ANE int8 / fp16 peak, TOPS | GAP | [m5max-s3-peak-int8-d128] 13.1 (W8A16) · [m5max-s3-peak-fp16-256x64-d256] 6.9 |
| ANE dispatch floor, ms/eval | GAP | [m5max-s3-dispatch-floor] 0.119 |
| ANE large-op latency, ms/eval (4096ch) | GAP | [m5max-s3-scale4096] 26.8 |
| ANE effective bandwidth, burst / slow state | [granite-embedding-97m-fp16-v3-fp16-pooling-ane-effective-ane-bandwidth] 31 · [granite-embedding-97m-fp16-v3-fp16-pooling-ane-effective-ane-bandwidth-2] 14.5 | GAP (rail in slow regime on M5; EXP-022 open thread) |
| ANE latency fast / slow state, ms | [granite-embedding-97m-fp16-v3-fp16-pooling-ane-latency-fast-state] 1.85 · [granite-embedding-97m-fp16-v3-fp16-pooling-ane-latency-slow-state] 4.75 | GAP |

The M5 numbers reproduce their published claims (`bench diff` within per-row tolerance;
see REPRODUCE section). The M4 raw ceiling has no row from this suite — **first gap to
close if the two-machine comparison is to become quantitative**.

## Rung 2 — stack overhead (same model, different placement)

| Measurement | M4 | M5 Max |
| --- | --- | --- |
| Granite-97M warm latency by placement, ms | [granite-cpuonly-warm-median] 8.28 · [granite-gpu-warm-median] 6.06 · [granite-neuralengine-warm-median] 4.33 | GAP (Granite itself; EXP-023 put the reranker on all three lanes instead) |
| Qwen3-Reranker-0.6B ms/pair by placement (converted graph, JIT) | [timing-direct-ane] 88 · [timing-direct-gpu] 87 | [t8-m5-reranker-ane-latency] 71 · [t8-m5-reranker-gpu-latency] 26 · [t8-m5-reranker-cpu-latency] 214 |
| `neuralEngine` actually on the ANE? | NO — [granite-neuralengine-warm-median] ships 0 regions: [coreai-build-ne-macos-ane-regions] 0, [coreai-build-ne-ios-ane-regions] 0 (AOT falsified as the cause) | NO at artifact level too: all three bench graphs AOT to 0 `*ANE_region*` ([m5max-s4-coreai-matmul].ane_regions = 0, [m5max-s4-coreai-deep-fp16], [m5max-s4-coreai-deep-int8]) — same failure mode, now proven from the bundle |
| Core ML MiniLM throughput, emb/s | ANE [minilm-coreml-all-throughput] 1363 · CPU [minilm-coreml-cpu-only-throughput] 597 · GPU [minilm-coreml-cpu-and-gpu-throughput] 480 | GAP |
| Core ML MiniLM latency mean, ms | ANE [minilm-coreml-all-latency-mean] 0.73 · CPU [minilm-coreml-cpu-only-latency-mean] 1.68 · GPU [minilm-coreml-cpu-and-gpu-latency-mean] 2.08 | GAP |

## Rung 3 — port fidelity (the recipe: fp16 everywhere, no fp32 ops/literals, RoPE as
graph inputs, 1×1 conv + BC1S, no scatter/RNN/control-flow)

| Measurement | M4 | M5 Max |
| --- | --- | --- |
| ANE-shaped control graph regions | [tiny-ane-shaped-control-graph-1-1-conv2d-bc1s-channel-layernorm-ane-an] 66 vs [tiny-ane-shaped-control-graph-1-1-conv2d-bc1s-channel-layernorm-gpu-an] 0 (GPU placement proves the counter only counts ANE) | GAP for the tiny probe; the S3 suite is the ANE-side equivalent and passes |
| fp32 published graph → ANE regions | [granite-embedding-97m-fp32-published-gpu-ane-regions] 0 | same story in Core AI: [m5max-s4-coreai-matmul] ane_regions 0 |
| fp16 re-export regions | [granite-embedding-97m-fp16-v0-as-is-ane-ane-regions] 13 → [granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-regions] 1 | Qwen3-Reranker re-author → 2 ANE regions ([t8-m5-reranker-ane-latency].ane_regions = 2) — the conversion path reaches the ANE on M5 even though the MPSGraph path ([m5max-s4-coreai-matmul]) does not |
| Segmentation overhead, ms | [granite-embedding-97m-fp16-v0-as-is-ane-converged-median-latency-4000] 13.19 (13 regions) → [granite-embedding-97m-fp16-v3-fp16-pooling-ane-converged-median-latenc] 4.6 (1 region) | GAP |
| int8 weight quant: ndcg | [granite97m-w8] 0.68546 = fp16 parity | GAP |
| int6 / int4 quant gates | [granite-embedding-97m-w6-fp16-ane-min-cosine] 0.9983865 FAIL · [granite-embedding-97m-w4-fp16-ane-clear-pair-flips] 16 FAIL | GAP |
| Recipe effect on a non-autoregressive decision model (Von) | [von-v0-ane-regions] 31 → [von-v1-ane-regions] 3; [von-v0-ane-latency] 74 ms → [von-v1-ane-latency] 24 ms; [von-v1-worst-dp] 0.0027 max prob. drift | GAP |
| Recipe holds on M5 Max? | — | **compile level: yes** — S3 private-API suite reproduces (peak [m5max-s3-peak-int8-d128] 13.1 TOPS within published tolerance, SRAM cliff reproduced, dispatch floor [m5max-s3-dispatch-floor] 0.119) and the `_ANE` API surface is unchanged 16-core on both chips (`exp022-raw/ane-probe.txt`; 16 = API-visible count — compiler per-die is 8/32 by HAL suffix, arXiv 2606.22283 Ch24, see `knowledge/ane/10` Q8); **Core AI dispatch level: split** — the MPSGraph route is dead (0 ANE regions, GPU fallback, [m5max-s4-coreai-matmul] et al., now reproduced in the quietest window, plus python-runtime AOT load failure), but the EXP-013 conversion route works end-to-end: re-authored Qwen3-Reranker compiles to 2 regions and runs 71 ms/pair on the ANE ([t8-m5-reranker-ane-latency]) |

## Rung 4 — task quality (what the user gets)

| Measurement | M4 | M5 Max |
| --- | --- | --- |
| JevBench Intelligence, ANE vs CPU-published | [laya-en-ane-s256] 41.5 vs [laya-en-cpu-published] 45.8 — the port costs points, speed does not buy them back | GAP (T8) |
| Von JevBench Intelligence | [von-ane-s256] 36.2 | GAP |
| SciFact ndcg@10, our pipeline | [granite97m-chunk-ane-reranked] 0.7586 vs [published-bge-base-ndcg10] 0.74345 and [bge-base-plus-reranker-ndcg10] 0.77204 | GAP |
| Reranker contribution, ndcg delta | [granite97m-chunk-ane-delta] 0.07937 | GAP |

## Rung 5 — energy (the durable axis)

| Measurement | M4 | M5 Max |
| --- | --- | --- |
| MiniLM per-embedding energy, mJ | ANE [minilm-coreml-all-energy-per-embedding] 2.06 vs CPU [minilm-coreml-cpu-only-energy-per-embedding] 11.45 — ratio [minilm-coreml-energy-per-embedding-ratio] 5.6 | GPU [m5-minilm-all-energy-per-embedding] 4.94 vs CPU [m5-minilm-cpu-only-energy-per-embedding] 11.40 — ratio [m5-minilm-energy-per-embedding-ratio] 2.31. **M5 places MiniLM on GPU, not ANE** ([m5-minilm-all-gpu-power-mean] 1426 mW, ANE rail 0.0) — the M4 "ANE" column does not transfer |
| ANE path GPU rail, mW | [minilm-coreml-all-gpu-power-mean] 0.0 (control: [minilm-coreml-cpu-only-gpu-power-mean] 2.4) | M5 all-lane GPU rail [m5-minilm-all-gpu-power-mean] 1426.3 vs CPU-lane [m5-minilm-cpu-only-gpu-power-mean] 163.1 — inverted vs M4 because the model runs on the GPU here; ANE rail stays 0.0 |
| Granite fp16-ANE vs fp16-on-GPU, mW | [granite-embedding-97m-fp16-v3-fp16-pooling-ane-gpu-power-4] 75 vs [granite-embedding-97m-fp16-v3-fp16-pooling-gpu-gpu-power] 4124 | ANE rail (neuralEngine preference) [m5-granite-ane-ane-rail] 261.1 — moves only on that lane (S4 settled, EXP-022 thread 2); GPU-lane GPU rail [m5-granite-gpu-gpu-power] 739.9; CPU-lane [m5-granite-cpu-gpu-power] 174.9 |
| Laya ANE graph, GPU rail specialised | [laya-en-ane-energy] 15.9 vs GPU-specialised [energy-gpu-power-gpu-specialised] 773.8 (ratio [energy-gpu-power-ratio] 48.7) | GAP |

## REPRODUCE

M5 Max rows: from the public [silicon-ledger-bench](https://github.com/4rg0naut/silicon-ledger-bench)
suite on Mac Studio M5 Max, 40-core GPU, 18 CPU, 128 GB, macOS 27.0 (26A428),
Xcode 27; fingerprint `bda452aabd60bf26`.

```
make build
make all                       # ~8 min, unloaded machine
.build/release/bench diff examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json results/<run>.json
```

Tolerances are per-row in the bench repo's REPRODUCE.md (GPU bandwidth ±5%, tensor-copy
±20%, GEMM ±5–8%, ANE peak ±5%, dispatch floor ±15%, Core AI 75–95 / 1.8–2.1 bands);
cross-machine diffs require identical fingerprints. The 19 M5 rows above were imported
verbatim (values at the declared rounding) by `bench/import_bench_reports.py` from the
committed reference run — the report itself carries min/median/mean/p95 and the
validation audit trail. M4 rows: see the cited `EXP-*` directories; each carries its
exact command, date, and raw artifacts.

## C8 plausibility re-audit against HAL-derived ceilings (2026-10-06, annotations only)

Ceilings from arXiv 2606.22283 (per-die suffix sequence base=4 g=8 s=16 c=32 d=64) and
Zakharko per-core rates (NA fp16 ≈1024 FLOPS/core/cycle, int8 ≈2×; SOURCES PAPER-ANE-RE+,
TZAKHARKO-NA). Machine is 40-core GPU per this doc's own header; HAL suffix h17c exposes
32 to the compiler. No measured value below is modified — annotations only; measured rows
stand.

| row | measured | ceiling | % of ceiling | audit |
| --- | --- | --- | --- | --- |
| [m5max-s2-gemm8192-fp16-mps] | 60,750 GFLOPS | 32×1024×1.8 GHz = 58.98 TF (HAL-32) · 40×1024×1.75 GHz = 71.7 TF (40-core, Zakharko estimate) | **103% of HAL-32**, 85% of 40-core | PLAUSIBLE, and informative: exceeding the HAL-32 ceiling at nominal clock means the suffix count (32) is NOT the physical matrix-core count (40) — the compiler-visible/core-visible layer distinction from Q8, now with a performance-side measurement. NA-routing inferred, not proven (await C7 delta). |
| [m5max-s2-gemm8192-int8-mps] | 7,691 GFLOPS | 2× above = 118 TF / 143 TF | 6.5% / 5.4% | SUSPECT-WITH-REASON: a NA-routed int8 GEMM should sit near its 2× ceiling; 6% says MPSGraph int8 here rides the shader/dequant path, not NAX int8 MMA. Do not read as silicon limit. |
| [m5max-s2-gemm8192-fp32-mps] | 14,619 GFLOPS | SIMD fp32 ~18 TF (Zakharko A19-scaled) | 81% | PLAUSIBLE (shader path, as designed — fp32 has no NA datapath). |
| [m5max-s2-gemm8192-bf16-msl] | 12,161 GFLOPS | no published per-core bf16 rate | — | UNBOUNDED: no ceiling claim available; plausible between fp32-SIMD and fp16-NA paths. |
| [m5max-s3-peak-int8-d128] | 13.1 TOPS | ANE per-core ≈1.2 TF → 32–40 cores = 38–48 TF fp16, int8 ≈2× | 34% / 17% (int8 vs fp16 ceiling; vs 2× int8 ceiling 17%/9%) | SUSPECT-WITH-REASON, reason known: single-op burst recipe (d128) is dispatch-bound (floor 0.119 ms/step measured same session), not compute-bound — recipe ceiling, not silicon ceiling (Rung-1 caveat already on file). |
| [m5max-s3-peak-fp16-256x64-d256] | 6.9 TF | 38–48 TF | 18% / 14% | SUSPECT-WITH-REASON, same mechanism as above; published tolerance ±5% is about REPRO, not plausibility. |
| [m5max-s3-dispatch-floor] | 0.119 ms | paper M1 dispatch floor ~0.9 W power side; time floor unlisted | — | consistent with published "dispatch floor dominates small ops" framing; keep. |

Net: no published row is now *implausible*; two int8-family rows are explicitly flagged
as path-shaping artifacts rather than ceilings. The HAL-32 exceedance (103%) is the
first ceiling-side evidence for the 32-vs-40 core-count layering — logged for Q8/FLEET.

## What this is NOT

- Not a task benchmark for the M5 Max — one small model has run on it (Qwen3-Reranker,
  EXP-023, [t8-m5-reranker-ane-latency] 71 ms/pair); no retrieval task has been scored on it.
- Not power data on the M5 Max — its IOReport rails batch into a slow regime; every M5
  energy slot above is a declared GAP, not a zero.
- Not a cross-machine ceiling comparison — the suite has never run on the M4 (Rung 1 GAPs).
- Not proof the official stack uses the ANE anywhere — it currently does not, on either
  machine ([coreai-build-ne-macos-ane-regions] = 0, [m5max-s4-coreai-matmul].ane_regions = 0).
- Not human-verified: every row is machine-checked; `human_review` appears nowhere
  (CROSS-REPO-CONTRACT.md).

## Redaction checklist (before publication)

1. `exp022-raw/` artifacts reference host `<host>.local` and local `/Volumes/…` paths —
   keep the fingerprint, strip hostnames and absolute paths (the bench repo already
   redacts `machine.host` in its example).
2. oMLX / local-agent contamination notes mention the assistant stack; fine to publish,
   but check no API keys or account names ride along (`cron.log`, `probe.txt`).
3. The M5 Max fingerprint is a hash over hardware identity — publishing it is intended;
   check nothing else in the raw dumps identifies the owner.
4. Verify `bench/audit_measurements.json` regenerates clean against the published ledger.
5. Every number cited in prose maps to a row id — re-run this document's last check:
   `python3 bench/results_table.py --summary` and confirm the counts on page.
