# EXP-035 C-84 — in-process capture verdict (2026-10-23, studio M5 Max bda452aabd60bf26, 26A434)

Question: does the proven in-process `_ANEInMemory` path hand us the door traffic +
a live `ANEClientProgramHandle` we can replay through sel-2?

## Method

DYLD interposition IN OUR OWN PROCESS (no SIP issue): `tools/ane_door_probe/probe7_interpose.dylib`
hooks `IOConnectCallMethod` (10-param ABI — structInput params 5-6, scalar output 7-8
per IOKitLib.h 26A434), `IOConnectCallStructMethod`, `IOServiceOpen`; hexlogs every
struct input (≤4 KB), scalars, kr. Defensive pointer probes (`vm_read_overwrite`) —
capture never trusts a caller pointer before proving readability.

Shim validated BEFORE framework contact (poison-first discipline): known-good
`probe6b_chain` sel-2 ladder under insert → 12/12 full 3152 B `structIn` hexdumps,
`kr` output byte-identical to unperturbed run, exit 0 → zero perturbation.
Three real bugs fixed in the 18:10 draft (dlsym(RTLD_NEXT) self-recursion → SIGSEGV;
wrong ABI arg order; selector-misread-as-size 2-byte dump). First draft dying on its
own self-test is why the self-test is the gate.

## Captures

### 1. Compile path — `mil_battery baseline` under insert (`capture_mil_battery_baseline.txt`)

Door (`H1xANELoadBalancer` type-1): `OPEN kr=0` + `sel0 136 B kr=0` ONLY.
`IOSurfaceRoot` conn: `sel 0xd`, `sel 0x2c kr=0xe00002f0`, 2× `sel0 244→3176`.
**No door chaining/program selector (2/4/5/6/8/9) in-process.**

### 2. Eval path — `ncm0 anectx --field` under insert (100 evals, 24 capture lines)

Three compiles → three `OPEN + sel0` pairs; same IOSurfaceRoot + AGX setup traffic;
`evals=100 median=6560 µs` identical to unperturbed (6593 µs — machine-state band),
parity line unchanged (`mismatch_float=476/15800`, `bad_cells=0`).
**Across 100 evals: ZERO door selectors beyond sel0.** The eval transport is aned XPC
plus the `_ANESharedEvents`/`IOSurfaceSharedEvent` mach-port mailbox (EXP-025) —
kernel-door ioctls are setup-only at IOKit level.

**Honest negative, named:** the raw door never sees a framework program/chaining call
from our process → a captured wire blob for sel-2 CANNOT be lifted from our own door
traffic. C-83's handle-global-table insight is what saves the plan:
`getProgramResource` resolves from the GLOBAL ANEDriver table, so a handle registered
by ANY client (ours included, via aned load) works on our door connection.

### 3. Handle source, closed — `probe7_capture` (`capture_probe7_handles.json`)

Direct ObjC flow (baseline.mil = EXP-032 proven grammar dump, sha256
`204a66051a3c66b1a1e5cdc3bc918f80e317b10548d3ad7c86c9b35c7cf71892`, byte-exact via
`MIL_DUMP=1 ./mil_battery baseline`), model read while on-stack alive:

    run 1: programHandle=5842 state=3(loaded) eval_ok=true intermediateBufferHandle=0
    run 2: programHandle=5883 state=3 eval_ok=true intermediateBufferHandle=0

`_ANEModel.programHandle` agrees with `_ANEInMemoryModel.programHandle` (5842/5883) —
the C-85 fill value for `args+0x10` is a small sequential u64 (kernel counter), minted
by every fresh compile+load process. `intermediateBufferHandle = 0` on this path:
matches ane-infer's "required for chaining" hypothesis being testable at the door —
zero may be fine for a single-procedure chain, or may be the NEXT gate after 0x10.

Build gotcha (measured): probe MUST compile `-fobjc-arc` like `ane_bridge.m`;
MRC build frees the autoreleased model mid-flight (isa-garbage SIGSEGV at `+0x10`).

## 26A434 runtime confirmation vs ane-infer (MIT since 2026-10-02)

`ane_class_dump` (ANE_CLASS=_ANEInMemoryModel/_ANEChainingRequest) on this OS:
all handle accessors they name on macOS 26.3 exist here (`-programHandle`/
`-intermediateBufferHandle`/`-string_id`/`-state`, types `Q`); `_ANEChainingRequest`
9-ivar ObjC surface identical to the EXP-032 ane_dsc decode. Their framework-layer
`prepareChainingWithModel:` success story changes nothing at the raw door; their
`_ANEIOSurfaceOutputSets.objectWithstatsSurRef:outputBuffer:` factory finding is the
named cross-check if C-85 reaches an output-set gate.

## C-85 go-shape (collapses to one fill + one ladder)

`probe8_replay` (probe6b lineage, ABI-correct): args{0x10=live handle from
probe7_capture in the SAME process, 0x18=0, 0x20/0x28=0, 0x38∈{0,1}, rest 0}.
kr oracle per gate; poison-0xFACE rule per offset. Meter rule from OFFSET_MAP stands:
a bare chainingPrepare may be bookkeeping-only — engine-work claims need the SOC-NI9
per-eval counters (EXP-030/032 bands) before any EVAL-THROUGH-DOOR word is said.

## C-85 verdict — PARKED-WITH-NAMED-GAP (2026-10-23, probe8_replay)

`probe8_replay` (live in-process handle minted by its OWN mil compile in the same
process, stderr witness `live handle=6061 state=3`):

- **Ladder: 6/6 arms + cnt-loop 12/12, uniformly kr=0xE00002C2 BadArgument.**
  Arms N-zero / B-bogus / P0 / P1-can / P2-proc1 / F-full — the LIVE handle
  (`0x17ad`) behaves EXACTLY like the bogus one. Poison scalar returns unmodified
  (nothing written), oSz_back=64. `raw/p8_arms.jsonl`.
- **Cause located in disasm (not inferred):** `ANE_ProgramChainingPrepare_locked`
  prologue gate `ldr x8,[x0,#0x10]; ldr w8,[x8,#0x88]; cbz → fail(mov w9,#0x2c2)`
  (`raw/prep_locked.asm` 0x9370ea4-0x9370eac) fires BEFORE any args byte. The
  handle key-gate (`getProgramResource` → global process-list walk matching
  `ANEProcess+0xC0 == args+0x10`, `raw/get_program_resource.asm`) is never reached.
  Fresh type-1 direct-path client shows zero in `[[core+0x10]+0x88]`; sel-1 pre-arm
  (C-80) does not set it; the 11-entry direct-path table has no provable setter.
- **Meter witness:** enginemon over the probe8 lifetime — `DCS Floor ANE-DCS-BW`
  F1-only, zero F≥2 residency (EXP-022 idle signature), ANE L0/L1 pinned at 2GB/s
  floor; GPU/AGX bands active (the probe's own compile). Engine took ZERO work from
  all 18 door calls — consistent with pre-args rejection, rules out
  accepted-but-slow path. `raw/p8_meter.jsonl` (window = child lifetime 0.2 s).
- **Zero-residue witness:** structural ioreg snapshot (DirectPathClient sensor
  validated live: `hold 1 20` child `H1xANELoadBalancerDirectPathClient` visible
  under ANEDriverRoot while open); probe8 run while hold alive → post-run snapshot
  structurally identical, client count back to hold's own. `raw/p8_ioreg_witness.txt`.

**Named gap (replaces "blob grammar"):** client-state word
`[[ANEClientDeviceCore+0x10]+0x88]` — no known user-space selector sets it for the
direct-path client class. Whether a valid handle would pass the second (key) gate
is UNOBSERVABLE from user space: both branches return the same 0xE00002C2. The
kernel log distinguishes them (`"Could not find program for handle 0x%llx"` present
⇒ Gate-A passed, key failed; absent ⇒ died at Gate-A). sudo pack prepared:
`tools/ane_door_probe/sudo_verify.sh` (awaits human sudo terminal).

**Verdict: the EXP-035 raw-door chaining line is PARKED at Gate-A.** Struct map
stands (it maps the inner door); the direct-path client class cannot yet open the
outer one. Not closed as negative — the decider is one sudo run away, not more RE.

## Kernel-log decider RAN (2026-10-23 21:28 local, root probe8 pid 77007,
`raw/sudo_kernel_log_20261023T192852Z.txt`, 121 ANE-driver lines)

Subsystem `com.apple.driver.AppleH16ANEInterface` raised to level:debug (macOS 27
removed the legacy private_data config key — the old instruction was obsolete;
bare `log` in interactive zsh hits the shell builtin — script now uses
/usr/bin/log). Findings, each traceable to a line in the captured file:

1. **Gate-A CONFIRMED as the rejection site (by the right kind of absence).**
   `Could not find program for handle 0x%llx` is an `[ERROR]`-format string in the
   kext — error level always reaches the log — and it appears ZERO times. No
   chaining-path message of any kind appears across all 18 rejected calls. The key
   gate (getProgramResource walk) is provably NEVER REACHED: rejection is at or
   before the `[[core+0x10]+0x88]` prologue check, exactly as disasm predicted.
2. **Process-level program registration happens and is NOT sufficient.**
   `ANE_AddClientForProgram: Adding client … probe8_replay to programHandle:
   0x186d` — our own compile (via aned type-2 client, pid 957) registers our
   PROCESS against the program, and the kernel knows our handle — yet sel-2 on our
   type-1 CONNECT still rejects uniformly. So the Gate-A word is a per-client-
   instance property that process registration does not set. Sharpens the target.
3. **`ANE_ProgramDestroy: WARN: Process not found. ProgramHandle: 0x186d`** at
   teardown — the process↔handle keying that `getProgramResource` walks
   (`ANEProcess+0xC0`) is half-wired for self-compiled clients; same-key family
   evidence, recorded as a lead, NOT over-read (destroy ran after client cleanup).
4. Full cold-start chain visible (ANE power-on → FW init → program prepare →
   "Network doesn't require intermediate buffer" = the intermediateBufferHandle=0
   from CAPTURE.md §3, kernel-confirmed). Meter's zero-engine band + this log
   agree: everything ran, nothing chained.

**Next bounded step (no sudo): probe9_opentype** — the log shows the successful
load path rides aned's **type-2** connect (`newUserClient type=2`); our door has
only ever been opened type-1. Open type-2 (and the rest of 0–5) from our own
process and re-run the arm ladder: if the type-2 client class sets the Gate-A
word at open, the kr signature must change. Falsifiable in one run.

## probe9_opentype RAN (2026-10-23, `raw/p9_types.txt`) — open-type lane CLOSED

Open sweep from an unprivileged process: **only types {1,4} open** (kr=0); 0, 2,
3, 5, 8, 16 all `0xe00002c7` (kIOReturnNotPrivileged) — **aned's type-2 class is
NOT attainable by us without an entitlement**, so "just open like aned does" is
closed at the Mach-permission layer, not tested-and-failed at the door. Both
attainable types give the identical Gate-A signature (6/6 sel-2 `0xe00002c2`
incl. live handle; sel0 BadArgument with no struct = contract enforcement as
known; poison scalars untouched; zero residue). Type-forge is dead as a lane.

**Revised open lead (C-87 candidate):** the Gate-A word is per-client-instance
and something on the SUCCESSFUL path sets it during program registration
(`ANE_AddClientForProgram` runs on the aned connect, never on ours). Within the
11-entry direct-path table that leaves a door-side **program-register/prepare
selector** (sizes known from EXP-033 contracts, semantics unmapped for indices
2–10) as the only untested setter. Next bounded step: per-selector semantics
sweep with poison discipline on the remaining indices, watching for any kr
difference once the program is loaded in-process (load-then-sweep ordering,
probe8 plumbing reused). If none sets it: the direct-path door is CONFIRMED
load-blind, and the daemon-free chaining story redirects to the EXP-025 mailbox
lane — a clean, decision-forcing negative.
