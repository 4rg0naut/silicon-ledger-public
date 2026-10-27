# EXP-045 — Receipts for the scene (closed-claims campaign)

Question: do the hardware claims that shipped inside closed Apple-silicon retro/emulation
threads survive bare-metal re-test on this fleet? Every row below is a bare-metal instrument
on our two boxes (M5 Max Studio, M4 mini). We never ran any third-party runtime; we test the
*hardware claim*, not the project.

Machine legend — **Studio** = Mac17,14 M5 Max 16c, macOS 27.0.1 (26A434), metalfe-32023.921.6,
fingerprint `bda452aabd60bf26`. **mini** = Mac mini M4 16 GB, same OS, same fingerprint.
**No M1 on this fleet** — any comparison to M1-era claims is cross-generation, not same-chip.

Window stamps: Studio windows today carry loadavg ~3.3 (upper-bound timings, stamped per row);
mini windows carry the probe stamp from `raw/`.

## P0 — claim extraction (closed/merged threads → verdict tracks)

| # | Claim (as filed) | Thread / status | Claimed machine | Verdict track |
|---|------------------|-----------------|-----------------|---------------|
| 1 | Metal pipeline-state compiles stall the first frame; pre-baked shader state removes the stall | PS4Recomp (co-latino) #5 — **closed** | M1 | arm A (arm P46 for floor bound) |
| 2 | 33–50 ms frame times attributable to GPU submission/dispatch overhead | PS4Recomp #5 — **closed** | M1 | arm P46 bracket (EXP-046) — GPU-exec floor only; full frame = runtime-required, excluded |
| 3 | 8,582 precompiled shader variants shipped in a metallib because runtime compilation was the bottleneck | MacNativeGames RetroReversing #16 — **merged** | Intel→M-series | arm B |
| 4 | GPU→CPU and CPU→GPU copies are several-fold slower than plain CPU memory copies ("~3×") | n-delic #110 — **merged**; decompdecomp #16 | Intel/M1 | arm D (mini) |
| 5 | Background/low-priority QoS starves GPU-adjacent work at first launch ("default class gets no GPU time under load") | MacNativeGames closed first-frame/QoS threads | M-series | arm E (Studio + mini) |
| 6 | Pinned ~2.2 GB working sets swap/stutter on 16 GB boxes | MacNativeGames closed first-frame threads | 16 GB M-series | arm F (mini, 16 GB) |
| 7 | Shader math builtins with fast-math enabled change emitted results (precision/behavior) | OpenEmu #44 — **merged March** | M-series | arm C (bit-diff tables) |
| 8 | Fence/first-frame presentation latency is dominated by vsync wait, not submit | MacNativeGames closed fence threads | M-series | arm P46 (present-half needs WindowServer session — Studio pid 498 present, bracket captured) |
| 9 | 144 skipped tests hide arch-gated failures ("decompdecomp drop-rule") | decompdecomp #16/#110 | x86/arm CI | **runtime-required** — test-suite semantics, no hardware claim; recorded as drop with reason |

Every row maps to a verdict track or is marked runtime-required. Non-verifiable frame-level
claims (#2 full-frame, fps numbers, on-screen artifacts) stay **not vouched** — hardware floors
only.

## Verdict rows (machine · window · verdict)

| Arm | Verdict | Evidence (machine · window) |
|-----|---------|------------------------------|
| A — PSO cold vs MTLBinaryArchive warm | **confirmed**: 64 PSOs cold 247.4 ms (3.866 ms/PSO) vs archive-rebuilt warm 0.1 ms (0.002 ms/PSO), ratio 2550×. Archive build cost 81.8 ms paid once. Timings upper-bound (loaded window); ratio survives load. | Studio · 13:35Z loadavg 3.25 · [raw](raw/studio-AB-rerun-20261027T133502Z.txt) |
| B — 8.5k-variant compile vs metallib load | **confirmed**: per-variant runtime compile 0.275–0.481 ms vs metallib load 0.0006–0.0018 ms (~300–500×). Extrapolated N=8582: runtime ≈2.4 s vs load ≈5.3 ms (raw line `metallib_load_est_s=5.33` is a unit-label bug in the instrument — value is ms, per-variant math confirms). Offline xcrun cost 0.14–1.4 s one-time per metallib. | Studio · 13:35Z loaded · [raw](raw/studio-AB-rerun-20261027T133502Z.txt) |
| C — fastMath bit-exactness | **confirmed as semantics split**: OFF vs ON bit-equal only 55.6% tanh / 36.6% exp / 71.7% sqrt; **sin 100% bit-identical** (HW sin already strict — seed row for the ulp-atlas). Max rel err vs double ref: OFF 1.3–1.5e-07, ON up to 6.5e-07. Zero NaNs in tested bands. Oracle = bit-diff tables + max-rel-err vs double reference (int maxabs=0 N/A for float builtins). | Studio · 13:23Z · [raw](raw/armC-fastmath-20261027T132351Z.txt) |
| D — copy ladder CPU-vs-GPU ≥256 KB | **shape-dependent, 3× claim upper-bounded at 1.65×**: ratio cpu/gpu 0.57 @256 KB, 1.13 @1 MB, 1.05 @4 MB, **1.65 @64 MB**, 1.06 @256 MB. CPU beats GPU only in the ~1–64 MB band; 3× never observed on shared-buffer path. | mini · 13:24Z ssh window · [raw](raw/mini-dfeb-20261027T132418Z.txt) |
| E — QoS starvation | **shape-dependent**: M4 mini DEFAULT-class workers get itps ratio **0.703** vs USER_INITIATED under 9 default-class loaders (QoS ordering live, 30% deficit). Studio 17-loader run ratio **1.003** — extreme starvation not reproduced under homogeneous load on M5 Max. Claim's strong form ("no GPU time") refuted on both; weak form confirmed on mini. | mini + Studio · 13:24Z · [mini raw](raw/mini-dfeb-20261027T132418Z.txt) · [studio raw](raw/studio-ABp-eb-20261027T132418Z.txt) |
| F — 2.2 GB residency on 16 GB | **confirmed (claim refuted as stutter story)**: 2.2 GB pinned touched in 0.16 s; latency p50 <1 µs, p99 2 µs, p999 7 µs, max 1182 µs single outlier. Swap already 0.71 GB used box-wide; pinned residency held. `vm.page_free_count`/compressed counters read garbage on 27.0.1 (instrument note, see gotcha). | mini · 13:24Z · [raw](raw/mini-dfeb-20261027T132418Z.txt) |
| P46 — dispatch bracket | **floor measured**: commit→complete p50 113 µs (load 0) / 121 µs (load 1); GPU-exec span p50 2.0 / 7.25 µs. GPU-side floor ~2 µs; host round-trip dominates the bracket — bounds #2 but does not vouch 33–50 ms frames. | Studio · 13:24Z loaded, WindowServer present (pid 498) · [raw](raw/studio-ABp-eb-20261027T132418Z.txt) |
| B5 — CPU AMX sgemm + vDSP | M5 Max sgemm 512³ **1428.9 GFLOPS** (loaded → upper bound; consistent-below NCM's 1540 external claim), vDSP_sve **53.6 GB/s** (beats NCM's 37.8 → their path is the limiter, refuted as a ceiling). mini: **1493.9 → 1688.5 GFLOPS** across load 1.4→1.2 (retake; load moves AMX ~13 %), vDSP **105.4–105.8 GB/s** stable. | Studio 13:24Z loaded · mini 13:24Z + 13:37Z retake · [raws](raw/) ([retake](raw/mini-quiet-B5D-20261027T133701Z.txt)) |

## N2 poison adjudication (contested Surface-1 `mm_f32`)

Run on the registered EXP-037 instrument (extended in place: `poison` mode, 0xFF pre-fill,
tf32-revealing needle oracle). **[canonical run](raw/poison_run3-20261027T141021Z.txt) 14:10Z** —
deterministic correctness, load-independent. [run1](raw/poison_run1.txt)/[run2](raw/poison_run2.txt)
(13:13Z) are **superseded**: run1 predates a geometry-label fix (its `multiK`/`big` duplicate rows
show mixed K, not nondeterminism) and run2 carries unlabeled duplicate tf32 rows; all three agree
where comparable. In `/needle` rows the `-> FAIL` marker is the generic bad-count check — the
**class column is the verdict** (`fp32-full` at 2.3e-05 passes the adjudication threshold):

- `mm_f32` (fp32 device tensors, `relaxed_precision=false`): **bit-exact AND fp32-full**
  (needle maxabs 2.3e-05 ≪ tf32 floor 0.11) at single tile, multiN, multiK and 512³×128-tile.
  → Surface-1 **14.0 TF row CONFIRMED as true-fp32 mantissa**, mechanism label **ok**
  (not written-zero, not tf32 artifact). Fleet reading "f32-class 14 TF" stands.
- `mm_tf32` (`relaxed_precision=true`): tf32-truncated everywhere (needle maxabs ≈0.11),
  **never written-zero, never never-written** in this invocation form.
- `mm_f16`, `mm_i8`: pass, bit-exact.
- **NCM split**: their `nax_ladder` form (cooperative destination) fails single-tile with
  written-zero/never-written — same family as our EXP-029 992-of-2048, whose reconciliation
  already sits in GOTCHAS-092. Their "broken at single tile" law is form-specific, not
  universal on 27.0.1. Recorded GOTCHAS-095.

## Deferred (open-flag + decider)

- **C5** (S1 DRAM lanes on mini): armB5 vDSP partially fills; full S1 matrix needs `bench/`
  DRAM harness on mini — decider: next certified-quiet mini window.
- **EXP-047** tile probe: precondition Plasma #1534 still open at execution — **verified open
  2026-10-27** (0 comments); scheduled, not run (needs quiet Studio window).
- Mini D/B5 retake: **done** 13:37Z (uptime-gated loadavg 1.2; quiet_probe.sh not certifiable —
  script writes relative to its own dir and died under /tmp; noted, per-row load stamps used instead).
- Mini P46 bracket: captured 13:38Z → folded into [EXP-046](../EXP-046-dispatch-bracket/README.md).

## Reproduce

```sh
cd results/EXP-045-closed-claims/harness
# clang -fobjc-arc -O2 -o mtl_compile_ladder mtl_compile_ladder.m -framework Metal -framework Foundation
# clang -fobjc-arc -O2 -o retro_probe retro_probe.m -framework Metal -framework Accelerate -framework Foundation
./mtl_compile_ladder a   # arm A   (Studio)
./mtl_compile_ladder b   # arm B   (Studio; needs xcrun metal for offline rung)
./mtl_compile_ladder c   # arm C   (Studio)
./retro_probe d|e|f|b|p  # arms D/E/F/B5/P46
# mini: scp retro_probe mini:/tmp/ && ssh mini '/tmp/retro_probe d'
# N2: EXP-037 harness — /tmp lane_arms poison mode (see lane_arms.m ARM defs)
```

## Corrections (append-only)

- (d) 2026-10-27 ~15:50Z — arm B unit-label bug fixed in the instrument (C-13 round-6): the
  extrap line now prints `metallib_load_est_ms` computed and labelled in one expression; fixed
  re-run `raw/armB-unitfix-20261027T155037Z.txt` (`metallib_load_est_ms=4.4`, loaded window).
  Old lines stand unedited (`raw/studio-AB-rerun-20261027T133502Z.txt`); class record
  `GOTCHAS-098`. No published conclusion used the wrong scale.
