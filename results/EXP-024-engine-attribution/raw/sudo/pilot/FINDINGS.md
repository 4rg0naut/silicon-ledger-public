# Pilot (2026-10-06 09:3x, NON-QUIET — oMLX production active) — Core ML MiniLM on M5 Max

Plumbing + attribution pass via unprivileged enginemon v2.1 (`GPU Energy` rail discovered
2026-10-06; powermetrics capture still the primary). Load: `bench/mlpower-runner` on
`models/minilm128.mlmodelc`, fixed 4 texts, 20 s windows.

| lane | rate | GPU Energy mean | ANE0 | ANE-DCS-BW F≥2 duty |
|---|---|---|---|---|
| ALL | 1038.4 emb/s | 10 694 mW (shared with oMLX+display) | 0.00 mW | **0.0%** |
| CPU_ONLY | 745.2 emb/s | 8.6 mW | 0.00 mW | 0.0% |

## Findings

1. **Core ML MiniLM (`compute ALL`) does NOT land on the ANE on M5 Max** — 0% ANE duty,
   0 mW ANE rail, GPU rail carries the load. The M4 LADDER row [minilm-coreml-all-*] was
   ANE-executed; the same compiled model on M5 runs GPU. The Rung-5 row name "ANE path GPU
   rail" is therefore a *machine-dependent placement* — merge note: M5 rows must be
   labelled `placement=gpu` (attribution honesty, EXP-004 rule).
2. **GPU floor channels are another documented trick, not a metric**: `AGX-DCS-BW` F7+F8
   duty and `AGX Energy ≥8W` duty are 90–96% AT IDLE (display pipe streams 9.6 GB/s
   constantly, DISPEXT0-BWR, pinning VMAX floors) — no usable idle-vs-load, let alone
   shader-vs-NA, separation. Re-check across the r3 calibration set: idle 95.6% / cpu 90.3 /
   mps 99.8 / msl 100.0 / tensorops 99.9 / ane 89.8 — top end saturated, bottom above idle.
   `ANE-DCS-BW F≥2` remains the ONLY sharp engine-positive channel.
3. CPU Energy / GPU0 / ANE0 rails: still 0 unprivileged (unchanged).

Quiet-window capture (powermetrics) will supply the primary mW/mJ numbers; these pilot rows
are attribution-only and stay marked non-quiet.

Files: `minilm_all.jsonl`, `minilm_cpuonly.jsonl` (raw enginemon streams).
