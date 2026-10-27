# EXP-044 — Metal 4.1 gates & lane parity across two generations; the 4 GiB ANE wall is an OS regression

## Question
Rigel (arXiv:2606.12765, M4 Max, macOS 27.0-beta) published three load-bearing claims we could extend:
(1) Metal 4.1 fp8 `matmul2d` is emulated (0.94× fp16) — a footprint feature; (2) `matmul2d` runs on the
GPU shader/simdgroup path, no dedicated matrix unit, no ANE routing — explicitly "cross-generation is
future work"; (3) the 4.1 surface is double-gated (Xcode 27 *and* macOS 27.0; a 4.1 binary refuses to
load on 26.5). Simultaneously: EXP-043 pinned our ANE shared-blob wall at file-size crossing 2^32 —
but "one OS build" was its declared caveat. The MacBook Air 15" M4 (Mac16,13, macOS **26.6.2**) joined
the fleet as the first pre-27 bench box; EXP-044 tests all of it.

## Machine roles
- **Studio** Mac17,14 M5 Max, 27.0.1/26A434, toolchain metalfe-32023.921.6 — compile source + C3 lanes. **Loaded window (oMLX up)**: parity ratios are the claim, absolutes stamped.
- **Air** Mac16,13 M4 base (10c GPU on-machine verified), 26.6.2/**25G83**, Xcode 27.0 installed but Metal Toolchain component ABSENT (thin install) — C2a load gates + C4 bursts + C5 wall. Cockpit box (user's screen-sharing terminal): burst protocol, thermal state logged (no warnings), load ~2.7 declared.
- mini not needed this round (its 27.0.1 wall data from EXP-043 is the paired cell).

## Results

### C2a — the version gates, reproduced verbatim on our silicon (`raw/gate-26.6.2-20261027T101433Z.log`)
| artifact (built on Studio 32023.921) | macOS 26.6.2 load | dispatch |
|---|---|---|
| `-std=metal4.0`, unpinned floor | **REFUSED**: "deployment target (0x00020009) not supported on this OS" | — |
| `-std=metal4.0 -mmacosx-version-min=15.0` | OK | c_write PASS; g_f16 matmul2d bit-exact incl. full-shape oracles |
| `-std=metal4.1 -mmacosx-version-min=15.0` | **REFUSED**: "language version 4.1 which is not supported on this OS" | — |

Three findings: (a) Rigel's language-version gate reproduces word-for-word on 26.6.2 — and the Air runs
**Xcode 27.0**, proving the gate is the OS, not the Xcode generation; (b) an **orthogonal, undocumented
deployment-target floor gate** (new here, filed GOTCHAS-093) — cross-OS metallib shipping must pin
`-mmacosx-version-min`; (c) M4-base GPUs run MPP `matmul2d` fp16 correctly on 26.6 via the offline route.
fp8-type compile gate re-checked at this toolchain (4.0 rejects type, 4.1 accepts) — GOTCHAS-091 holds.

### C3 — M5 Max lane matrix + decode K-ladder (`raw/lanes-20261027T101521Z.log`, `raw/decode-4096-20261027T101456Z.log`)
@4096³ (loaded): **f8 31.92 | bf16 31.53 | f16 31.40 TF** — EXP-037 parity band reproduced ±1.7 %.
@2048³: f8 32.18 | bf16 31.79 | f16 31.77 | f32 11.63 | i8 57.87 TF (i8 = 1.82×, matches EXP-037 1.74×
and the A19 1.8× report). **bf16 is a band-dweller**: it rides the fp16 lane exactly; ComfyUI's
"bf16-decode fast route" is the fp16 rate, not a new lane. All ladders bit-exact; full-shape @4096³
oracles 16,777,216 samples **maxabs=0** for f8/f16/bf16.

**Decode M=1 (padded to 64-row tile), the regime where fp8's half-bytes MUST pay off** (min-ms):
K2048 f8 **−8.4 % faster** than f16 · K4096 −1.3 % · K8192 **+2.8 % SLOWER**. The byte advantage exists
only at small K and dissolves exactly where operand streaming (f8 64 MiB vs f16 128 MiB) should double
it. fp8 is footprint-only in the compute regime (EXP-037) *and* in the decode regime (this). The decode
to bf16 buys zero speed over staying fp8; the reported "~4× vs f32" is the bf16-vs-f32 gap (ours: 2.7×
at 2048³ — methodology differs, MLX path unmeasured here).

### C4 — M4 base rates (`raw/air-f16-bursts2-20261027T104259Z.log`)
g_f16: 3.29 TF @2048³ (5.2276 ms, 100 reps), 3.25 TF @4096³ (42.35 ms, 30 reps), bit-exact full-shape;
decode-padded 1.021 ms @K4096, 6.365 ms @K8192. No thermal warnings. **Per-core cross-check vs Rigel:
0.33 vs 0.37 TF/core (88 %) — independent two-lab corroboration that pre-NAX matmul2d fp16 rides the
per-core shader path.** (Their 14.8 TF is their M4 Max @2048³ stable-clock; ours cockpit-loaded.)

### C5 — THE HEADLINE: the 2^32 ANE wall is a macOS 27 regression (`raw/air-wall-26.6.2-20261027T104348Z.log`)
Same bench (bench/ane-dma-test.m), same h16g ANE generation, only the OS differs:
| C | file = 32·(128+2·C²) B | 27.0.1 (mini h16g / Studio h17g, EXP-043) | 26.6.2 (Air h16g, this) |
|---|---|---|---|
| 8128 | 4,228,124,672 | OK CORRECT | OK CORRECT (63.2 ms) |
| 8192 | 4,294,971,392 = **2^32+4096** | **REFUSED Code=10 verifyBundleAtPath** | **OK CORRECT** (177.3 ms cold) |
| 9216 | 5,435,822,080 | (not run — wall already below) | OK CORRECT (80.9 ms) |
| 10240 | 6,710,890,496 | — | OK CORRECT (100.0 ms) |
| 12288 | 9,663,680,512 | — | OK CORRECT (143.6 ms) |
| 14336 | 13,177,139,200 (784 MiB/core) | — | **OK CORRECT** (195.3 ms) |
Streaming holds 66.9–67.4 GB/s across every size. On 26.6.2 this h16g accepts **≥13.2 GiB** — the
"4 GiB wall" appeared with macOS 27.0 in the load-verify path. Every published ceiling is an
OS-stamped number. Filed API-174; EXP-043 gets an append-only addendum; the sidekick #104 draft is
corrected **before posting**.

## What this says upstream
1. To Rigel's authors: their "cross-generation future work" is answered for M5 Max from our side —
   fp8 parity (not 2×) replicates on NAX silicon too (EXP-037 + EXP-044 C3), bf16 = fp16 band, and
   their version gate reproduces verbatim on 26.6.2 with Xcode 27 installed (OS gate, not Xcode gate).
2. To the M6 crowd ("does fp8 at ~2× fp16", r/LLMDevs single-source): the checklist that makes it
   falsifiable — (i) fp8/fp16 ratio at ≥4096³ vs the 1.5× pre-registered bar, (ii) decode-M=1 K-ladder
   (where our M5 shows the byte advantage dissolving), (iii) bf16 lane identity, (iv) OS+toolchain pair
   reported always (EXP-044 C5 proved ceilings are OS-version-pinned), (v) placement via matched-A/B
   energy, not engagement lenses. Draft: `work/outreach/rigel-m6-opencells.md` (super-root).
3. To anyone shipping metallibs: pin your deployment target (GOTCHAS-093), and stamp the OS on every
   "ANE limit" number you publish (API-174).

## Open cells
- 26.x ceiling beyond 13.18 GiB (RAM-bound on the 16 GB box).
- certified-quiet Studio re-take (EXP-038 watcher pid 76816 still armed).

## C2b RESOLVED (2026-10-27, after user installed the Metal Toolchain component — `raw/c2b-air-local-compile-20261027T110435Z.log`)
Xcode 27.0's toolchain (metalfe-32023.921) **on** macOS 26.6.2 emits `__METAL_VERSION__ == 410` at
`-std=metal4.1` and compiles `metal_fp8_e4m3_format` on a 26.x box — but the locally-built 4.1
metallib is then refused at load by its own OS ("language version 4.1 … not supported on this OS"),
while a local 4.0 build loads and computes bit-exact. The two-part gate is now fully separated on
one machine: **compile surface = Xcode generation; runtime = macOS version**. A 26.x user with
Xcode 27 can write fp8 kernels and cannot run them. Rigel's gate finding fully corroborated;
untested remnant: whether Xcode *26.x* ever emits 410 (Air has Xcode 27 — their "26.5/26.6 emit 4.0"
half stands unchallenged from our side).

## Window state
Studio: LOADED (oMLX production up) — all C3 figures are within-window parity claims; absolute ms stamped.
Air: cockpit-load ~2.7, GPU idle between bursts, pmset thermal clean — absolutes stamped, ratios and
acceptance verdicts are the claims. Neither box is certified-quiet this round; the M4/M5 per-core
comparison borrows Rigel's clock-stable regime and does not claim cross-box absolute parity.

## Reproduce
```sh
# Studio (toolchain box)
cd results/EXP-044-metal-generations/harness
clang -fobjc-arc -O2 -o lane_arms44 lane_arms44.m -framework Metal -framework Foundation
./lane_arms44 ladder                                  # all 5 lanes bit-exact
sh run_lanes44.sh decode                              # decode K-ladder f8/f16/bf16
sh run_lanes44.sh full                                # 2048/4096 matrix (slow full-shape oracles)
sh compile_gate44.sh                                  # gate_ctl40*.metallib gate_all41*.metallib
# Air (26.x box) — ships as metallibs; -mmacosx-version-min pin is load-bearing (GOTCHAS-093)
xcrun -sdk macosx metal -std=metal4.0 -mmacosx-version-min=15.0 -c gate_kernels44.metal -o a.air
xcrun -sdk macosx metallib a.air -o gate_ctl40b.metallib
clang -fobjc-arc -O2 -o gate_load44 gate_load44.m -framework Metal -framework Foundation
./gate_load44 gate_ctl40b.metallib g_f16 2 4096 4096 4096 30
# C5 wall on old OS
clang -O2 -o ane-dma-test44 bench/ane-dma-test.m -framework Foundation -framework IOSurface
SHAPES="8192,8192,64,32" SAME_SHAPE=1 SHARED_BLOB=1 ITERS=3 ./ane-dma-test44
```
