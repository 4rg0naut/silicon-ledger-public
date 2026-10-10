# EXP-024 — Engine attribution: who actually computes what on M5 Max

**Status:** measurement stage DONE 2026-10-06 (user-run sudo capture, quiet window,
euid 0 @07:30Z). Arms A/B measured or GAP-declared below; MLX arm (C) awaits its own
window + API key; D/E remain GAP. Capture home (canonical):
`results/EXP-024-engine-attribution/raw/sudo/`; execution scratch (ignored, root-owned):
`/Volumes/data/OpenFox/dev_m5max_re/exp024-raw/sudo/`.

## Question

LADDER Rung 5 energy rows exist per machine, but nobody publishes **which engine did the work**
for a given kernel or token stream. This experiment produces a per-arm WHO-DID-WHAT matrix
(CPU / GPU-shader / GPU-NA / ANE per phase, per-signal confidence + calibration status) and the
matched A/B pJ/token delta for the same math landing on different engines.

## Deviations (declared, not silent)

1. **Model swap (twice declared).** The frozen protocol names MiniCPM5-2B (1.43 GB).
   No local copy exists on any volume and the internet is down. Pass 1a ran
   **Qwen3-Reranker-0.6B** calibration (local HF checkpoint, EXP-013/023 re-author
   route). The sudo capture then ran **granite97m** as the Core AI arm-B workload —
   the reranker `.aimodel` bake did not happen inside the window; rail attribution
   (lane-specificity mechanics) transfers, reranker-specific numbers do not. The
   device-gate rule (fp32 margin, not habit) carries over unchanged.
2. **ds4/NAX and BaseRT arms: GAP.** No local implementation (source notes only in
   `knowledge/ane/SOURCES.md`, 2607.19438 / ds4 #14). Fill after internet returns or defer
   to a follow-up EXP.
3. **MLX arm via the Studio's production oMLX server.** No offline `mlx` python install, and a
   *second* MLX server on the Studio is forbidden (a prior self-started server broke the
   production one — full reboot to clean). Pass 1 therefore drives the **already-running**
   server (`:8000`, API key from user) — attribution measured around real server load, in its
   **own window** (the quiet capture requires oMLX *off*; these two never overlap), with
   production-traffic contamination declared per row.
   Operational rules applied repo-wide: M5 metrics are measured **only on the M5 Studio**
   (mini is M4 — plumbing convenience only, never an M5 stand-in); the Studio oMLX server is
   never probed with new models and never doubled.

## Signals available (calibrated, from Thermometer v2 — see knowledge/ane/10)

| signal | engine | calibration status |
|---|---|---|
| thread CPU-time + `CPU Energy` (root) | CPU | [V] (energy needs sudo) |
| GPU Stats active/idle histogram + renderer % | GPU-shader | [V] matched (MSL A/B) |
| PMP0 `DCS Floor` F≥2 full-window duty | ANE-DCS-BW | [V] 0% on non-ANE arms, 82.9% ANE-direct |
| `ANE-LNK*‑AF-BW` VMAX/VOVD duty | ANE link lanes | [V] 82.9/51.6/0% |
| Energy Model `GPU Energy` (unprivileged) | GPU rail | [V] idle 259 mW → 11.5 W load (2026-10-06 addendum) |
| `UT_EXT_*` histograms | ~~GPU-NA~~ | trick — failed calibration (EXP-004 rule) |
| `AGX-DCS-BW` F7/F8 + `AGX Energy` floors | ~~GPU load~~ | trick — 90–96% duty at idle (display pins VMAX; see `results/EXP-024-engine-attribution/raw/sudo/pilot/FINDINGS.md`) |
| Metal counterSets | tensor pipes | dead — `timestamp` only, both machines |
| **GPU-NA positive per-kernel signal** | GPU tensor units | **CLOSED 2026-10-06: does not exist.** Root powermetrics still exposes 5 GPU keys only (freq / active+idle residency / SW state / Power); AMC Stats = 0 lines even euid 0; counterSets `timestamp`-only. Matched model-level A/B is the substitute — see armA-matrix.md |

Pilot result (non-quiet, 2026-10-06), **confirmed in the quiet sudo window the same
day**: **Core ML MiniLM `ALL` lane = GPU on M5 Max, never ANE** (ANE rail 0.0 mW both
lanes, GPU rail 1426.3 vs CPU-lane 163.1; M4 ran it on ANE at 2.06 mJ/emb, M5 GPU at
4.94). Rung-5 rows label the M5 placement `GPU` — the M4 "ANE path" name does not carry
across machines. Rows: `m5-minilm-*` in the ledger.

## Arms and their matrices (to fill from raw/)

| arm | workload | expected landing | raw | RESULT 2026-10-06 |
|---|---|---|---|---|
| A. MSL A/B matched matmul | `bench gemm --paths tensorops` (MSL 4.0) vs `--paths msl` (3.2 simdgroup), SAME extent 4096 | GPU-NA vs GPU-shader | `cal_tensorops_priv.jsonl`, stage4_load.log | **GAP — tensorops arm no-ops (R8 validation_failed at every full size, re-confirmed under root); delta would be workload-vs-idle. A/B deferred to a toolchain fix or valid small-tile probe.** |
| B. Core AI engine preference | granite97m `.aimodel` 3 lanes (substituted for the Qwen3 reranker bundle — reranker bake pending; deviation declared) | ANE vs GPU-shader | `raw/sudo/power_coreai_run.log` + `results/EXP-022-m5max-baseline/raw/energy-close-2026-10-06/` (single home since 2026-10-06 correction; the log's EXP-004 paths are the pre-correction capture) | **FILLED: neuralEngine lane ANE rail 261.1 mW (lane-specific, gates PASS 35/35), GPU co-rise 240.7 = hybrid partition; gpu 739.9; cpuOnly GPU 174.9/CPU 7192.7.** |
| C. MLX (oMLX server) | Qwen3.8 Flash-Next completions, fixed prompts | GPU (shader+NA mix) | post-window, enginemon-wrapped | PENDING — needs oMLX API key (not in any agent-readable file/env) + own window (window used oMLX-off); server relaunched ~07:35Z, healthy |
| D. ds4/NAX | — GAP (no local impl) | — | — | GAP stands |
| E. BaseRT | — GAP (no local impl) | — | — | GAP stands |

Matched A/B pJ/token = A-arms delta: mean rail mW over window / throughput, from powermetrics
(primary) cross-checked against the unprivileged `GPU Energy` channel and macmon.

## Reproduce

Calibration stage: `/Volumes/data/OpenFox/dev_m5max_re/exp024-raw/calibration/` (r3 round = canonical) +
`results/EXP-024-engine-attribution/raw/stage3-metal/FINDINGS.md`. Measurement stage: run capture, then this file's
merge note (IDs into `bench/build_measurements.py` ROWS, `--apply-new`, regen SUMMARY).

## h17-truth pass (2026-10-06, same day — additions, no body rewrites)

- B4 delivered — §33.3 probe ran on M5 (unfiltered enginemon, idle/ANE/GPU/CPU phases):
  12 PMP0 ANE byte/histogram channels live and load-selective; NEW `SOC-NI8 ANE UP` /
  `SOC-NI9 ANEXL U` ANE-selective (idle <=2/s, ANE ~1460/s, GPU/CPU 0/s); generation-drift
  absences documented (Cluster-Power-States|ANE0, SOC0_ANE_F1/F2, AMC); `dart-ane0`
  interrupt trick confirmed dead-on-M5 (GPU phase out-rates ANE phase). Full table + raws:
  `knowledge/ane/10` B4 section, `raw/b4-channels-2026-10-06/`. M4 re-diff pending mini reach.
- B5 delivered — 24/24 kANE_* names enumerable on h17c via
  `-[​_ANEPerformanceStats stringForPerfCounter:]` (index table captured); mask-forcing
  measured client-type zeroing (`perfStatsMask` 15 to 0 through load, load stays OK);
  paper's create-1-load-0 failure lives on the kernel C-path (`ANE_ProgramCreate` absent
  in every user-land dylib). `bench/kane_gate_probe.m`, raw alongside B4.
- C6 DELIVERED (2026-10-06 late, runs/c6-runs/na_ab_all_20261006T164010Z.log):
  `bench/na_tiles.py --tag all` on Studio — arm A tensorops_64x32 checksum PASS
  (max_abs_err 7.74e-03); arm B rebuilt as embedded SIMT fp16 shader kernel per spec
  (simdgroup_matrix load/store + data_ptr unavailable in GPUCompiler 32023 MPS runtime —
  honest path substitution, non-tensor character preserved and improved); full clean
  per-arm runs logged — arm A `runs/c6-runs/na_ab_tensorops_20261006T164908Z.log`
  (checksum PASS 7.74e-03, 268.8–277.0 us/predict, 0.946–0.975 GFLOPS ×3) and arm B
  `runs/c6-runs/na_ab_simdgroup_20261006T164820Z.log` (checksum PASS 7.74e-03,
  337.8–352.1 us/predict, 0.745–0.776 GFLOPS ×3), while oMLX held its pool;
  arm A runs 1.27× faster at this dispatch-bound single-tile size.
  `mpsgraph_ref` (third,
  non-spec arm) still deterministic e53 "no memory" while oMLX holds its wired pool —
  retry/backoff (2/4/6s) exhausts and re-raises honestly; supports the ANE-contention
  theory, quiet window expected to clear it. Reviewer runs corroborate (arm A PASS under
  oMLX; e53 confined to the MPSGraph-compiled program).
- C6 harness history, first pass — `bench/na_tiles.py` (matmul2d 64x32 K=64 valid
  tile vs MPSGraph matched, checksum-gated, alternations): both arms compile and convert
  (verified via --dry CPU mode 2026-10-06). Program-load fails machine-wide at
  createProgramInstance "no memory" while oMLX holds its wired pool (EXP-023 signature
  reproduced). Valid-tile path itself is silicon-proven (stage4: single 64x32 K=64 tile,
  all elements correct) — the valid-tile path works; what awaits is the RUN.
  Protocol (user standing rule 2026-10-06): agents do not run GPU work on the Studio;
  user switches oMLX off and runs the one command — see C7.
- C7 one-shot ready — `raw/na_ab_window.sh` (user sudo): idle/armA/armB/idle phases,
  sudo powermetrics gpu_power plus enginemon per phase, dW and dMJ-per-million-tiles summary.
  First window (raw/na-ab-20261006T165856Z, 19:02) INVALID: script bug — arm payload was
  appended to enginemon's argv instead of executed (0-byte arm streams, GPU pinned 338 MHz,
  no na_tiles logs). Fixed same day: payload now runs parallel to samplers, analyzer verified
  against the invalid capture (idle-drift noise floor ~0.7 mW across idle↔idle2). Second
  attempt (na-ab-20261006T174630Z) also died: kernel log shows the harness LEAKS ~1
  IOSurface/predict against a 16384 per-client cap ("possible leak?" at 12288) — my
  90k-iter batch blew the cap mid-load (Swift fatalError NDArray+Pool.swift:77). Not a
  sudo/session issue (uid/session-port logs clean). Third design (working): relauncher loop
  — <=15000 predicts per process, batches relaunched inside a 90s rail window, energy
  counted as window dW x WIN / completed-tiles (duty honest). Stumble between attempts:
  root-leftover /tmp/pmpid blocked the user-run version (na-ab-20261006T180034Z, pid-file
  relocated to $OUT).
  C7 DELIVERED (2026-10-06 18:06Z, raw/na-ab-20261006T180625Z/ + summary.txt):
  quiet window drift 0.1 mW; armA (matmul2d) 561,612 mJ/Mtile (+1497.6 mW @951 MHz,
  237 us/tile, 16 launches, checksum PASS x16); armB (SIMT shader) 647,457 mJ/Mtile
  (+1618.6 mW @976 MHz, 262 us/tile); DELTA -85,845 mJ/Mtile = -13.3% to the tensor-ops
  arm, signal = inter-arm Δ 121.0 mW = 1210x the 0.1 mW idle-drift floor. Ceiling: measured 1.11 GF = 0.0036% of HAL-32 fp16
  @951MHz — dispatch-bound launch+memory cost at single-tile size; NA-pipe share stays
  unproven (C6 Tungsten-envelope note stands). Ledger: m5-naab-tensorops-tile-energy,
  m5-naab-simdgroup-tile-energy, m5-naab-tile-energy-delta (+3, SUMMARY regen 960 records).
  F-39 filed for the IOSurface leak.
  Curation 2026-10-08 (review): 180625Z enginemon streams gzipped in place (4.3:1) +
  MANIFEST.sha256; superseded windows (165856Z, 174157Z, 174630Z, empty 180034Z) stay on
  disk but unversioned via .gitignore na-ab-*/; future re-runs ignored by the same rule.
- C8 done — LADDER plausibility audit appended (measured untouched): fp16-8192 at
  103% of HAL-32 ceiling = first ceiling-side evidence for the 32-vs-40 core layering.
- Sources plus raw pins: `knowledge/ane/SOURCES.md` H17 section;
  `raw/research-2026-10-06/` (paper chapter extracts, Zakharko report plus swifts, MANIFEST).

### C7 status at step close (2026-10-06, pre-window) — GAP declared, instrument verified

ΔmJ/million-tiles measurement awaits the user-run quiet window (standing rule: no agent
GPU work on the Studio; user switches oMLX off and runs the command). Instrument state:
`raw/na_ab_window.sh` analyzer validated against this morning's real capture
(powermetrics_gpu_tensorops.txt: 1650 samples parsed, mean 17,948 mW under load, clock
extraction live) and synthetic-phase end-to-end test (ΔmW → mJ/million-tiles arithmetic
verified at correct scale, idle-drift spread printed as noise floor). Arm B in the one-shot now uses the checksum-verified embedded SIMT arm (2026-10-06 late), so the
window no longer depends on the e53-prone MPSGraph path. When the window
runs, the script itself prints the number and the HAL/40-core ceiling check; rows then
merge via `bench/build_measurements.py --apply-new`. Until then the NA-vs-shader energy
delta stands as the declared GAP it has been all pass — no fabricated rails.
