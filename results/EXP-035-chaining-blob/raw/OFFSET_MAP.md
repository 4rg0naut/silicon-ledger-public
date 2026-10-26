# EXP-035 C-83 — ANEProgramChainingPrepareArgs offset map (26A434, AppleH16ANEInterface 10.19.2)

Method: `ipsw macho disass` on the on-disk extracted kext (results/EXP-033-door-map/raw/kext/kexts/
com.apple.driver.AppleH16ANEInterface, 26A434 exact, kextstat-matched) + a2s symbol cache.
Raw extracts in this dir: `prep_locked.asm` (ANE_ProgramChainingPrepare + _locked + siblings),
`chaining_prepare.asm` (ANEDataChainingRequest::chainingPrepare full body).
Prior art searched FIRST, dated 2026-10-23: "ANEProgramChainingPrepareArgs" and
"ANEDriver externalMethod selector chaining prepare args struct" → **both zero hits** —
no published grammar for this struct; ours is the first measured map (home base read first:
docs 13/14 confirm only contract sizes were known).

## Chain (kernel truth, addresses = this build)

sel-2 thunk @0xfffffe00092c9764 (PAC `braa` trampoline; 40-B table entry re-verified raw:
structIn 3152 = 0xC50, structOut 64, scalarOut 1) → … →
`ANEClientDeviceCore::ANE_ProgramChainingPrepare` @0xfffffe0009370df4 (lock wrap) →
`ANE_ProgramChainingPrepare_locked` @0xfffffe0009370e84 →
`ANEDriver::getProgramResource(u64, shared_ptr<ANEProcess>*, bool)` →
`ANEDataChainingRequest::create(ANEHWInterface*, ANEScheduler*, ANEClientDeviceCore*)` →
`ANEDataChainingRequest::chainingPrepare(ANEProgramChainingPrepareArgs&)` @0xfffffe00093694c0 →
`ANEScheduler::submitRequest(shared_ptr<ANERequest>)`.

**Format verdict: PLAIN FIXED-LAYOUT STRUCT.** Zero `OSUnserialize`/plist references in the
whole consumption chain; every gate is a raw offset read/compare. (C-80's "blob grammar /
OSValueObject deserializer" framing is superseded — the `cmp w8,#3` device-type switch we
called part of the payload path is the GLOBAL `_fAneSubType` jump table, not an args field;
the OSValueObject<ANEClientDevice*> symbols were adjacent-window noise from the bounded
EXP-033 extract. Dated correction for doc 14 Q5 addendum item 3.)

> **Dated correction 2026-10-23 (evening, probe8_replay C-85, `raw/p8_arms.jsonl`):**
> "Handle table is GLOBAL in ANEDriver … a handle created by the framework path is
> resolvable from the raw door" — half right, and measurably insufficient. Lookup
> (`getProgramResource` → `getProgramResourceWeakPtr`, raw/get_program_resource.asm)
> walks a GLOBAL per-ANEDriver process list (`ANEDriver+0x778`, element `+0x18` =
> ANEProcess weak) matching `ANEProcess+0xC0 == args+0x10` (bool arg false = plain
> key match; true pre-filters on `[lock+0x1f20]`, an owner-token gate). BUT nothing
> reads args at all unless the FIRST gate passes: `[[this+0x10]+0x88] != 0` —
> per-DEVICE-CORE client state (lock, count, or readiness flag) checked BEFORE any
> payload byte (`prep_locked.asm:0x9370ea4-0x9370eac`, local os_log fmt then
> `mov w9,#0x2c2`). A fresh type-1 direct-path client shows zero there, and the
> C-80-measured sel-1 pre-arm does not set it — so every probe8 arm (including the
> LIVE in-process handle 0x174d) dies at the same pre-args branch with identical kr,
> exactly as observed (6/6 arms uniform 0xe00002c2). Named gap moves from "blob
> grammar" to: **client-state word `[[core+0x10]+0x88]` — the 11-entry direct-path
> table offers no selector that provably sets it; whether a valid handle would pass
> the second (key) gate is UNOBSERVABLE from user space without kernel logs
> (sudo log stream pack prepared).** Struct-offset map above stands (verified from
> disasm); it maps the inner door the current client class cannot yet open.

## User-area offsets (bytes 0x00–0xC50 = what the door copies in)

| Offset | Width | Evidence | Meaning |
| --- | --- | --- | --- |
| 0x00 | ? | never read before copy-forward | padding / size word (kernel-side) |
| 0x08 | ? | not read in this chain | unused by prepare path (likely used by the sel-4 3104B sibling) |
| **0x10** | **u64** | `ldr x1,[x19,#0x10]` → `getProgramResource`; log `"Could not find program for handle 0x%llx"`; strings `ANEClientProgramHandle`, `lookupClientProgramWithHandle`, `Found client (%s) for program handle 0x%llx, is base model: %d` | **ANEClientProgramHandle — THE first gate.** Our zeroed probes = handle 0 → not found → BadArgument 0xE00002C2 (constant verified @0x9370fe8/1000/107c). Handle table is GLOBAL in ANEDriver (client resolved FROM the handle) — a handle created by the framework path (our in-process anectx loads, or aned-loaded programs) is resolvable from the raw door. |
| 0x18 | u32 | `cmp w8,#2` special-case; `ldr w9,[x9,#0x1fb4]` (program record) `cmp w8,w9; b.hs → "Out of range procedure index"` | **procedure index** (valid: < program's procedure count; <2 takes a fast path) |
| 0x20 | u64 | `ldr x9,[x20,#0x20]` → stored request+0xF0 | copied into request; paired with +0x28 → transactionHandle (matches `_ANEChainingRequest.transactionHandle`) |
| 0x28 | u32 | `ldr w9,[x20,#0x28]` → stored request+0xE8 | request copy-through (fwEnqueueDelay or memoryPoolId class) |
| 0x38 | u32 | `cmp w8,#0x100; b.hi → fail` (`"Out of range procedure count"` family) | buffer/procedure-set **count, must be ≤ 256** |
| 0x40–0xC50 | — | no reads in prepare chain within extract window | buffers arrive separately (sCSneDataChainingBufferDescriptor / chainingBufferSetInfo build path); first-pass submit needs none of it armed beyond 0x38=small |

Kernel-side tail (> 0xC50, NOT user-supplied — read from the larger 14.7 KB kernel struct the
handler allocates; door-copied 3152 B land at 0x00): `0x3040` u32 gate `>= 0x101` selects a
rare branch (firmware TD table variant; zero → common path), `0x3950` u32 `≤ 0xc`.
**Zeroed tail = pass** on both: the kernel-init region works FOR us.

## What C-85 must actually do (gap collapses to one number)

1. `probe8_replay`: args{0x10 = real ANEClientProgramHandle, 0x18 = 0 (first procedure),
   0x20/0x28 = 0, 0x38 = 0…1}, everything else zero. Expect to pass handle gate → next gate
   or success; kr transitions observable per gate (BadArgument → BadArgument-at-different-site
   distinguishable via a second field sweep, or success).
2. Handle source, in priority order: (a) C-84 in-process capture — our own process's anectx
   `_ANEInMemory` load registers a handle in the SAME global table → dump it from the
   framework object graph; (b) scan small u64 window around values seen in tmpDir/log
   artifacts with the door itself (bounded, zero-residue, kr oracle per call — this is a
   named-field probe, not blind fuzz).
3. Meter stays honest: eval-shaped submit needed for SOC-NI9 attribution; a bare
   chainingPrepare may be bookkeeping-only (no engine work claimed until outputs + meter move).

## Repro

```sh
cd results/EXP-033-door-map/raw/kext/kexts
ipsw macho disass com.apple.driver.AppleH16ANEInterface --vaddr 0xfffffe0009370df4 -c 1400 \
  --cache com.apple.driver.AppleH16ANEInterface.a2s --no-color > …/prep_locked.asm
ipsw macho disass com.apple.driver.AppleH16ANEInterface --vaddr 0xfffffe00093694c0 -c 900 \
  --cache com.apple.driver.AppleH16ANEInterface.a2s --no-color > …/chaining_prepare.asm
strings -a com.apple.driver.AppleH16ANEInterface | grep -iE "Out of range|ClientProgramHandle|chainingBufferSet"
```
