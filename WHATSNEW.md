# What's new — 2026-10-27 (round 5: ceilings are OS-pinned — the 4 GiB "wall" is a macOS 27 regression)

Same status key: **NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public — house terms decoded in [`GLOSSARY.md`](GLOSSARY.md).
Finding numbers remain global and monotonic; this round adds `#26`–`#29` on top of `#1`–`#25`.
Priors behind every verdict: [`knowledge/ane/SOURCES.md`](knowledge/ane/SOURCES.md).

A third machine joined the fleet — a 15" MacBook Air M4 base (`Mac16,13`, 16 GB, **macOS 26.6.2**),
the first pre-27 bench box — and it immediately paid for itself: the 2^32 byte wall from round 4
(`#20`) **does not exist on macOS 26**. Round 4's numbers stand exactly as measured — on 27.0.1 —
and `#26` restates them OS-stamped. Same round: the two orthogonal gates that decide whether a
metallib loads (one of them undocumented), a lane-parity replication, and a cross-lab per-core
corroboration on the pre-NAX chip.

| # | Finding | Status | Evidence |
|---|---|---|---|
| 26 | **The 2^32 B ANE weight wall is a macOS 27 regression, not silicon** — at 27.0.1/26A434 both h17g (M5 Max) and h16g (M4 mini) refuse the 4,294,971,392 B blob (`Code=10 verifyBundleAtPath`), while the **same bench, same h16g ANE generation** on 26.6.2/25G83 (M4 base Air) accepts that size and keeps accepting, exact to the `out[0]==C` oracle, up to 13,177,139,200 B (784 MiB/core) at a steady 66.9–67.4 GB/s. **Every published ANE ceiling is an OS-stamped number.** | **NEW as a correction** — supersedes the un-OS-stamped reading of `#20` (whose measurements stand as taken on 27.0.1) | [`EXP-044 wall log`](results/EXP-044-metal-generations/raw/air-wall-26.6.2-20261027T104348Z.log) · [`EXP-044 README`](results/EXP-044-metal-generations/README.md) · [`EXP-043 README + addendum`](results/EXP-043-m5max-weight-budget/README.md) |
| 27 | **Two orthogonal gates decide metallib loading — pin the deployment target** — a 27-SDK build without `-mmacosx-version-min` is refused on 26.6.2 by a **deployment-target floor** ("deployment target (0x00020009) not supported on this OS" — the error names the target, not the language version); pinned to 15.0, the Metal 4.0 lib loads and computes bit-exact. The Metal 4.1 **language** gate is separate and OS-bound, not Xcode-bound: the Air runs Xcode 27.0 on 26.6.2, its local toolchain emits `__METAL_VERSION__ == 410` and compiles fp8 — then the same OS refuses the 4.1 metallib at load. **Compile surface = Xcode generation; runtime = macOS version.** | **NEW** (deployment-target floor gate); **EXT** (published Metal 4.1 language gate, reproduced verbatim on our silicon) | [`gate matrix log`](results/EXP-044-metal-generations/raw/gate-26.6.2-20261027T101433Z.log) · [`C2b local-compile log`](results/EXP-044-metal-generations/raw/c2b-air-local-compile-20261027T110435Z.log) · [`EXP-044 README`](results/EXP-044-metal-generations/README.md) |
| 28 | **NAX lane parity replicates; bf16 rides the fp16 lane; fp8's byte advantage dissolves at decode** — @4096³ (loaded window): f8 31.92 / bf16 31.53 / f16 31.40 TF (our own prior band ±1.7 %); @2048³: i8 57.87 TF = **1.82×** fp16 (matches an independently published A19 ratio of 1.8×), f32 11.63 TF; decode M=1 K-ladder: f8 is 8.4 % faster than f16 at K2048, 1.3 % at K4096, and **2.8 % slower** at K8192. Full-shape @4096³ oracles 16,777,216 samples, maxabs=0. | **EXT** (replicates our EXP-037 band on a new session/window; corroborates published M4-Max ratios on NAX silicon) | [`lane matrix log`](results/EXP-044-metal-generations/raw/lanes-20261027T101521Z.log) · [`decode ladder`](results/EXP-044-metal-generations/raw/decode-4096-20261027T101456Z.log) · [`EXP-044 README`](results/EXP-044-metal-generations/README.md) |
| 29 | **Pre-NAX `matmul2d` fp16 rides the per-core shader path — cross-lab corroboration at 88 %** — M4 base on 26.6.2 via offline metallib (pin per `#27`): 3.29 TF @2048³, 3.25 TF @4096³ bit-exact, decode-padded 1.021 ms @K4096; **0.33 vs 0.37 TF/core** against an independent lab's clock-stable M4 Max figures on the same 10-core-per-GPU framing. | **EXT** (independent two-lab confirmation of a published per-core rate) | [`M4 bursts log`](results/EXP-044-metal-generations/raw/air-f16-bursts2-20261027T104259Z.log) · [`EXP-044 README`](results/EXP-044-metal-generations/README.md) |

### The numbers behind round 5

- `#26` — the refusal bracket from `#20` simply disappears on 26.6.2: C=8192/9216/10240/12288/14336
  all accepted with exact output. Different chassis (Air vs mini), **same ANE generation (h16g),
  same bench binary**; OS build is the only material variable. 13.18 GiB is a **lower bound** — the
  16 GB Air hits RAM/disk pressure before any ceiling does; the 26.x ceiling above it stays open.
- `#27` — the two errors read alike at a glance; only one names a language version. Filed
  internally as GOTCHAS-093; the shipping rule: pass `-mmacosx-version-min` explicitly, and stamp
  the OS on every limit you publish.
- `#28` — Studio window was production-loaded (oMLX up): **ratios are the claim**, absolutes are
  window-stamped, per house convention.
- `#29` — Air ran cockpit-loaded (~2.7) with clean thermal logs; the per-core comparison borrows
  the published clock-stable regime and claims no cross-box absolute parity.

EXP-038 (certified-quiet lane re-take) remains in flight and is still not shipping numbers here.

---

# What's new — 2026-10-27 (round 4: the real ANE weight wall, and the trap that fakes limits)

Same status key: **NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public — house terms decoded in [`GLOSSARY.md`](GLOSSARY.md).
Finding numbers (`#1`–`#25`) are **global and monotonic** — oldest round first — so a number cited
anywhere (issue, doc, chat) pins exactly one finding forever. Priors behind every verdict:
[`knowledge/ane/SOURCES.md`](knowledge/ane/SOURCES.md).

Two community constants took hits this round. The "1 GiB ANE weight limit" turns out to be a
32-bit file-size wall on both of our chips — four times higher than the folklore. And the
"multi-input requests fail (0x1d)" limitation does not reproduce at all; what does reproduce is a
compiler-cache trap that presents exactly like it. Both measured on two chips, same OS build.

| # | Finding | Status | Evidence |
|---|---|---|---|
| 20 | **The ANE weight wall on the shared-blob private path is a 2^32 B file-size limit, not a capacity policy** — accepted 4,228,124,672 B, refused 2^32+4096 (`Code=10 verifyBundleAtPath`), **identical on M5 Max and M4 mini at the same OS build**. The circulated "1 GiB" framing understates this budget ~4×. | **NEW as a correction** | [`EXP-043 README`](results/EXP-043-m5max-weight-budget/README.md) · [`byte-wall log`](results/EXP-043-m5max-weight-budget/raw/byte-wall-2_32-20261027T002835Z.log) |
| 21 | **A second, count-shaped wall, cleanly separable from the byte wall** — 248 conv tensors compile and compute exact, 256 are refused (`ANECCompile Code=1`), identical on both chips. Distinct from the published 16-weight-files refusal, which counts separate files — a third axis. | **NEW** | [`EXP-043 README`](results/EXP-043-m5max-weight-budget/README.md) · [`count-256 arm`](results/EXP-043-m5max-weight-budget/raw/count-256-20261026T232416Z.json) |
| 22 | **The multi-input ANE limitation does not reproduce on the eval path — a cache-key trap fakes it** — 10/10 arms (N=1..4, controls) compile AND evaluate bit-exact on both chips; zero 0x1d. The trap: the compile bundle key is derived from **MIL text only**, so arms sharing text but differing in weight bytes collide in the compiler cache. | **NEW** (the mechanism, with reproductions); **EXT** — replicates a published M4 two-input result, extended to N=4, unequal sizes, and the M5-era chip | [`EXP-041 README`](results/EXP-041-multi-input/README.md) · [`battery raw`](results/EXP-041-multi-input/raw/battery-studio-20261026T232314Z.txt) · [`rejected-load capture`](results/EXP-041-multi-input/raw/rejected-load-231150.txt) |
| 23 | **Compile-time model for the in-memory path: ~1.6–1.8 ms/conv + ~14 ms fixed, and no compile-cache reuse** — a 32-conv graph cold-compiles in 66.9 ms (M5 Max) / 78.6 ms (M4 mini); repeat compiles are not faster. The only multi-second compile is the refusal-validation path (22.6 s). | **NEW** (per-conv compile scaling with a declared negative on reuse) | [`EXP-042 README`](results/EXP-042-cold-compile/README.md) · [`ladder raw`](results/EXP-042-cold-compile/raw/ladder-studio-20261026T232934Z.txt) |
| 24 | **The W8-palettized embedding penalty is machine-pinned, not a constant** — same graph, matched same-window A/B: **1.57× slower than fp16 on M5 Max** vs **4.8× on M4 mini**; load penalty 8.2× vs 39×. Still a loss on this graph — a storage lever only. | **NEW** (the second machine's number); **KNOWN** that palettization is storage-only for this model class | [`EXP-039 README`](results/EXP-039-w8-palettization/README.md) · [`latency raw`](results/EXP-039-w8-palettization/raw/lat-w8-20261026T233525Z.json) · [`EXP-005 (M4 side)`](results/EXP-005-ane-residency/README.md) |
| 25 | **A published "M4 fp16 zero-collapse" does not replicate on the M4 base — and ANE fp16 outputs are cross-chip bit-identical** — 0 zeros in 13,440 embedding components on every surface; the fp16 embedding dumps from both chips' ANEs are **sha256-identical** on the same OS build. | **NEW** (negative replication + cross-chip bit-identity we could not find published) | [`EXP-040 README`](results/EXP-040-m4-fp16-zero-collapse/README.md) · [`gate captures`](results/EXP-040-m4-fp16-zero-collapse/raw/mini-cpu-gpu-gates.txt) |

### The numbers behind round 4

- `#20` — accept/refuse bracket is 1.6% wide with 2^32 inside it; both chips at OS build
  27.0.1/26A434; the accepted 4,228,124,672 B blob computes exact output. The reported
  M1 Max ~1.022 GB refusal is real for that chip/surface, not a constant.
- `#21` — bracket 3.2% wide, size-independent: the refused 512 MiB blob sits 8× below the
  byte ceiling; empty error body on every refusal.
- `#22` — arms covered index-reversal control, unequal input surface sizes, and three fill
  patterns; the trap was caught on our own harnesses, with before/after captures filed.
- `#23` — measured on M5 Max (66.9 ms) and M4 mini (78.6 ms); `ANECCompile` recompiles
  in-process and cross-process; Apple publishes no compile-cost model here.
- `#24` — warm p50 19.11 ms vs 12.17 (M5 Max), 19.48 vs 4.05 (M4 mini); the build is
  2.3× smaller than the published fp32 build, 167 vs 195 MB against our own fp16 build.
- `#25` — min cosine ≥ 0.99996 against an fp64 oracle on every surface (cpu/GPU/ANE);
  "chip X is low-quality" reports are surface/software stories until a dump says otherwise.

One experiment is deliberately not in this round: the certified-quiet re-take of the round-2 lane
matrix (EXP-038) is still in flight — its ladder cells stay DECLINED, not estimated, until the quiet
window completes. Rule stated in [`PUBLISH-POLICY.md`](PUBLISH-POLICY.md): unfinished windows do not
ship numbers.

---

# What's new — 2026-10-26 (round 3: the integer lanes, and the door)

Same status key: **NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public — house terms decoded in [`GLOSSARY.md`](GLOSSARY.md).
Earlier rounds follow below, newest first. Finding numbers in this round ran `#1`–`#19`; the
numbering has since been consolidated into one global monotonic sequence (see round 4) — so a
number cited anywhere (issue, doc, chat) pins exactly
one finding forever. Priors behind every verdict: [`knowledge/ane/SOURCES.md`](knowledge/ane/SOURCES.md).

| # | Finding | Status | Evidence |
|---|---|---|---|
| 15 | **First published int8 and fp32 lane numbers for the M5 Max NAX tensor units** — hand-written MSL `matmul2d`, bit-exact against exact-integer oracles: **int8 55.2 TF @4096³ = 1.74× the fp16/fp8 band** (independently matches a published A19 ratio of 1.8×), **fp32 14.0 TF** @4096³, decode (M=1, 64-row padded tile) i8 0.0679 ms @K4096. Measured in a loaded-box window and declared as upper bounds. | **NEW** | [`results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv`](results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv) · [`README`](results/EXP-037-fp8-nax/README.md) |
| 16 | **fp8 (`metal_fp8_e4m3_format`) executes natively on NAX** — 32.0 TF @2048³, bit-exact 24/24, energy at parity-with-noise vs fp16; it **requires `-std=metal4.1`** (4.0 rejects the type — measured), and the 4.1 gate is fp8-specific, not device-tensor-general (the f32/f16 arms compile at 4.0 too). | **NEW** | [`results/EXP-037-fp8-nax/results/fp8_matrix-20261026T1356Z.tsv`](results/EXP-037-fp8-nax/results/fp8_matrix-20261026T1356Z.tsv) |
| 17 | **The IOKit side door into the ANE, mapped** — direct-path round-trips 3.2–7.1 µs (success), error returns from 0.6 µs, and the submit gate is **CLOSED and load-blind** (36/36 cells): the door answers whether the box is busy, not how busy; side-door injection observed 0.5–7.3 µs (n=141). | **NEW** | [`results/EXP-033-door-map/README.md`](results/EXP-033-door-map/README.md) · [`raw sweep`](results/EXP-036-side-door-inject/raw/probe10_sweep_run1.jsonl) |
| 18 | **int8 flips sign between fleets**: 4.8× *slower* than fp16 on the M4 mini's ANE (round-1 finding) vs **1.74× faster** on the M5 Max's GPU tensor lane — quantization advice does not transfer between engines, even within one vendor generation. | **EXT** — extends our own M4 result | [`results/EXP-005-ane-residency/README.md`](results/EXP-005-ane-residency/README.md) · [`lane_matrix tsv`](results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv) |
| 19 | **A single consolidated lane reference, gated** — every lane measured on this fleet in one table, per surface, each cell carrying window·metric-convention·instrument·capture-link; 13 contaminated sets quarantined (kept, stamped, excluded); 9 open flags with named deciders. | **NEW** (process; published because drift is the failure mode it prevents) | [`knowledge/ane/16-neural-accelerators.md`](knowledge/ane/16-neural-accelerators.md) |

---

# What's new — 2026-10-10 (round 2: the GPU Neural Accelerators, and the tooling memory)

This mirror is the **distilled** public slice of a private Apple-silicon reverse-engineering
corpus (private paths scrubbed, evidence kept). This page is the one-screen summary: what the
latest round found, and — honestly — **what is new versus already public**. Full priors are in
[`knowledge/ane/SOURCES.md`](knowledge/ane/SOURCES.md) ("Novelty check 2026-10-10").

## Status key
**NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public.

## The findings

| # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | A **cross-chip arch identity**: the Core AI compiler target is `h17c` on an M5 Max and `h16g` on an M4 mini, while the older private `_ANEDeviceInfo` selector returns the `g` form on both (`h17g`/`h16g`) — so it agrees on the M4 and **diverges on the M5 Max**. | **EXT** — the rule is public, and the **M4 half is our own merged PR** ([coreai-model-zoo #36](https://github.com/john-rocky/coreai-model-zoo/pull/36)); new: the M5 Max `h17c` target + the selector divergence | [`results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt`](results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt) |
| 2 | **Core AI's on-disk specialization cache decoded** — the `~/Library/Caches/coreai-cache` layout (`modelHash` per model vs `optsHash` = a pure function of the compute-unit options). Nothing public documents these bytes. | **NEW** | [`results/EXP-026-ane-kitchen/results/coreai_cache_format.md`](results/EXP-026-ane-kitchen/results/coreai_cache_format.md) |
| 3 | **The cached `mpsgraph` bytecode printed as readable MLIR** — a stub dialect plugin + a bytecode rewrite recover the op graph, region functions, shapes and `mps.aneArch`/`aneRegionsSHA`. | **EXT** — "MPSGraph is MLIR bytecode" is public (Apple's LLVM RFC, `mpsgraphtool`); **new**: the private `aicode`/`placement` dialects and the printing technique | [`results/EXP-026-ane-kitchen/results/p2b_model_src_ir.txt`](results/EXP-026-ane-kitchen/results/p2b_model_src_ir.txt) |
| 4 | **`PMP0/SOC-NI9 "ANEXL U"` is a lane-exclusive, calibrated ANE activity counter** — 0 in every idle/GPU/CPU window, ~19.6k under ANE work. The channel is known; its **exclusivity** is not. | **NEW as a discriminator** | [`results/EXP-027-nax/results/p27_anpos_promote.txt`](results/EXP-027-nax/results/p27_anpos_promote.txt) |
| 5 | The `PMP0` **`ANE-DCS-BW` floor-residency channel is *not* ANE-specific** (reads higher at idle than under ANE load), and the **`Fast-Die CE` utilization histogram reads 0** even during confirmed ANE work — so the channel public tools use for "ANE utilization" is dead on this box. | **NEW** (negative results) | [`p27_anpos_promote.txt`](results/EXP-027-nax/results/p27_anpos_promote.txt) |
| 6 | **Apple's on-device Foundation Model uses the Neural Engine** — measured with the calibrated exclusive lens, unprivileged: `ANEXL U` reads 0 at idle and 10,862 across a 25-call `fm` burst. (Lane mix: ANE-active; no GPU engagement above idle.) | **NEW method** (the fact was known via xctrace; the repeatable unprivileged measurement is new) | [`results/EXP-002-apple-fm-baseline/results/fm_lane_audit.txt`](results/EXP-002-apple-fm-baseline/results/fm_lane_audit.txt) |
| 7 | The **ANE↔GPU "direct link" carries data, both directions** — a GPU kernel writes an IOSurface and signals; the ANE-side event wrapper waits; content verified every iteration. 500/500 both ways at ~123 µs / ~136 µs, unprivileged. | **NEW** (the wire the ANE uses, driven end-to-end with data; putting a live ANE program on the other end is still blocked) | [`results/EXP-025-ane-gpu-sync/results/chain_harness.txt`](results/EXP-025-ane-gpu-sync/results/chain_harness.txt) |

A correction note for finding #1 is filed upstream:
<https://github.com/sbryngelson/ane-guide/issues/1>.

## What this mirror is (and is not)
- **Is:** measured numbers, the failure corpus, and the instruments, with every claim carrying its
  command and its caveats. The claim layer is machine-checkable — see
  [`PUBLIC-OPENCLAIMS.md`](PUBLIC-OPENCLAIMS.md) (702 claims, 827 provenance events, 0 invalid).
- **Is not:** vendor claims, or a promise that any of the private/documented Apple interfaces are
  stable. Where a claim is an AI's check rather than a human's, it says so.

Start at [`README.md`](README.md) and [`PUBLIC-INDEX.md`](PUBLIC-INDEX.md).

---

# Round 2 continued — same day, the GPU side (findings 8–14, published as it happened)

Same status key: **NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public — house terms decoded in [`GLOSSARY.md`](GLOSSARY.md).

| # | Finding | Status | Evidence |
|---|---|---|---|
| 8 | **The widely-repeated "M5 multi-tile `matmul2d` silently no-ops — Apple compiler regression" is REFUTED on this box.** Third-party MetalHLO runs all 8 of its GEMM benchmarks correct against MLX, **including 4096x4096** (2048 threadgroups, cooperative-tensor MPP path), through the **legacy** pipeline with MSL 4.0. Our own no-op was a *usage* artifact (device destination, wrong accessor, MSL 4.1). | **NEW as a correction** (the failure is discussed publicly; the refutation is ours) | [`results/EXP-029-nax-crosslane/README.md`](results/EXP-029-nax-crosslane/README.md) |
| 9 | **Measured NAX lane matrix on M5 Max** — NAX (MPP `gemm_loop`) **2.26x faster than the shader/SIMT path at 4096^2**, ~2.0x less GPU energy for the same work, and **all three GPU datapaths collapse to ~0.43 ms at decode (M=1)**. | **NEW** (vendor material claims NAX is faster; no NAX-vs-SIMT-with-energy matrix that we could find) | [`results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md`](results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md) |
| 10 | **Engine comparison on identical GEMMs (fp16, K=N=4096)**: GPU beats the ANE **10.2x / 7.3x / 5.4x** at M = 1 / 512 / 2048 wall-clock — including decode. A **bare `matmul` does reach the ANE** at 2048^3 (refining the older "Linear falls back off-ANE" guidance), while the **1x1-conv form of the same GEMM is 2.1x slower** on the ANE. | **NEW** (measured); **KNOWN** that the ANE prefers conv shapes | [`results/EXP-029-nax-crosslane/docs/NAX-ACTIVATION-AND-MEMORY.md`](results/EXP-029-nax-crosslane/docs/NAX-ACTIVATION-AND-MEMORY.md) |
| 11 | **Unprivileged, symmetric lane attribution for one workload**: the ANE arm shows **GPU Energy 0.00 mJ with `ANEXL U` = 896**; the GPU arm shows **`ANEXL U` = 0**. | **EXT** — extends finding #4 (the ANEXL calibration) | [`NAX-LANE-MATRIX.md`](results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md) |
| 12 | **Measurement hazards, measured** (they invalidate joules if ignored): GPU idle power swings **25 -> 104 mW inside 30 s**; this machine's only "display" is the **screen-share virtual display** (no physical monitor) and `WindowServer` exists only while sharing, so the **headless floor is ~0-3 mW vs 27-85 mW while sharing**; and the `DISP*/DISPEXT*/VDD*` "RT" counters are **free-running ~24 MHz** (measured at 23.99 MHz with *no display attached*), so they are **not** display/activity signals. | **NEW** (the free-running-counter trap family was documented for `ANE_*_TRIG`; `DISP*` is new) | [`results/EXP-029-nax-crosslane/results/QUIET-STATE.md`](results/EXP-029-nax-crosslane/results/QUIET-STATE.md) |
| 13 | **A locale hazard that silently corrupts power data**: with `LANG=fr_FR`, Apple CLIs print comma decimals (`9,1`); the shared rail parser matched only `[\\d.]+`, so localized samples were **dropped without error**. Fixed and self-tested. | **NEW** (our fix; the bug class is generic) | [`bench/_power.py`](bench/_power.py) · [`tools/publish/push-mirror.sh`](tools/publish/push-mirror.sh) |
| 14 | **An instrument registry with a gate** — 193 instruments indexed across five locations with a *capability* map (which instrument is canonical for timing / joules / lane activity / matmul2d ladders / placement / ledger), plus a one-command gate set that **fails** when a tool exists on disk unregistered. | **NEW** (process; published because anyone with the same problem can use it) | [`tools/TOOLS.md`](tools/TOOLS.md) · [`tools/registry.py`](tools/registry.py) |

**What is published vs private in round 2 (so a reader knows what they cannot see):** the mirror
carries the **evidence and the instruments** — `bench/` in full (including `.py`/`.m`), `tools/`,
`knowledge/`, and `results/**` as `.md`/`.json`/`.txt`/`.sh`. **Private-only:** the per-experiment
`results/**/harness/*.{m,metal,c,h,py}` sources, the gzipped raw captures, `repos/`, `models/`, and
the agent rule files under `.omp/`.
