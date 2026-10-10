# Arm A — matched matmul matrix (structure + signals ready, numbers pending)

Same math (4096³ fp matmul), different engine paths, per-signal WHO-DID-WHAT.
Unprivileged columns from the r3 calibration rounds are marked [u]; quiet-window
powermetrics columns arrive with the capture (see `results/EXP-024-engine-attribution/raw/sudo/merge-plan.md`).
Units/parsing note: raw channel deltas are nJ or 24M-tick counts per interval — always
route through enginemon `sum` (mW) or the analyze scripts before quoting numbers.

| signal | engine | calibration | idle | `--paths msl` (3.2 simdgroup) | `--paths tensorops` (MSL 4.0 matmul2d) | confidence |
|---|---|---|---|---|---|---|
| GPU Stats active duty | GPU (any pipe) | [V] matched r3 | 0% baseline | high (long kernels) | **void** — arm no-ops (see below) | [u] |
| `GPU Energy` Δ vs idle | GPU rail | [V] unpriv 2026-10-06; [V] root 2026-10-06 (cal_*_priv.jsonl) | baseline | real load; live channel at root | **void** — 9169 mW reading is a no-op dispatch arm (R8), not tensor-unit work | [u] |
| powermetrics gpu_power mW | GPU rail (primary) | model loads DONE 2026-10-06 (MiniLM ALL GPU 1426.3 mW / CPU_ONLY 163.1; Granite lanes 739.9/261.1/174.9 — see EXP-022 Energy close) | PENDING (step-6 idle tail oMLX-contaminated) | PENDING (needs own clean window) | **GAP — arm no-ops** (R8); needs fixed GPUCompiler toolchain or smaller valid matmul2d probe | — |
| `ANE-DCS-BW F≥2` duty | ANE | [V] | 0% | 0% | 0% (no-op — no ANE engagement either way) | [u] both paths keep ANE parked |
| UT engagement centi-% | context only | trick | — | — | — | never quoted |
| thread CPU-time (harness) | CPU | [V] | floor | low | low | [u] |
| **GPU-NA per-unit counter** | tensor units | **CLOSED 2026-10-06: none exists at any privilege** (root powermetrics still exposes only 5 GPU keys — freq/residency/SW-state/Power; no performance-counters block; AMC Stats = 0 lines even euid-0) | — | n/a | n/a (R8 no-op blocks the empirical A/B that would have inferred it) | settled |

**Capture findings that changed the matrix (2026-10-06 sudo window, `results/EXP-024-engine-attribution/raw/sudo/`):**
(1) tensorops arms at every full size report `VALIDATION FAILED … silently no-ops on
macOS 27.0 beta GPUCompiler (32023)` (stage4_load.log) — the arm has been measuring an
empty dispatch (R8, re-confirmed under root in this capture); any "tensorops vs msl"
energy delta quoted before this note is
a workload-vs-idle delta, not shader-vs-tensor. (2) Root does NOT unlock anything for
enginemon: CPU Energy/GPU0/ANE0 stay 0.0, ANE handler_count/dcs_bytes 0, AMC lines 0
(cal_*_priv.jsonl, eng_list_priv.txt); only `GPU Energy` is live (9169 mW under the
no-op arm — channel scaling uncalibrated, never quote as load power). (3) Step-6
powermetrics ran past the load into the oMLX-restart surge (user relaunched oMLX
~07:35Z) — its tail is unusable; raw kept for completeness.

**Honest matched A/B that DOES hold on M5 today:** model-level rails — MiniLM ALL(GPU)
4.944 vs CPU_ONLY 11.400 mJ/embedding (2.31×), Granite neuralEngine 261.1 mW ANE vs
gpu-lane 739.9 mW GPU vs cpuOnly — all from one clean quiet window (EXP-022 Energy
close). The gemm-level shader-vs-tensor-arm delta was **GAP until the matmul2d
multi-tile no-op is fixed** (R8) — **DELIVERED 2026-10-06 via the R8-workaround path**:
single valid 64x32 K=64 tile, matched arms, in `bench/na_tiles.py` (+ `na_tiles.metal`),
quiet-window energy in `raw/na-ab-20261006T180625Z/` —
matmul2d 561,612 vs SIMT-shader 647,457 mJ/Mtile, delta −13.3%, dispatch-bound
(0.004% of HAL-32 ceiling), NA-pipe share still open. Ledger: `m5-naab-*`.
Multi-tile (4096³) arms remain void under R8 (F-37) — the GAP applies only there now.

Matching protocol (frozen from Rigel §3 + MSL A/B method in knowledge/ane/10):
identical shapes/dtype/iterations across arms; result-buffer checksum pass on BOTH arms
before any energy window counts; alternated runs ≥2 to cancel thermal drift; pJ/token
here = Δ(quiet gpu_power mW) × window / matmuls = **the matched A/B delta nobody publishes**.
