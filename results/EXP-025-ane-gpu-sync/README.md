# EXP-025 — ANE↔GPU shared-event sync primitive (M5 Max, private paths)

**Status:** primitive **VERIFIED** 2026-10-07 (unprivileged + dtrace + lldb, evidence
in `results/`); end-to-end **package-path timing = GAP** (see Deviations 2 and
"Next steps" Lane A; phase-2 follow-up `docs/P2-LANE-A.md` relocated the wall: not the
toolchain — `compileModelAtURL:` works CLT-only — but the espresso-file legacy door vs
the live `ANECompilerService.xpc` producer, plus a first measured GPU-routing instance). Canonical capture home: `results/EXP-025-ane-gpu-sync/` (this
directory). Provenance: transferred 2026-10-07 from the `AI_dev` session
"SIP blocks aned debug attach" (`clm-run/ane-sync/`, OpenFox session
`98718b89-7e99-4938-84f0-5b97bbdc5538`); content otherwise unchanged except two
path re-points (VERDICT header, build line below). Harness binaries and `.dSYM` were
not transferred (rebuildable); `raw/MANIFEST.sha256` pins every committed file of this
pack.

**Machine:** Mac17,14 (M5 Max) · macOS 27.0.1 (26A434) — the Studio.

## Question

Can a Metal encoder gate ANE evals **without a CPU round-trip** — i.e. do the ANE's
private shared-event classes and `MTLSharedEvent` sit on the same kernel signalling
primitive, and does the eval dispatch actually consume them?

## Headline

**Yes — with two caveats** (full evidence chain: `VERDICT.md`; failure log F1–F17:
`FAILURES.md`; symbols: `docs/SYMBOLS.md`; traces: `docs/TRACE.md`):

- `_ANESharedWaitEvent` / `_ANESharedSignalEvent` / `_ANESharedEvents` exist on
  27.0.1; their ivar type is `IOSurfaceSharedEvent` — a runtime-only class, absent
  from the 27 SDK headers.
- The bridge is a **mach port**: `MTLSharedEventHandle.eventPort` feeds
  `[IOSurfaceSharedEvent initWithMachPort:]` — one kernel event object, two wrappers.
  A GPU `encodeSignalEvent:` was observed through the IOSurface-side wrapper in
  **~62 µs** (`results/porttest.txt`, T2; bidirectional via T3).
- dtrace (pid-provider, own process): eval dispatch reads `-[_ANERequest sharedEvents]`
  **exactly 4× per `processRequest:`** — shared events are a first-class eval input
  (`results/dtrace_ane_methods.txt.gz`).
- Caveat 1: attaching events on the in-memory-MIL path (Path A) SIGSEGVs at
  `processRequest+1524` (addr 0x10), deterministic — consumption appears
  firmware-gated to the Path-B `intermediateBufferHandle` flow, independently
  corroborated by `tmc/apple` Go bindings (`ErrSharedEventRequiresPackage`:
  "shared events require package-backed models (ModelTypePackage)").
- Caveat 2: Path B never ran end-to-end here (toolchain gap below), so the latency
  table's event column carries `PATHB_ONLY`, not numbers. Baseline CPU-completion
  floor: 0.10–0.63 ms/eval, events overhead 0.005–0.053 ms (`results/latency.md`).

## Chaining result (2026-10-10) — data crosses the wire, both ways

Follow-up that turns the counter proof (API-103) into a **data** chain, standalone
(`harness/chain_harness.m`; public Metal + runtime-only `IOSurfaceSharedEvent`, no private
ANE framework). Each iteration the GPU compute kernel writes a per-iteration pattern into an
IOSurface and signals; the ANE-side wrapper waits and the CPU **verifies the surface content**.
Reverse direction too.

```
C1 GPU->wrapper : waits=500/500 verified=500/500  median handoff 123.2 us
C2 wrapper->GPU : waits=500/500 verified=500/500  median handoff 135.7 us
VERDICT: data+sync crossed the boundary in BOTH directions
```

Evidence `results/chain_harness.txt`. **Scope:** this is the *wire the ANE uses* (API-102/103/
104), driven end-to-end with data; it does NOT put a running ANE program on the other end —
that integration stays blocked (Path-A crash on attached `_ANESharedEvents`; Path-B
shared-event SIGSEGV, F-40). Record `API-141`.

### Path (b): the shipping stack — joined, but not ANE-specific (2026-10-10)

Interposing the shipping Core AI stack (`harness/join_chain.m` via `DYLD_INSERT_LIBRARIES`
over the public runner, 20 evals × 4 arms) shows Apple's own code **does** use the primitive —
13 `IOSurfaceSharedEvent` counters (one per ANE region), 260 signals, and a duplicate wrapper
over one port read the live value (`signaledValue=40`) → **we joined a live counter**.

**But it is not the ANE route:** the counts are *identical* under `cpuOnly`, `gpu`,
`neuralEngine` and `default`, and `-[_ANERequest setSharedEvents:]` never fires. These are
generic MPSGraph/Metal-side counters; Core AI's ANE execution does not use the `_ANERequest`
shared-event route. Evidence `results/join_chain.txt`, record `API-142`. The ANE-specific
e5rt/E5 route (API-115) is Core ML's ANE execution and needs an ANE-routed `.mlmodelc`.

### Core ML *is* that route (2026-10-10)

A blind-spot sweep of the workspace clones turned up the missing piece — an **ANE-eligible
CoreML model** (`conv_512x64_d8.mlpackage`, 8× fp16 conv, `[1,512,1,64]`, in
`m5max-ai-bench/models/coreml/`). Running it through `MLModel` (`cpuAndNeuralEngine`):

- **it lands on the ANE** — `ANEXL U = 18271`, `ANE UP = 18252` over 100k predictions
  (0.187 ms/call); and
- interposition separates the stacks cleanly:

| stack | `-[_ANERequest setSharedEvents:]` | `IOSurfaceSharedEvent` created/signalled |
|---|---|---|
| **Core ML** | **101 calls (all nil)** | 0 / 0 |
| Core AI | 0 calls | 13 / 260 (generic, arms-invariant) |

So **Core ML drives the ANE through `_ANERequest`**; Core AI does not. The gap that remains:
a *pure-ANE* workload attaches **no events** (all nil), so there is no inter-engine chain to
join yet — that needs a **mixed ANE+GPU model**. Evidence `results/coreml_ane_route.txt`,
record `API-143`.

**Split search (negative):** a placement oracle (`harness/coreml_plan.py`, coremltools
`MLComputePlan`) shows Core ML keeps an eligible conv graph **entirely on the ANE** (pure
8-conv, and 6-conv + `gather`/`pad`/`interp`/`maxpool`), and a CPU-only op (`topk`) moves the
**whole** graph to CPU — so no non-nil cross-engine chain arises from these shapes.
`results/coreml_placement.txt`, `GOTCHAS-074`.

### The ANE-side event, captured (2026-10-10, path ii)

Hooking the **creation** path (request initializer/factory, `_ANESharedEvents`, and
`_ANESharedSignalEvent`/`_ANESharedWaitEvent`) — not just `setSharedEvents:` — reveals what the
first attempt missed: **Core ML's ANE request is created with a non-nil `_ANESharedEvents`**
(the getter returns non-nil **2/eval**), carrying a `_ANESharedSignalEvent` bound to an
`IOSurfaceSharedEvent` counter (401 signal events over 200 predictions; **1 distinct counter**
reused; value 0 at bind). Core AI attaches none. The counter is neither built via
`initWithMachPort` nor signalled via the ObjC setter → the write is hardware/firmware-side.
So the **ANE-side inter-engine event object is real and capturable**. Evidence
`results/ane_event_joined.txt`, record `API-144`.

**But it is inert for a single-engine workload** (5000 predictions): the signal value is always
`0` and the retained counter, polled at ~5000/s, **never moves** (`samples=7124 distinct=1
final=0`). The object is attached to every request but not armed — so a *live* cross-engine
handoff needs a genuinely partitioned ANE+GPU model. Record `API-145`.

**Partitioned model tried — still not armed.** A local **FluidAudio** model (`parakeet-tdt`
`Encoder.mlmodelc`) *is* partitioned: `MLComputePlan` shows **1381 ANE + 4 CPU** ops. Running it,
the counters still never move (8 counters, **22,715 polls, all 0**; signal value 0), and with
`compute_units=all` the same Encoder is placed **entirely on the GPU** — so Core ML does not
co-schedule ANE+GPU on this box; the only split is ANE+CPU. The live ANE↔GPU handoff therefore
stays unobserved with the available models. Evidence `results/coreml_partition_no_arm.txt`,
record `API-146`.

### Core ML's placement heuristic — first decision table (2026-10-10)

`harness/coreml_route_sweep.py` reads `MLComputePlan` (per-op device **and** the planner's own
`MLComputePlanCost.weight`) over one-axis-at-a-time models. First findings:

- **`compute_units` caps the candidate set**: `cpu`→CPU, `gpu`→GPU, `ne`/`all`→prefer ANE.
- **fp16 is a gate** (fp32 conv → CPU).
- a conv is ANE-placed only above **~1.5e8 FLOPs** (~7.5e7 MACs), and the threshold **scales with
  kernel area** (k=3 flips at 74.6→78.0 M MACs; k=5 at 74.6→80.3 M) → a **compute**, not shape,
  threshold. Bracket: FLOPs (149.3, 156.0] M.

Evidence `results/coreml_route_sweep.txt`, record `API-147`.

**Plan == runtime (P2).** A just-below/just-above pair (C=352 → plan CPU; C=384 → plan ANE), 20000
predictions each: `ANEXL U = 0` for the below model, **12065** for the above — so the threshold is
honoured at runtime, no silent fallback for this case. (First attempt used the ObjC runner, which
crashed on zero-shape inputs; its reading was compile-side and was discarded — the Python runner
`harness/coreml_run.py` is the correct instrument.) Record `API-148`.

**P3 recon — the plan code is reachable (2026-10-10).** CoreML's binary is a broken symlink (code
in the dyld shared cache; `dyld_info` can't target one image), so we read the **loaded** image at
runtime (`harness/coreml_image_probe.m`: `_dyld_get_image_header`+slide, parse `LC_SEGMENT_64`) and
disassemble at a method IMP with `llvm-mc`. Routing entry points: `-computeDeviceUsageForMLProgramOperation:`
@`0x191f7c2a8`, `-estimatedCostOfMLProgramOperation:` @`0x191f7ab84`,
`+computePlanOfModelStructure:modelAsset:configuration:error:` @`0x191f7c420`. A constant search
for 1.5e8/1e8/2e8/7.5e7 found **nothing in `__TEXT`/`__DATA_CONST`** → the threshold is **computed**,
not a literal. Evidence `results/coreml_plan_recon.txt`, record `API-149`.

**Guided walk (P3b).** `harness/coreml_walk.m` decodes BL/B/ADRP/ADD/MOVZ/MOVK from the mapped image
and follows internal callees — it resolves the call graph and data refs (e.g. an ADRP+ADD to a
`device_fault…` string) — but a depth-3/40-function walk finds **no `movz/movk` building the
threshold** either ⇒ the ~1.5e8-FLOP gate is **derived** from other fields, not stored. A naive
whole-`__TEXT` MOVZ/MOVK adjacency scan is too noisy; full recovery needs a decompiler on the
extracted cache image or a directed walk. Record `API-150`.

**P3c — full disassembly tooling (`ipsw`).** Homebrew `ipsw` (3.1.735) both **extracts** the
cache-only CoreML image to a real Mach-O and **disassembles at cache addresses with labels**
(`ipsw dyld disass --vaddr`). At the placement entry the path runs **double-precision**
comparisons (`fcmp d0,#0.0` / `b.hi` / `csel`) — cost weights, not integer thresholds, exactly
as API-150 concluded. Evidence `results/coreml_plan_disasm.txt`, record `API-151`.

**P3d - call path traced (address-space caveat).** `ipsw`'s `--vaddr` space is **not** the runtime
address space: a first decompile fed with a runtime IMP (`0x191f7ab84`) returned BLAS code
(`cblas_dsymm`), while the runtime dump of the same address begins with a prologue - so the
authoritative bytes are the runtime dump (`coreml_image_probe` -> `llvm-mc`), and `ipsw` is used for
extraction/symbols only. On the correct bytes: `computeDeviceUsageForMLProgramOperation:` is a
**wrapper** -> op-attribute extractors -> `sub_191F7ADB4` (cost region) -> `sub_191F7BC30` (the
device-usage builder) -> returns a dictionary; `estimatedCostOfMLProgramOperation:` is a wrapper that
builds a cost object, reads a **double** (`sub_65395280`), NaN-checks it (`fcmp d0,d0`/`b.vs`) and
formats it. `sub_191F7BC30` switches on a compute-unit enum
(`switch(sub_65408860(v0)) { case 1/2/4 }`, power-of-two unit masks) with **no float comparison**
(integer sentinel + bit-mask filter only). The cost->unit **predicate is not in these wrappers** - it
lives in their callers, which is the next pass. Evidence `results/coreml_plan_callpath.txt`, record
`API-152`.

**P3e - correction: no floating point in this path (API-153).** Having established the
address-space rule, the P3c floating-point claim was re-checked on the **correct** bytes and
**withdrawn**: `computeDeviceUsageForMLProgramOperation:` touches no `d0`/`s0` at all, and across
the examined cluster (device-usage wrapper, `estimatedCost` wrapper, cost engine, builder) the only
float instruction anywhere is the single `fcmp d0,d0` NaN check in the `estimatedCost` wrapper.
`API-151` is marked **contested**. New tool `harness/coreml_findcallers.m` (reverse scan: BL/B sites
by target + 8-byte pointer-table matches) then mapped the cluster: `sub_191F7ADB4` is its **own**
function (432-byte frame) doing tag-keyed dictionary lookups over tags {1,2,4,5,6} with no
accumulation and no cost comparison; `sub_191F7BC30` is called only from `0x191f7bb60` and
`0x191f7c358`; the ObjC method IMPs have **no direct BL callers** (msgSend only). So everything
reachable from the two ObjC entry points is **attribute plumbing + per-unit config lookup** - the
numeric decision is delegated to unread callees (and may live at ObjC plan-assembly level, which a
static scan cannot see).

**P3f - dynamic: the decision is a preference, and the flip point re-derived (API-154/155).**
Since a static scan cannot see `msgSend` callers, the question was taken to the API itself.
New `harness/plan_devicesupport.m` walks a compiled model through the plan and dumps, per op, the
preferred device, the supported device list, **and the private per-device support info**
(`-deviceSupportInfoArray` / `-supportInfoForComputeDevice:` -> `MLComputePlanDeviceUsageSupportInfo`
with `_state` + `_computeDevice`). Result: at **both** sides of the threshold (conv 1.89e7 FLOPs ->
CPU, 1.21e9 -> ANE) both CPU and ANE are **supported** with `_state = 0`; only `preferred` moves.
**So placement is not a support/eligibility gate - it is an internal cost/perf preference**, and
the API exposes the decision but not the comparison. Running the oracle over a one-variable sweep
re-derives the gate independently of the earlier route table: for C=256 conv3x3 the CPU->ANE flip
sits between **1.416e8** (CPU, H=12 W=10) and **1.557e8** FLOPs (ANE, H=12 W=11) - corroborating
API-147's ~1.5e8. SDK-27 API drift was also fixed on the way: the ObjC plan entry point is now
**async** (`+loadContentsOfURL:configuration:completionHandler:`), devices are `id<MLComputeDeviceProtocol>`,
`program.functions` is a dictionary - and a no-ARC harness must `retain` the plan handed to the
handler or the next `[plan modelStructure]` segfaults. `coreml_plan.m` was stale and is fixed;
both harnesses build and agree.

**P3g - the gate is not conv FLOPs alone (API-156).** With the oracle cheap now, one-conv sweeps
across kernel size and channels were run (`harness/plan_flip_sweep.sh <k> <C> <H,H,...>`). Each
single config flips monotone in FLOPs, but the flip point moves with the config, and there is a
**deterministic counterexample at identical work**: at 1.4746e8 FLOPs (= 7.37e7 MACs) a
`k=1 C=256 25x45` conv is **ANE**-preferred while a `k=5 C=128 15x12` conv is **CPU**-preferred
(3/3). In MACs the flip brackets cluster within ~10% (k=1 ~7.2-7.4e7, k=5 ~7.4-7.9e7, k=3/C=64
still CPU at 7.5e7) but are not equal, and the difference tracks neither weight count nor output
count alone. So the earlier "~1.5e8 FLOPs gate (kernel-scaled)" is a **config-specific correlate**,
not a law: the planner weighs a per-op cost model with inputs beyond FLOPs.

**P3h - designed experiment: the gate is arithmetic *plus a kernel term* (API-157).** Holding the
arithmetic fixed at 7.4e7 MACs and moving only the shape (`harness/plan_mac_probe.py`), **every 1x1
conv is ANE-preferred and every 3x3 conv is CPU-preferred**, across C=64/128/256/512. Bisecting the
threshold per config (`harness/plan_hw_sweep.sh`) puts 1x1 at **<=7.30e7 MACs** and 3x3 at
**(7.47, 7.90)e7** at the same C=192 - the threshold **rises with kernel size**. Practically: 1x1 ->
ANE from ~1.44-1.46e8 FLOPs, 3x3 from ~1.50-1.56e8 FLOPs, so **"~150 MFLOPs" is a good ~+/-10%
rule of thumb for 3x3 but not the law**. Screening the obvious single-factor metrics against the
table refutes each: output count, weight count, spatial size and arithmetic intensity all have an
ANE row that sits on the wrong side of a CPU row.

**P3i - and it does not survive in a network: placement is a GRAPH decision (API-158).** Real models
are multi-op, and the planner normalises cost across the graph, so the single-op rule was tested
against padded conv stacks (`harness/make_graph.py`). Result: **no graph was ever mixed** - every op
in a graph takes the *same* device - and the CPU->ANE boundary is a clean, deterministic, monotone
phase diagram in (layers N, spatial H):

```
        H=4   H=6   H=8   H=11  H=16
  N=1   CPU   CPU   CPU   CPU   ANE
  N=2   CPU   CPU   CPU   ANE   ANE
  N=3   CPU   CPU   ANE   ANE   ANE
  N=4   CPU   ANE   ANE   ANE   ANE
  N=5   CPU   ANE   ANE   ANE   ANE
  N=6   ANE   ANE   ANE   ANE   ANE
```

**This contradicts the single-op rule outright:** six convs of 9.44e6 MACs (5.66e7 total) go
*entirely* to ANE, while a **single** conv of 7.14e7 MACs - seven times the per-op work - stays CPU.
Every single-scalar explanation was screened and refuted (total MACs, per-op MACs, op count,
weights, N*H - each has a counterexample pair in the results file). **Practical consequence:** for a
real multi-layer model the "~150 MFLOPs per conv" rule of thumb is not a predictor; read the plan of
the actual model (`plan_devicesupport` / `coreml_plan`) or force the engines via the compute-unit
configuration.

**P3j - reconciliation: capability filter + group decision (API-159).** P3i's "no mixed graphs" sat
uneasily with a real mixed plan already in this ledger (API-146). Resolved by reading that same
local model with the new harness:

| compute_units | plan |
|---|---|
| `cpuAndNeuralEngine` | **1381 ANE + 4 CPU** |
| `all` | **1385 GPU + 0 CPU** |

and the four CPU ops are `ios17.cast` (x2), `ios17.expand_dims`, `ios17.less` - type/shape plumbing
and a comparison yielding a boolean mask, i.e. **exactly the ops the ANE cannot execute** (under
`all` they run on the GPU, so nothing is left on CPU). So the split is a **capability filter**, not
a cost decision; where every op is executable, P3i's single-device phase diagram applies to that
capable group. P3i's "no mixed graphs" is therefore a property of *all-capable* graphs - which also
explains why none of the synthetic conv/pool/softmax/topk graphs split. Side benefit: this
reproduces API-146's 1381/4 **and** its all-GPU swap from an independent harness.

**P3k - and the real trigger is DTYPE, not op type (API-160).** Two follow-ups corrected P3j's
wording. (i) *Instrument lesson:* a battery of 65 single-op models (`harness/ops_battery.py`) came
back **all CPU** - including `relu` and `conv` - because a single small op is below the P3h
threshold; the battery measured **size**, not capability. Re-run with three big convs in front of
the op and *every* op (including `less`, `cast`, `topk`, `sort`) is ANE. (ii) *Causal A/B*
(`harness/make_dtype_test.py`, MIL builder): the **same graph**, only the tail dtype changed -
`fp16` tail → all ANE; `int32` tail → `cast`/`expand_dims`/`less` go **CPU** while the convs stay
ANE; an `fp32` export cast stays ANE. That matches the real model's MIL, whose CPU path is exactly
the lengths/mask plumbing: `cast → int32`, `expand_dims` on int32, `less(int32,int32) → bool`,
`expand_dims` on bool. **The ANE is an fp16 data path**; ops that must *carry* int32/bool data are
placed on CPU. (The file's other int32/bool entries are attributes - axes/strides/pads - i.e.
constants, and are fine.)

**P3l - layer 3 resists (negative, API-161) + the practical rules fall out.** Two more attempts to
reach the graph-level rule failed honestly: (a) the planner's *own* cost number is a **normalised
equal share** - in a chain of N identical convs each conv reports `weight = 1/N` and every `relu`
reports `0` - so it carries no decision signal; (b) `+computePlanOfModelStructure:modelAsset:
configuration:error:` @`0x191f7c420` is a **wrapper/validation path** (no op loop, no cost
comparison, no `msgSend` selector; it validates, calls a same-image boolean helper and delegates
outward), so the decision sits in a callee outside that body; (c) an additive model
(`ANE iff ΣMAC_i + β·N ≥ Θ`) is **refuted** by the phase diagram - `(5,5)` CPU and `(6,4)` ANE
force β > 1.71e7, while `(3,7)` ANE and `(5,5)` CPU force β < 6.5e6. What *does* fall out is worth
more than the formula: the measured rules are now a user-facing **GOTCHAS-075** - keep the data path
fp16 (int32/bool plumbing forces CPU), read the plan instead of guessing per-op sizes, treat
"~150 MFLOPs/conv" as a ±10% correlate only, and remember `computeUnits` caps (and can move) the
whole model.

## Deviations (declared, not silent)

1. **Transfer re-points.** Only two lines differ from the AI_dev capture: the VERDICT
   header path and the build command's `cd`. Evidence files are byte-identical to the
   manifest-era originals; rebuild and re-run to regenerate.
2. **Path B end-to-end GAP.** The system Espresso compiler rejected every local model
   source (`results/pathb.txt`: `InvalidNetworkSourceFileName`; no full Xcode,
   `MLModel.compile` missing in the bench venv). **Phase-2 correction:** the toolchain
   gap was a false wall — `+[MLModel compileModelAtURL:error:]` works CLT-only and the
   real 27 wall is `_ANEClient`'s demand for a `model.espresso.net` no current bundle
   format emits (`results/p2_espresso_net_wall.txt`). Lane A below closes this via the
   producer path.
3. **F14 crash fix inside the capture.** A delayed ANE completion block dereferenced
   the autoreleased options dict under GPU load; fixed with a statically retained
   options dict + per-eval request retain in `harness/ane_bridge_mrr.m`; latency table
   re-reproduced 2/2 after the fix.
4. **`ane_bridge_mrr.m` is a locally patched copy** of the `silicon-ledger-bench`
   `ane_bridge.m` (submodule untouched at capture time — pack FAILURES F8).

## Layout

- `harness/` — sources (`.m/.d/.sh/.py`); binaries + `.dSYM` gitignored, rebuild below.
- `results/` — evidence. Raw dumps >1MB are gzip'd (`zcat results/dtrace_ane_methods.txt.gz`);
  docs quote their lines with the `.gz` names. `ane_spike.json` is an earlier (16:50)
  mini-probe artifact retained for provenance, not referenced by the verdict.
- `raw/MANIFEST.sha256` — sha256 of every committed file in this pack.

## Build / reproduce

```sh
cd results/EXP-025-ane-gpu-sync/harness        # from the silicon-ledger repo root
clang -O2 -I . -framework Foundation -framework CoreFoundation \
      -framework IOSurface -framework Metal -ldl \
      -o ane_sync_harness ane_sync_harness.m
./ane_sync_harness porttest                      # T1/T2/T3 bridge tests (unprivileged)
ANE_STOP2=1 ./ane_sync_harness latency           # 5-batch baseline table (events phase skipped: pack FAILURES F11/F14)
ANE_ONE=1 ANE_SP=128 ./ane_sync_harness x        # single compile+eval
sudo ./trace_primary.sh                          # dtrace -c runs → results/dtrace_primary.txt
sudo ./trace_ane_attach.sh                       # -[_ANE*] pid-attach → results/dtrace_ane_methods.txt
./inspect.sh                                     # lldb live-instance dump (no sudo)

# placement oracle + decision inputs (SDK 27; links CoreML)
clang -O2 -framework Foundation -framework CoreML -o coreml_plan coreml_plan.m
clang -O2 -framework Foundation -framework CoreML -o plan_devicesupport plan_devicesupport.m
# a one-conv model, then read the decision + per-device support info:
#   /Volumes/data/OpenFox/AI_dev/silicon-ledger-bench/tools/.venv/bin/python make_conv.py m.mlpackage 256 12
#   ./plan_devicesupport m.mlpackage cpuAndNeuralEngine
# reverse-reference scan of the loaded CoreML image (BL/B sites + pointer tables):
clang -O2 -framework Foundation -o coreml_findcallers coreml_findcallers.m
#   ./coreml_findcallers 191f7bc30 191f7adb4
```

`ane_sync_harness.m` `#include`s `ane_bridge_mrr.m` (retain-fixed copy of the
silicon-ledger-bench `ane_bridge.m`; see Deviation 3).
Re-runs write uncompressed `.txt`; re-gzip before commit. SIP note: `dtrace -c` cannot
probe the dlopen'd AppleNeuralEngine (probes enabled pre-`main`) — spawn then attach
with `-p` (pack FAILURES F2, recipes in `docs/TRACE.md`).

## KB cross-refs

`knowledge/ane/02-private-api.md` §2/§3.3/§5/§8 (shared-event family, promoted to
measured on this machine) and `FAILURES.md` F-40…F-42 (ledger-level rules distilled
from pack F2/F11+F14/F8).

## Next steps (phase 2 — kanban `dab9dfe1a23341cd`, "the routing black box")

- **A1. DONE 2026-10-07 → new wall.** The hand-emitted Path-B bundle and a
  freshly-`compileModelAtURL:` bundle both load into the legacy `_ANEClient` door and
  both die at `_ANEEspressoIRTranslator : Cannot load network …/model.espresso.net`
  (`results/p2_espresso_net_wall.txt`). The door is legacy; the 27 producer is
  `ANECompilerService.xpc` (`docs/P2-LANE-A.md` §3). E2E event timing is re-scoped to
  lane **A2b** (`docs/P2-LANE-A.md` §7): drive `ANECompilerService` XPC directly, or
  ride the E5 path (which already uses our mach-port shared-event primitive,
  `results/p2_census_e5_selectors.txt`).
- **A2. DONE 2026-10-07.** `+[MLModel compileModelAtURL:error:]` compiles CLT-only in
  <1 s (`results/p2_compile_at_url.txt`); bundle diff vs the EXP-003-era `.mlmodelc`:
  structurally identical, and **neither carries `model.espresso.net`**
  (`results/p2_bundle_diff.txt`). Bonus measurement: over a 600-predict loop `enginemon`
  shows the router sent this ANE-eligible model to **GPU** — ANE 0.0 mW, 0 B DCS
  (`results/p2_enginemon_gpu.txt`). First caught routing decision.
  **Re-stamped 2026-10-08 (lens validation, EXP-027 AN-POS):** the counter that
  would have caught ANE activity is `PMP0/SOC-NI → 'SOC-NI9 ANEXL U'` (ANE-exclusive:
  0→14,746 on a known full-ANE-region program, stays 0 under GPU load; companion
  'SOC-NI8 ANE UP' 9→13,766). It read 0 in this window ⇒ GPU routing is a
  lens-validated TRUE NEGATIVE (KB API-114 re-stamp, API-127)."

- **A3. PARTIAL 2026-10-07.** In-process scan finds both keys on 27.0.1 —
  `kANEFDisableIOFencesUseSharedEventsKey`, `kANEFEnableFWToFWSignal` (+52 neighbours,
  one block typed `v24@?0@"IOSurfaceSharedEvent"8Q16`) — `results/p2_kanef_strings.txt`.
  Behavior probes need a loaded ANE program: folded into A2b.
- **B/C/D.** Scheduler black box (`MLComputePlan`/`MLComputePlanCost` per-op device
  maps), NAX (Metal 4 tensor API on M5 Max), and synthesis: mapped onto existing board
  tasks — B4/B5 `f6f758ea0e3cee2b`, C6/C7 `cab6d2d0942693de`, TOOL-4
  `a0bcf78ce2a48653`, TOOL-5 `2b9c190ab9faada8` (direct dispatch prerequisite),
  TOOL-7 `7aa716f0fd58cf8e`, TOOL-10 `1cefcd81d0617916`. No duplication.
