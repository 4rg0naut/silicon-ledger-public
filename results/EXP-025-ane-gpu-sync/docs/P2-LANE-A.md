# P2 Lane A — the producer door, the espresso wall, and the routing verdict (2026-10-07)

Phase-2 follow-up to `VERDICT.md` (kanban `dab9dfe1a23341cd`). Machine: Mac17,14 (M5 Max),
macOS 27.0.1 (26A434), CLT-only (no Xcode). All cited lines live in this pack's `results/`
(`p2_*.txt`); tools in `harness/` (`p2_*`). Nothing here rewrites the phase-1 verdict —
caveat 2 ("Path B blocked by toolchain") turns out to be the WRONG wall, replaced by a deeper one.

## 1. The toolchain GAP was a false wall (A2)

`+[MLModel compileModelAtURL:error:]` — public, CLT-only, no Go, no Xcode — compiles our
EXP-13-era `minilm128.mlpackage` on 27.0.1 in <1 s (`results/p2_compile_at_url.txt`).
The resulting `.mlmodelc` is structurally **identical** to the EXP-003-era bundle:
`{analytics/, coremldata.bin, model.mil, weights/weight.bin}` — and **no `model.espresso.net`
exists anywhere in current bundle formats** (`results/p2_bundle_diff.txt`).

## 2. The legacy `_ANEClient` door is exactly where we stopped (A1)

Feeding the real 27.0.1-compiled bundle through our `pathb` (`modelAtURL:key:` →
`compileModel:`/`loadModel:`) fails at the same translator for both entry points:

```
_ANEEspressoIRTranslator : error Cannot load network '<bundle>/model.espresso.net'
```

(`results/p2_espresso_net_wall.txt`; `pkgb_harness.m` shows `loadModel:` alone hits it too).
The door demands a file generation no current toolchain emits. It is a **legacy door**, not a
package-format puzzle: the espresso net is generated in-process by Core ML's engine stack
before the daemon is ever asked.

## 3. Where the live producer actually is (root fs_usage census)

During a public `MLModel` load of the same bundle, `ANECompilerService.xpc` fires in the
client's service chain: it writes `model.src` into its sandbox temp and produces
`model.hwx` in a hash-keyed cache read back by `aned` (`results/p2_espresso_net_wall.txt`,
excerpt of `/tmp/p2_sudo_capture.txt`, root-owned, out-of-repo). That is the 27-era
MIL→ANE-compiler pipeline: **MIL → ANECompilerService → model.hwx → aned**.

## 4. But the router chose the GPU (the black box earns its name)

`enginemon` over a 600-predict E5 loop: **GPU Energy 443.2 mW mean, 2.35 J in the window;
ANE 0.0 mW, 0 handlers, 0 B DCS traffic, 0 B GFX↔ANE lane** (`results/p2_enginemon_gpu.txt`).
The public stack compiled ANE material for this model and **routed the work to GPU** on the
M5 Max. This is the first measured instance of the routing decision this project set out to
catch: `MLComputePlan`-level accept/refuse is not even the layer — E5's executor made the
call invisibly.

## 5. The E5 runtime rides OUR primitive (steady-state census)

dtrace census on our own probe during steady-state prediction
(`results/p2_census_e5_selectors.txt`; probe `harness/p2_mlmodel_probe.m`, D script
`harness/p2_census.d`, 264 MB raw out-of-repo at root):

- `newSharedEventWithMachPort:` — 131 calls/predict window (MTLDevice mach-port shared events)
- `enableLowLatencyWaitSharedEvent` — 37
- `disableIOFencing` — 131
- `aneExecutionPriority` — 78
- `e5rtStreamReuseExpectation` — 130

The production E5 path wires prediction streams through **mach-port shared events and
IO-fence toggling** — the same kernel primitive whose ANE-side wrappers we measured in phase 1
(~62 µs crossing, 4×-per-eval `sharedEvents` reads). Phase-1's primitive is not an obscure
side door; it is how the shipping stack already talks to the engine.

## 6. kANEF keys confirmed in-process (A3)

`harness/p2_kane_scan.c` (unprivileged dlopen + `__cstring` walk of the shared-cache image):
54 `kANEF*` keys present on 27.0.1, including both targets —
`kANEFDisableIOFencesUseSharedEventsKey`, `kANEFEnableFWToFWSignal` — plus a block encoding
`v24@?0@"IOSurfaceSharedEvent"8Q16` (callback typed on the bridge class itself). Full hit list
`results/p2_kanef_strings.txt`. Behavior tests deferred: they need a loaded ANE program, which
is exactly what the next lane unlocks. (`_ANEStrings` exposes no key selectors —
`harness/p2_kane_strings.m` — the keys are image constants, not runtime properties.)

## 7. What E2E event timing needs now (lane A2b — revised)

To fill `event_extra_ms` we need a program aned will run on the ANE, which on 27 means
feeding the MIL→`ANECompilerService` pipeline or the E5 path, not `_ANEClient compileModel:`.
Ranked options for the next slice:
1. Drive `ANECompilerService.xpc` directly (observe its XPC selectors with the same census
   method while a public load runs; then invoke them ourselves on our MIL).
2. `MLComputePlan`-battery (lane B1) with a model family the router *does* send to the ANE
   (EXP-013-style single-region fp16 conv graphs) — if nothing routes to ANE, the black box
   answer for 27.0.1 Core ML CLT-pipeline models is: GPU.
3. Full-Xcode `coremlcompiler` bundle (espresso-net emitted) on a borrow box — untested
   whether 27's translator still honours it.

## Reproduce (unprivileged parts)

```sh
cd results/EXP-025-ane-gpu-sync/harness
clang -fobjc-arc -o /tmp/mlc_load p2_mlmodel_probe.m -framework Foundation -framework CoreML
/tmp/mlc_load <any .mlmodelc>                      # load+predict+image census
clang -o /tmp/kane_scan p2_kane_scan.c && /tmp/kane_scan      # kANEF key scan
clang -O2 -I . -framework Foundation -framework CoreFoundation -framework IOSurface \
      -framework Metal -ldl -o pkgb_harness pkgb_harness.m
PATHB_DIR=<bundle> ./pkgb_harness pathb             # espresso wall (SKIPC variant included)
../../tools/enginemon                               # while: PROBE_LOOPS=600 mlc_load, see p2_enginemon_loop.sh
```
Sudo parts (user-run): `harness/p2_sudo_capture.sh` → `/tmp/p2_sudo_capture.txt`, `/tmp/p2_census_out.txt`.
