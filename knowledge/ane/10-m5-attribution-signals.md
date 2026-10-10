# 10 — M5 Max per-engine attribution signals (UT demystified, ANE floor-bins, matmul2d fixes)

Compiled 2026-10-05 from the r3 calibration matrix (in-repo:
`results/EXP-024-engine-attribution/raw/calibration-r3/`, gzipped + MANIFEST.sha256;
generation scratch on the dev box: `exp024-raw/calibration/`,
M5 Max Mac17,14, macOS 27.0.1 / 26A434, in-session windows), local ioreg/registry
inspection on this machine, and the primary sources listed in SOURCES.md. Companion:
`tools/enginemon/README.md` "M5 Max (v2.1)" calibration table. Confidence tags:
**[V]** = verified locally on this machine this week · **[C]** = credible external
source, consistent with local evidence · **[U]** = unresolved / partially decoded.

## Q1 — "UT" is PMGR utilization tracking, NOT the Neural Accelerator **[V]**

- `UT_EXT_THROTTLE_*` event names live under **`AppleT6050PMGR`** in the IORegistry and
  span the SoC: `MGPU03 MGPU12 AFR PWRS ACCP ACCM0 ACCM1 SOC_GM SOC_CI` (ioreg, 2026-10-05).
  A vocabulary spanning power rails, CPU accelerators and MGPU partitions is SoC-level
  utilization/throttle accounting, not a per-GPU-core tensor-unit counter.
- `GPU Stats → UT Engagement centi-% Histogram` (unit `centi-%`) and
  `GPU UT AggD Stats → AGX.{Min,Max,Sum,Count}_UT_Engagement_Perf_State_0..15` /
  `UT_Not_Engaged_Perf_State_*` = **generic GPU engagement, rolled up per perf state**.
- Empirical: r3 matrix — UT `Sum` peak-rate 295,979/s on the **non-tensor MSL shader** GEMM
  arm (2.6× idle) while the (buggy, zero-output) tensor arm sat *below* idle (33,629/s);
  fails the 10× separation rule → **documented trick, not a metric** (EXP-004).
- Consequence: H1 (general engagement) confirmed; H2 (NA-exclusive) rejected. The
  `gpu-na` TAG in enginemon is retained for stream compatibility but is not a verdict.
- The acronym's expansion is not publicly indexed (exact-phrase web search: zero hits)
  and the AGX binary is detached on macOS 27 (kext stubs, not in the shared cache) —
  recorded as **[U]**-minor; semantics are settled by data regardless.

## Q2 — Histogram decode; the details-blob API is gone **[V]**

- macOS 27 exports **no** `IOReportChannelGetChannelDetails`-style symbol (dlsym → NULL in
  both `libIOReport` and `IOKit`) — the earlier `32 00000000 00000000` /
  `13 00000000 e8030000` blobs cannot be re-dumped through the public path.
- Not needed: histogram channels arrive as **state elements with named buckets + residency**
  (`F1..F8` bandwidth-floor bins, `VMIN/VNOM/VMAX/VOVD/VOVD_TYP` voltage bins, 24Mticks),
  exactly what `powermetrics` renders. Bucket labels ride the sample.
- `0xe803` LE = 1000 — consistent with the `centi-%` fixed-point scale; first byte
  (0x32=50 vs 0x13=19) likely bucket-count/kind tag of the retired struct. **[U]**.
- Decode convention (mactop `pmp_names.h`, `binWeightedAverage`): bins read **at their
  label** ("12GB/s"→12, "2W"→2), residency-weighted, **lowest bin = idle floor** (skip).
  M5 Max ANE floor rests at **F1** (M6: F2 — mactop #99).

## Q3 — Privilege filtering on M5: three mechanisms, all evidenced

1. **AMC byte counters: kernel-blocked on M5+** (mactop `32d86fd`; M4 Pro/Max same on
   macOS 27 per PR #91 merge note). Local: 0 AMC channels in user delta; `dart-ane0`
   handler counts 0 under verified ANE-direct load → subscription-time delivery filter.
2. **Energy Model rails: gated, not killed** — "reads 0, advances over partial windows
   while an entitled sampler (Activity Monitor, powermetrics) runs" (mactop `53e5f90`).
   All-smi #415 fixture proves the rails exist on M5 Max (`ANE0 mJ`, `AFR0`, `GPU0`,
   `MCPU0/1_*` per-core, `*_SRAM`, DTL, `DRAM0`, PCIe). Our frozen zeros = gated.
3. **PMP0 is the unprivileged door**: bare `PMP` empty on M5; `PMP0` subscribes fine and
   carries the floor/BW fleet incl. `ANE-DCS-BW`, `ANE-LNK0/1-AF-BW` (names per
   mactop `pmp_names.h`, confirmed in our own `--list`).

**Calibrated ANE positive signal (this project, r3):** `PMP0 DCS Floor → ANE-DCS-BW`
F≥2 residency, full-window — 0% on idle/cpu/mps/tensorops/msl, **82.9%** under ANE-direct,
40.7% on coreai (matches its scheduling duty). Independent corroboration: `ANE-LNK*‑AF-BW`
VMAX/VOVD residency (82.9% ANE arm, 51.6% coreai, 0% elsewhere). enginemon v2.1 emits
both as `ane_floor` in `sum` records.

## Q4 — ANE energy is its own rail, gated; not folded into GPU **[C/V]**

All-smi #415 fixture: dedicated `ANE0` (+`AFR0`) mJ channels exist in the M5 Max Energy
Model. Unprivileged: frozen. Root/entitled: expected live (same gating mechanism as CPU,
which mactop measured live under Activity Monitor). To be settled empirically in the
sudo window (`results/EXP-024-engine-attribution/raw/sudo/sudo_capture.sh`): expect `powermetrics --samplers
gpu_power` + full energy rails under root to deliver `ANE0`/`AFR0` movement.
`H11ANEIn.IOPowerManagement.CurrentPowerState` remains the unprivileged binary ON/idle
fallback only (mactop `3ffd18e`; M5 ANE is exclave-based — binary, sticks high under
background ML, never a % — mactop `b0fdcabe`).

## Q5 — matmul2d multi-tile zeros: root causes and fixes (our bug, their repro) **[C]**

Tungsten "Metal 4 matmul2d on M5 Max" (same chip, same symptom) — two silent causes:
1. **cooperative tensors require the MTL4 pipeline path**: legacy
   `newComputePipelineStateWithFunction:` mis-dispatches; use `MTL4Compiler` +
   `MTL4ComputePipelineDescriptor` with `requiredThreadsPerThreadgroup` set (128). Apple's
   own `MPPTensorOpsMatMul2d.h` example uses the legacy path.
2. **extents are innermost-first**: row-major M×K ⇒ `dextents(K, M)`, strides `(1, K)`,
   `slice<inner,outer>`; NumPy order = silent multi-tile mis-write ((0,0)-tile correct).
Plus two more silent-zero traps: MTL4 needs an explicit **`MTLResidencySet`** before
commit, and **`setThreadgroupMemoryLength:`** for `[[threadgroup(N)]]` params.
Perf envelope (their M5 Max bench): matmul2d beats `simdgroup_matrix` only at **M≥~400**
(18.9 vs 11.8 TF @ M=1024); decode (M=1) stays on the shader path → a true-NA load arm
must use large-M tiles + a checksum gate.

## Q6 — num_gps vs cores vs the UT index **[V]**

UT AggD is indexed by **perf state only** (0–15); no per-unit sub-index. `num_gps=16`
= graphics processors; `num_mgpus=4` partitions show up as exactly two throttle
groups (`UT_EXT_THROTTLE_MGPU03` = partitions 0+3, `MGPU12` = 1+2). Engagement/throttle
rolls up per MGPU partition; per-core NA granularity does not exist at IOReport level —
it exists in MLX source ("NAX", 16×16 fragments, `steel/gemm/nax.h`) and marketing.

## Q7 — The machine calls itself `h17c` at Core AI level **[V]**

The CoreAI delegate on this M5 Max reports its architecture as **`h17c`** — surfaced by the
otherwise opaque `CoreAIDelegates.AIModelError.incompatibleCompiledAssetArchitecture(device:
"h17c", asset: ["h17g"])` when loading an `h17g` bundle (granite-runner, 2026-10-06).
Consequences, all verified same-day:

- AOT builds for this OS (`26A434`) must target `--architecture h17c`; the widely-copied
  `h17g` guess (M5 marketing key) is what produced the EXP-023 "AOT load regression" —
  error 0 was the mismatch surface, and the matching `h17c` bundle loads via
  `AIModel.load(..., specialization_options=…)` normally.
- Metal's kernel family name (`AGXG17X…` in assertion strings) and IOReport's `PMP0`
  confirm the same generation from two other layers; Core AI's arch string is the one
  that gates compilation.
- Unspecialized `.aimodel` loads are arch-indifferent — which is why the `.aimodel` JIT
  route never showed the problem (EXP-023 verdict stands, with the cause corrected).

## Q8 — HAL core-count mapping, extended to h17 (amendment 2026-10-06) **[C→V-partial]**

arXiv 2606.22283 Ch24 (num_nes profile table) decodes the compile-time core sequence:
**4 for the base name, 8 for the g suffix, 16 for s, 32 for c, 64 for the d Ultra-class
die**; Ch1.3 cross-checks 4/8/16 (M1 base / M1 Pro-Max / M5) against HAL offset 0x238.
Ch34.4 adds: the ANE **runtime** string is coarse (`h1N` base, `h1Ng` Pro/Max/Ultra, the
only two variants the runtime emits) — the finer `s/c/d` letters are **compiler-target**
identifiers, which is exactly why our CoreAI delegate's `h17c` gate behaves differently
from `_ANE` runtime strings (Q7). Applied to our fleet (arch strings measured locally,
mapping from paper):

| part | arch suffix | compiler-visible NE cores | Apple published | our evidence |
| --- | --- | --- | --- | --- |
| M1 base | h15 | 4 | 16 | paper Ch1.3/Ch24, power rail ~10 mW/compute set **[C]** |
| M4 mini (dev box) | h16 (base) | 4 | 16 | surface probe verbatim API match **[V-API]** |
| M4 Max | h16g | **8** | — | arch from bundle names; core count paper-derived **[C]** |
| M5 base | h17s | 16 | 16 | suffix rule only **[C]** |
| M5 Max (this machine) | h17c | **32** | 16 | arch `h17c` verified Q7 **[V]**; 32 paper-derived **[C]** |

Corrections that follow, effective repo-wide:
- "16 ANE cores" is never a hardware fact for M4/M5 Max; it is the API-visible count
  (`_ANEDeviceInfo numANECores` = 16 on both, EXP-022 [V]) which matches the H17**s**
  marketing part, and (on M1) the I/O-registry quantity the paper distinguishes from
  per-die truth.
- M5 Max compiler-visible matrix cores = 32 (h17c). This is the ceiling divisor used in
  the C8 LADDER re-audit; the NA ceiling uses the separate Zakharko per-core rate
  (see 16-neural-accelerators.md / SOURCES row TZAKHARKO-NA).
- Nothing here changes any measured value; it changes only what N we divide by.

### Q8 amendment — the arch string is part-keyed; the private selector does not carry the compiler class (2026-10-10) **[V]**

Two boxes, same OS build (26A434), four surfaces each (evidence:
`results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt`, record `API-138`):

| surface | M4 mini (Mac16,10, board 256) | M5 Max (Mac17,14, board 544) |
| --- | --- | --- |
| Core AI `AIModel.deviceArchitectureName` | **h16g** | **h17c** |
| `mpsgraphtool -specializeForDevice` `mps.aneArch` | **h16g** | **h17c** |
| Core AI AOT gate, accepted set | {h16g} | {h17c} |
| `_ANEDeviceInfo.aneArchitectureType` | h16g | h17g |
| `_ANEDeviceInfo.numANECores` | 16 | 16 |

- The **compiler target** is the Core AI arch string (`h16g` / `h17c`), corroborated by
  `mpsgraphtool` and **enforced** by the AOT gate — which accepts exactly one target per
  box, not a range.
- The private `_ANEDeviceInfo.aneArchitectureType` returns the **`g` form on both** boxes:
  it **coincides** with the compiler target on the M4, **diverges** on the M5 Max. The
  single-box note from earlier the same day ("runtime string is a separate identifier")
  holds only for h17 — the split is **part-keyed**, not a law.
- Both observed parts contradict Bryngelson ch34 Table 34.3's resolver-derived rows:
  M4 base → observed **h16g** (table `h16`); M5 Pro/Max → observed **h17c** (table
  `h17s`). `coreai-build` also rejects the bare base target name `h16` on 26A434.
- `numANECores` is 16 on both boxes; the guide's suffix→core decode is the compiler
  per-die field, explicitly not this count.

## §33.3 whole-engine channel catalog (arXiv 2606.22283, paper-documented) **[C]**

Paper-documented readable-without-entitlement catalog. Our empiricist names in the last
column; **paper-documented ≠ locally-verified** — status per our own `--list`/runs:

| channel (paper) | fmt | unit | reads out | ours / status |
| --- | --- | --- | --- | --- |
| AMC Stats \| Perf Counters \| ANE0 RD / WR | 1 | B | DRAM read/write bytes | M4 legacy path live [V]; **M5: 0 channels user** [V] (kernel-blocked, Q3.1) |
| AMC Stats \| ANE0 DCS RD / DCS WR | 1 | B | same via compression path | same as above [V/M4-only] |
| Energy Model \| — \| ANE0 | 1 | mJ | engine energy | frozen at user [V]; euid-0 still 0.0 [V] but powermetrics rail live sudo [V 261.1 mW] — gating is per-consumer not per-uid |
| PMP \| AF BW \| ANE0 RD+WR | 2 | events | aggregate RW bandwidth events | our AF-BW fleet (ANE-LNK*); VMAX duty calibrated [V] |
| SoC Stats \| Cluster Power States \| ANE0 | 2 | 24Mticks | clock-state residency | **untested here → B4 probe** |
| SoC Stats \| Events \| SOC0_ANE_F1 / F2 | 2 | 24Mticks | clock-domain frequency-point residency | our F-bins family; ANE floor at F1 [V] — the SOC0_* names untested → B4 |
| SoC Stats \| Events \| ANE0_ADCLK_TRIG / DITHR_TRIG | 2 | 24Mticks | adaptive-clock + dither trigger ticks | untested → B4 |
| Interrupt Statistics \| ane0 0 | 1 | counts+MATU | 1st/2nd-level handler counts | M4: our `ane 0` second-level count live [V]; M5 → B4 |
| PMP0 \| DCS BW \| ANE L0/L1 | hist | B dist | per-channel read/write distributions | our PMP0 floor/BW fleet, subscribed fine [V] |
| SoC Stats \| Events \| ANE_THROTTLE_{SW,HW,PPT,DITHER,EXT}_TRIG | 1 | counts | per-cause throttle counts | untested → B4 |

Paper also documents per-dispatch signpost op-lifecycle stream (not IOReport) — GAP for us:
signpost consumer not built. Per-task kANE_* counters (24 names) are **not** on this
unentitled list; they need the stats-descriptor gate (B5 recon target).

## B4 §33.3 delivery probe — run 2026-10-06 on M5 Max (this machine), unprivileged **[V]**

Method: `enginemon --unfiltered --interval 500 --json`, four windows — quiet idle (8 s),
known-ANE load (granite97m `--compute neuralEngine`, 42×500 ms windows), known-GPU load
(`--compute gpu`, gate PASS 2.12 ms median, 0/35 failures), CPU-only. Raw (ANE-relevant
stream): `results/EXP-024-engine-attribution/raw/b4-channels-2026-10-06/` (full 7 MB
captures in `exp024-raw/b4-channels-2026-10-06/` with MANIFEST; M4 re-diff deferred —
mini unreachable tonight, M4 channel facts cited from 2026-09-23 [V] record instead).

| §33.3 item (paper) | M5 status (this run) | calibration |
| --- | --- | --- |
| PMP0 AF BW / DCS BW `ANE L0/L1 RD/WR/RD+WR` (12 ch) | **live** — delivered only under ANE load (0 deltas idle/gpu/cpu) | load-only ✓ strong |
| PMP0 `DCS Floor|ANE-DCS-BW`, `SOC Floor|ANE-LNK0/1-AF-BW` | live (already-calibrated floor family, Q3) | unchanged |
| **NEW (not in paper): PMP0 `SOC-NI Util BW|SOC-NI8 ANE UP` / `SOC-NI9 ANEXL U`** | **live, ANE-selective: idle ≤2/s · ANE ~1460/s · GPU 0/s · CPU 0/s** | positive candidate ≥700× idle separation; GPU/CPU arms n=3 s — re-run with matched iters before promotion to metric |
| PMP0 `Fast-Die CE|ANE0` | enumerated, **no delivery** in any window | documented present, unreadable at user level |
| SoC Stats `Cluster Power States|ANE0` | **absent on M5** (only DISP/MACC/PACC listed) | paper catalog was M1-era; generation drift |
| SoC Stats `Events|SOC0_ANE_F1/F2` | **absent on M5** — F-bins live on `PMP0 DCS/SOC Floor` here | our Q2 decode is the right adapter |
| SoC Stats `Events|ANE0_ADCLK_TRIG/DITHR_TRIG` | present as **`ANE_THROTTLE_{ADCLK,DITHER,SW,HW,PPT,EXT0-3}_TRIG`** (9 ch) | delivered, nonzero at idle (residency histograms, aggregate-tick scale) — context only, no separation |
| Interrupt Statistics `ane0 0` | present as **`dart-ane0 0`**; delivered, cumulative handler_count: idle 1220/s · **GPU 6000/s** · ANE 3930/s · CPU 2040/s | **not an ANE indicator on M5** — GPU arm rates higher than ANE arm; M4's `ane 0` trick does not port (EXP-004: documented trick, dead on h17c) |
| AMC Stats ANE0 RD/WR/DCS | absent on M5 (matches kernel-block [V] Q3.1; live on M4 [V 2026-09-23]) | M4-only instrument |
| Energy Model `ANE0` | enumerated, zero delivery in all four windows (user level) | gated, reconfirmed; sudo rail [V] |

Two artifacts the paper mentions that we still cannot consume: per-dispatch signpost
stream (consumer unbuilt) and per-task `kANE_*` (B5 below). Net B4 gain: 12 PMP0
byte/histogram channels confirmed live + `SOC-NI8/NI9` ANE-selective pair = new candidates
worth a matched-matrix calibration run.

## B5 kANE gate recon — h17c, 2026-10-06 **[V]** (bench/kane_gate_probe.m, raw: `results/EXP-024-engine-attribution/raw/b4-channels-2026-10-06/b5_kane_probe_output.txt`)

What 2606.22283 claims vs what reproduces on OUR silicon (M5 Max h17c, unprivileged):

- **24/24 counter names enumerable locally** — the paper's Table 33.1 is not the only door:
  `-[​_ANEPerformanceStats stringForPerfCounter:]` (index 0..47) returns the 24 kANE_* names
  at slots 0–23, exact index table captured (`kANE_AF_TO_L2_DATA` … `kANE_DPE_ENERGY`),
  slots 24–47 = `kANE_UKNOWN` padding (Apple's typo preserved). Slot 6 returns
  `"kANE_FP16_CYCLES:"` with a trailing colon — selector-format artifact, same counter.
- Full stats surface found: `_ANEPerformanceStats` (perfCounterData/decodeDescriptor:perTdPerfCounters:/
  decodeRawStatsData:/dumpPerformanceStatsRawData:), `_ANEInMemoryModel perfStatsMask /
  setPerfStatsMask:`, `_ANEModel perfStatsMask`, `_ANERequest perfStats/perfStatsArray`,
  `_ANEIOSurfaceOutputSets initWithstatsSurRef:outputBuffer:` — the entire per-task plumbing
  exists on h17c unprivileged; only the VALUES are gated.
- **Mask-forcing stage (control + forced):** compile a tiny 1-conv MIL in-memory model,
  control mask=0: compile OK, load OK. Forced mask=0xf: setter accepts (reads back 15),
  compile OK, **load OK — then `perfStatsMask` reads back 0**. No create→1/load→0 failure on
  this path: the ObjC runtime path zeroes the mask *before* the kernel sees it (paper's
  aned `ThirdPartyAppUsingANE` zeroing, observed from inside), so the kernel
  `initStatsBufferSection` bail never fires here. Paper's failure mode lives on the lower
  `ANE_ProgramCreate` C-entry path (symbols absent in every user-land dylib we could dlopen —
  kernel/aned-only). **Gate theory upgraded to: mechanism verified on h17c (client-type
  zeroing measured; name space live; values remain gated).**
- No entitlement claims; nothing written outside NSTemporaryDirectory.
- What would now unblock: ANEForge-style producer that also fabricates a stats-descriptor
  section (FLEET D9a watch), or a per-task read of the signpost stream (consumer unbuilt).

## Method transfers adopted for EXP-024

- **Rigel checksum trick** (arXiv 2606.12765): every tensor-path result is validated by a
  checksum gate against a CPU reference *before* energy is attributed — our zero-output
  bug-armed case is exactly what this gate catches; the counter never does. Plus
  three-signal triangulation: throughput ceiling, `simdgroup_matrix` comparison,
  per-rail power delta.
- **MSL A/B (Mference rule)**: same matmul, two compilations — MSL 4.0+ tensor-ops
  (`matmul2d`) vs MSL 3.2 `simdgroup_matrix`; decode-shape (M=1) vs prefill-shape
  (M≥400) per the Tungsten envelope.
- **BaseRT-NA** (arXiv 2607.19438): independent confirmation that routing
  compute-bound GEMMs through M5 NA changes prefill throughput 3.9–6.4× vs MLX/llama.cpp —
  a large prefill pJ/token delta between tensor-ops and non-tensor arms is physically
  expected; attribution must show it.
- **ds4 #14**: Apple's MPP Programming Guide (2026-03-16) — M5 GEMM wants hardware-managed
  caching over TG staging; cooperative-tensor + postfix-fusion constructs.

## pJ/token attribution table (M5 Max, user level unless noted)

| engine | signal | user? | measures | pJ/token |
| --- | --- | --- | --- | --- |
| CPU | thread CPU-time; `CPU Energy` | time yes; energy only beside entitled sampler | cluster energy (MCPU/PCPU split) | ΔmJ·1e3 / tokens |
| GPU-shader | `GPU Stats` active/idle ticks; UT centi-% (context only); `GPU Energy` nJ | yes | engagement %, not engine class | ΔnJ / tokens (matched shader arm) |
| GPU floors (trick) | `AGX-DCS-BW F7/F8`, `AGX Energy ≥8W` duty | yes | saturated: 90–96% duty AT IDLE — connected display pins VMAX (DISPEXT0 ~9.6 GB/s constant); no idle/load or shader/NA separation | — (documented trick, not metric) |
| GPU-NA | **no per-unit counter at any level** — root powermetrics (euid 0, 2026-10-06) still exposes 5 GPU keys only; NX-D unfiltered enumeration (2026-10-08, 4606 `--list` entries / 4096-channel JSON subscription) finds **zero TENSOR/NAX-named channels**; the only NAX-reactive user-mode lenses are generic: `GPU Energy` nJ (Δ55× under load) and `GPU UT AggD Stats AGX.Count_UT_Engagement_Perf_State_13` (idle 0 → 125,798/tick) — calibration shows PS13 fires for plain MSL `simdgroup` dispatch too (1.32M dispatches), so **PS13 = top-perf-state engagement, NOT matmul2d-exclusive**; ANE-exclusivity of the ANEXL/ANE-UP SOC-NI pair confirmed disjoint (EXP-027 AN-POS) | delta method | on-die matrix units (Apple M5 post; BaseRT-NA) | **ΔnJ_between_arms / tokens — the unpublished number — GAP; single-tile matmul2d now runs (EXP-027 NX-B), matched-arm Δ still open** |
| ANE | `ANE-DCS-BW` F≥2 duty + `ANE-LNK*` VMAX duty (**calibrated**) | **yes** | ANE floor residency | duty × sudo rail gap / tokens |
| ANE energy | `Energy Model ANE0` stays 0.0 even euid-0; **powermetrics ANE rail works under sudo at 500 ms** — 261.1 mW lane-specific measured 2026-10-06 | root | dedicated rail, not folded | ΔmW-based, measured for granite97m |

Cross-machine rule: M4 AMC byte counters and M5 floor-bin duty are different instruments;
never compare their numbers by channel name — join only at the pJ/token layer (facet
`hw_model` guard, enginemon schema).
