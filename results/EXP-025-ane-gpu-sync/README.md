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
