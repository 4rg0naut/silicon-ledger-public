# EXP-022 findings so far — M5 Max (Mac17,14), macOS 27.0 (26A428)

Machine: Mac Studio, Apple M5 Max, 40-core GPU, 18 CPU (6P+12E), 128 GB,
fingerprint `bda452aabd60bf26`. All raw outputs in this directory, never deleted.

## 1. Headline finding: in-session measurement is contaminated on this box

On the M4, the agent ran on a **cloud** model, so the machine under test stayed
unloaded during measurements. On this M5 Max, the agent runs **locally** via
oMLX (`omlx-server`, Qwen3.8-27B-MLX-8bit, ~30 GB RSS). Every generated token is
live GPU work on the machine under test.

Evidence (same machine, 12 h apart):
- `bench all` @ 14:27 UTC, agent lightly active (one background launch + light IO):
  `gpu_copy 379.5 GB/s` — clean band.
- `tools/stability_run.sh` @ 17:00-17:05 UTC, agent actively generating between and
  during runs: `gpu_copy 72.0` then `91.3 GB/s` — primer never recovered (trap R9
  territory). Two DISCARDs, loop stopped and replaced by a scheduled capture.

Consequence: stability series, full-suite cross-check, and S4 placement evidence must
come from a window when the agent is unloaded. Implemented as `clean_capture.sh`
(cron 02:00 local, idle guard: two consecutive checks with load-1min < 4.0, 15 min
apart, 2 h max). The 30 GB omlx-server RSS remains a resident-memory confounder
(same class as the M4's external 87 GB server the stability protocol already
bands around); the GPU-compute contamination is what the quiet window removes.

## 2. ane-probe: private API surface is unchanged M4 (h16g) -> M5 Max (h17g)

`bench/ane-probe.m` rebuilt on this machine (note: `-framework ObjectiveC` does not
link here; Foundation supplies libobjc implicitly). Output: `ane-probe.txt`.

Device, queried live:

| selector | M4 (KB 07) | M5 Max (this run) |
| --- | --- | --- |
| `+numANECores` | 16 | **16** |
| `+numANEs` | 1 | 1 |
| `+aneArchitectureType` | `h16g` | **`h17g`** (new) |
| `+aneSubType` | `h16` | **`h17`** (new) |
| `+aneBoardType` | 256 | **544** (new) |
| `+productName` / `+isVirtualMachine` | macOS / NO | macOS / NO |

Classes: **39 `_ANE*` classes on both machines; same 15 of our 19 documented names
present, same 4 absent** (`_ANECompiler`, `_ANEMemoryModel`, `_ANEProgram`,
`_ANEModelCache` — all weak-prior). No stale documented name, no new class.
Method-level spot check: every key signature documented in
`knowledge/ane/07-private-api-verified.md` exists here verbatim, including
Apple's `initWithDesctiptor:` typo, `+sharedPrivateConnection`,
`doEvaluateDirectWithModel:`, the real-time task quintet, the mutable-weights
quintet, the hash-cache sextet, `+objectWithstatsSurRef:outputBuffer:`.

API-level verdict: **the M4 direct-path surface carries over to M5 Max verbatim.**
The numeric porting-recipe question is answered by S3/S4 numbers, not the API dump.
Follow-up: extend `07-private-api-verified.md` with an M5 Max section (T7).

## 3. Provisional suite assessment (in-session data — S4/S2 outliers suspect)

Diff vs `examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json`
(`bench-diff-vs-example.txt`), tolerances from `REPRODUCE.md`:

- S1 memory: all four GPU rows within 0.7% (gpu_read +0.4, gpu_write -0.1,
  gpu_copy -0.3, gpu_triad -0.7). `cpu_read -50%` (136.7 vs 273.5) and
  `cpu_write +141.9%` / `cpu_triad -8.8%` are the documented R9 band behaviour
  (external resident memory pressure); write/triad inside the declared band
  ranges, read is a newly observed instance of the same banding — the clean
  stability trio is the arbiter.
- S2 GEMM claim rows: fp32-mps +1.0% PASS; int8-mps +6.5% PASS (band 7000-7700
  GFLOPS held: 7220); **fp16-mps 46945 GFLOPS vs 60750 expected, -22.7% FAIL (±5%)**;
  **bf16-msl -8.1% FAIL (±8%, marginal)**. All other rows <7% except the
  max-power int8-msl rows (-27 to -30% — faster/slower spread across sizes =
  state/thermal, not silicon). The clean run decides.
- S3 ANE raw: **all five claim rows PASS** even in-session — dispatch_floor
  0.1102 (within ±15%; note: 0.006 ms below the reference band's 0.116 floor —
  trap 5's absolute floor is stated too strictly, needs a "~0.10" rewording),
  peak_int8_512x64_d128 13.51 TOPS (+3.1%), peak_256x64_d256 7.0 TOPS (+1.4%),
  sram cliff 42->94 MB reproduced (3.2x vs 3.4x), scale_4096 27.03 ms (+1.0%).
  Non-claim `scale_512 +32.2%` is sub-ms dispatch-regime variance.
- S4 Core AI: **all three rows out of band** — matmul 55.7 TOPS (vs 75-95),
  deep_fp16 ~0.50-0.54 TOPS (vs 1.8-2.1), deep_int8 0.90 TOPS (vs 0.6-0.8, fast
  side). All three models keep their equal-band across default/ane-preferred/
  gpu-preferred (R10 fallback signature intact). The uniform 1.5-4x slowdown
  across the whole suite points at system state/contamination rather than a
  per-model change — the clean run decides, with enginemon/xctrace as the
  placement instrument.

B-report validation notes (in `results/2026-09-26T14-27-41Z-...json`): all S4 rows
validated against torch refs (deep_int8 cosine 1.000000; deep_fp16 max_rel 1.045e-3
ok). Numbers are real, not corrupt.

## 4. IOReport channel map on M5 Max (enginemon)

`enginemon-list-m5.txt`: the unprivileged IOReport surface changed vs M4.
- **Absent on M5:** the whole `AMC Stats` group (the M4 byte-traffic signal),
  PMP, and the `ane 0` interrupt subgroup.
- **Present:** Energy Model (CPU Energy, GPU0, **ANE0**, GPU Energy),
  GPU Stats (14 channels incl. active-time histograms, PPM),
  Interrupt Statistics `dart-ane0 0` (First/Second Level Handler Count/Time),
  SoC Stats throttle/voltage events.
- Consequence: the M4 summary line "ANE activity = AMC bytes + Handler Count
  interrupts" is structurally zero on M5 (no AMC). `--all` per-channel rows are
  the evidence: watch `dart-ane0 0` handler counts and the `ANE0` energy delta
  (note: the summary filter only knows the M4 channel name `ANE`, so `ANE0`
  power never appears in the SUMMARY block — read the table). Idle control run
  included in the capture to establish baseline movement. Whether `ANE0` energy
  is live on M5 (vs M4's frozen `ANE`) is itself an open finding.

## 5. AOT region counts: silent GPU fallback confirmed at the artifact level (DONE, 17:57 UTC)

Both user prerequisites are now resolved (Xcode license accepted; Metal Toolchain
component installed via
`/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild -downloadComponent
MetalToolchain`, build 27A266a). The working compiler is `coreai-build` inside the
MobileAsset mount — Xcode's own `aimodelc` still refuses to run even with the
component installed. The M4-era MobileAsset path in the ledger scripts is
per-machine-suffixed (`.lM3wuu` here vs `.vbaqjL` on M4); resolve by glob.

`coreai-build compile --preferred-compute neural-engine` on all three bench Core AI
graphs, both target architectures (bundles saved under `aot-region-counts/`):

| graph | target | `*ANE_region*` | delegates dir |
| --- | --- | --- | --- |
| matmul | h17g | **0** | MPSGraph only |
| deep_fp16 | h17g | **0** | MPSGraph only |
| deep_int8 | h17g | **0** | MPSGraph only |
| deep_fp16 | h16g | **0** | MPSGraph only |
| deep_int8 | h16g | **0** | MPSGraph only |

Findings:
- `--preferred-compute neural-engine` is **silently ignored** for these graphs on
  macOS 27.0 — every bundle is a pure MPSGraph (Metal/GPU) executable. This is
  trap R10 (silent GPU fallback) confirmed at the *artifact* level, not just via
  the equal-band heuristic.
- Happens for the h16g (M4) target too: the compiler here emits no ANE placement
  for these graphs regardless of target architecture.
- Consequence: the S4 equal-band across default/ane-preferred/gpu-preferred is
  expected and carries no ANE information — **no ANE execution is even possible**
  through Core AI for these graphs on this box. S4 numbers are GPU-MPSGraph
  numbers; the clean run's S4 result measures GPU state, not ANE placement.
- Contrast: on M4, other graphs (Granite, reranker) did produce ANE regions
  (ledger export scripts counted them). Whether these three ever did on M4 is
  checkable against M4 AOT artifacts if they still exist there.

The cron script's AOT step now uses the glob-resolved `coreai-build` and covers
all three graphs x both architectures.

## 6. Plan

- Cron (installed): `0 2 * * * clean_capture.sh` — env snapshot + idle guard,
  probe, official stability trio, full `bench all`, diff vs reference,
  enginemon (idle control / ane / coreai, all `--all`), xctrace `Core AI`
  recording + ane-hw-intervals, AOT region counts (6 combos). ~30-45 min.
  All prerequisites verified working on 2026-09-26 evening.
- After the clean run: finalize `gate-memo.md` (GO/CONDITIONAL/NO-GO on the M4
  porting recipe), update KB 07 with the M5 Max section, then T5-T7.
- 14:27 in-session data stays in this directory as-is (contamination caveat
  recorded above); nothing deleted.
