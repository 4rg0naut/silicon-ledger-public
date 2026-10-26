# EXP-035 — Chaining-Blob Crack: raw-door chaining PARKED at Gate-A (client-state word, not blob grammar)

Campaign: **EXP-035 chaining-blob** (2026-10-23, studio M5 Max Mac17,14 `bda452aabd60bf26` +
mini M4 `057b28dd036ddbe8`, macOS 27.0.1/26A434). Question entering (C-82): how is the 3152 B
`ANEProgramChainingPrepareArgs` (door selector 2) built, and can an unprivileged client build it?
Predecessor chain: EXP-032 (door map + `ane_dsc` grammar) → EXP-033 (selector contracts) →
EXP-034 (sel-2 handle ladder parked with the blob-grammar gap). This campaign consumed that gap.

## Headline verdict

**PARKED-WITH-NAMED-GAP — the blob was never the gate.** Rejection happens in the
`ANE_ProgramChainingPrepare_locked` prologue gate (`[[ANEClientDeviceCore+0x10]+0x88] == 0` →
`0xE00002C2`), BEFORE any args byte is read (`raw/prep_locked.asm` 0x9370ea4-0x9370eac). A LIVE
in-process handle (`state=3`, same process, witness `live handle=6061`) behaves exactly like a
bogus one: ladder 6/6 arms + cnt-loop 12/12 uniformly `kr=0xE00002C2` (`raw/p8_arms.jsonl`).
The kernel-log decider confirmed it by the right kind of absence: the `[ERROR]`-level
`Could not find program for handle` string — which always reaches the log — appears ZERO times
across all 18 rejected calls (`raw/sudo_kernel_log_20261023T192852Z.txt`); the
`getProgramResource` key gate is provably never reached. Process-level program registration
(`ANE_AddClientForProgram … probe8_replay to programHandle: 0x186d`) happens and is NOT
sufficient — the Gate-A word is per-client-instance. Meter witness: engine took ZERO work
(ANE-DCS F1-only floor, EXP-022 idle signature, `raw/p8_meter.jsonl`); zero residue every run
(`raw/p8_ioreg_witness.txt`).

## Lane closures (each a bounded step, all run same day)

- **C-84 in-process capture: negative, named.** DYLD interposition (self-validated poison-first:
  probe6b 12/12 byte-identical under insert) shows our framework compile+eval traffic sends the
  door ONLY `OPEN + sel0` — across 100 evals, zero program/chaining selectors. Eval transport is
  aned XPC + the EXP-025 mach-port mailbox; kernel-door ioctls are setup-only. A wire blob cannot
  be lifted from our own door traffic (`CAPTURE.md` §1-2).
- **C-85 handle source: closed.** `probe7_capture` mints live `_ANEModel.programHandle`
  (5842/5883, small sequential kernel counter) — the fill value for `args+0x10`. Build gotcha
  recorded: probe must compile `-fobjc-arc` (MRC frees the autoreleased model mid-flight).
- **Open-type lane: closed.** `probe9_opentype`: only types {1,4} open unprivileged; aned's
  type-2 class (the one on the successful load path, per the kernel log) is
  `kIOReturnNotPrivileged` for us — Mach-permission layer, not door layer. Type-forge dead.
- **C-87 lead handed forward:** the only untested Gate-A setters left were direct-path selectors
  2–10 after an in-process load (load-then-sweep). EXP-036 ran exactly that and closed the line
  **CONFIRMED LOAD-BLIND** (clean negative 3/3; claims MEASURE-164/165). Daemon-free chaining
  redirects to the EXP-025 mailbox lane.

## Cross-checks

- `CROSS-CHECK-26A434.md`: everything ane-infer's MIT framework-level chaining fix needs is
  PRESENT on 26A434; consistent with our raw-door ground, no contradiction. Mutable-weights API
  is present on 26A434 (not 27-only) but carries `mutableWeightsBufferID=0 size=0` for
  in-memory-compiled programs.
- `INVENTORY.md`: C-82 home-base census — every probe/asm source with path → gives → caveats →
  REUSE/EXTEND/REPLACE verdict, committed before any new probe.

## Artifacts

- `CAPTURE.md` — full method + verdict narrative (interposition, captures, C-85 verdict, kernel-log decider).
- `CROSS-CHECK-26A434.md` — selector census vs ane-infer (MIT).
- `INVENTORY.md` — C-82 prior-art census table.
- `raw/` — `prep_locked.asm` / `get_program_resource.asm` / `chaining_prepare.asm` (gate disasm),
  `OFFSET_MAP.md` (3152 B arg map, C-83), `p8_arms*.jsonl` (+stderr), `p8_meter.jsonl`,
  `p8_ioreg_witness.txt`, `p9_types.txt`, `capture_*` (interposition), `sudo_*` (kernel-log decider runs).
- Probes: `tools/ane_door_probe/probe7_{capture.m,interpose.c}`, `probe8_replay.m`,
  `probe9_opentype.m`, `sudo_verify.sh` (sudo pack, ran 2026-10-23).
- Claims: EXP-035 findings flow into `knowledge/ane/14-door-map.md` narrative; the closing
  measurements are claimed in EXP-036 (MEASURE-164/165).

## Reproduce

```sh
cd tools/ane_door_probe
clang -fobjc-arc -O2 -o probe7_capture probe7_capture.m -framework Foundation -framework IOKit   # ARC mandatory
clang -O2 -dynamiclib -o probe7_interpose.dylib probe7_interpose.c -framework IOKit
clang -O2 -o probe8_replay probe8_replay.m -framework Foundation -framework IOKit
codesign -s - -f probe7_capture probe8_replay probe7_interpose.dylib
./probe9_opentype            # {1,4} only — closed lane witness
DYLD_INSERT_LIBRARIES=./probe7_interpose.dylib ../../results/EXP-032-pulse-map/harness/mil_battery baseline   # CAPTURE.md §1
../../results/EXP-032-pulse-map/harness/mil_battery baseline   # unperturbed self-test control (12/12 byte-identical kr)
```

## Limits / open

- Gate-A word: no user-space setter found for the direct-path class; deciding whether a
  valid-type-2 client passes the key gate is UNOBSERVABLE unprivileged (both branches return
  `0xE00002C2`). Owner-gated: entitlement ruling, or the EXP-025 mailbox lane instead.
- All conclusions single OS build (26A434), studio box; mini confirms door parity only.
- INVENTORY row `raw/EXP-032-pulse-map/raw/ane_dsc.asm` is now `.gz` (zcat) — packaging change 2026-10-26.
