# EXP-035 chaining-blob crack — C-82 home-base inventory (committed BEFORE any new probe)

Date 2026-10-23. Machines: studio Mac17,14 M5 Max (bda452aabd60bf26), mini Mac16,10 M4
(057b28dd036ddbe8), both 27.0.1/26A434. Question on the table: how is the 3152 B
`ANEProgramChainingPrepareArgs` (door selector 2) built, and can we build it ourselves?
Every item: **path → what it gives → caveats → verdict (REUSE / EXTEND / REPLACE)**.

## 1. Door probe suite — `tools/ane_door_probe/` (all ad-hoc signed, uid-501, zero residue)

| Item | Gives | Caveats | Verdict |
| --- | --- | --- | --- |
| `main.c` (3216 B) | class enumeration + benign props; entry point to service discovery | read-only, no selectors | REUSE (diagnostics only) |
| `probe2.c` (2721 B) | 70-type `IOServiceOpen` matrix — the {1,4} discovery | per-OS sweep; re-run after updates | REUSE (residue witness context) |
| `probe3_sb.c` (3170 B) | sandboxed-context sweep + enforcement witness (launchd container) | class identity not creator-diffed in sandbox arm | REUSE if C-84 needs sandbox parity |
| `probe4_grammar.c` (2850 B) | **the contract engine**: 11 decoded selector contracts, per-selector kr + returned-struct hex + µs timer | contracts hardcoded from 26A434 kext decode — re-decode after OS update | **EXTEND: base for probe8_replay (C-85)** |
| `probe5_devprops.c` (3241 B) | DeviceProperties read + sel-0 136 B hexdump + era arms | field map partial (one key match) | REUSE (control arm) |
| `probe6_chain.c` / `probe6b_chain.c` (1421/1578 B) | sel-2 3152 B send harness, word[0] ladder, sel-1 pre-arm control, 0xFACE poison scalar | ladder probed word[0] only — that IS the open gap | **EXTEND: base for probe8_replay; ladder superseded by C-83 offsets** |
| `roundtrip.c` (1720 B) | single-call IOConnectCallMethod smoke (sel 0x12 legacy — OUT OF TABLE on this door, historical) | superseded reading; keep for EXP-032 continuity | REUSE (smoke) |
| `whoami.c` (2270 B) | client-class attribution via IOUserClientCreator | — | REUSE (attribution witness) |
| `hold.c` (889 B) | hold connection open for ioreg capture | — | REUSE (witness) |

Registry truth: INSTR-154..163 (`tools/instruments.jsonl`), `sh tools/kb_pipeline.sh` gate 1/5 enforces.

## 2. Knowledge docs — `knowledge/ane/`

| Item | Gives | Caveats | Verdict |
| --- | --- | --- | --- |
| `13-pulse-map.md` | full virtio-era `_ANEVirtualClient` selector table 0x00–0x1e (eval = 0x13/16 B; weight trio 0x1c–0x1e) + **VM-guest caveat: zero virtio instances on-host** | do not confuse with the live door table | REUSE (grammar contrast only) |
| `14-door-map.md` + EXP-034 addendum | **current door truth**: 11-entry `_sANEDriverDirectPathClientMethods` @0xfffffe00080a1e00, per-selector live verdicts, µs costs, size(-era) ruling, corrected labels | handler semantics named from callee symbols, not source | REUSE (campaign baseline) |
| `12-perfstats-and-entitlements.md` §Q5 addendum | **C-64 SIP-session prep pack**: lldb attach-to-aned flow, breakpoints at `driverMaskForANEFMask:` @0x10001ced8 / kernel handoff @0x10001f290, poison-0xFACE-first rule, ioreporter-absent substitute, "test attach FIRST" checklist | C-64 was written for the perf-stats thread; same mechanics apply to chaining capture; hardened attach UNTESTED on 26A434 | REUSE (C-84 fallback pack) |
| `11-platform-naming.md`, `02-private-api.md`, `07-private-api-verified.md` | naming discipline (getANEDeviceProperties ANEDriver-first @0x1a20a619c / H11ANEIn fallback @0x1a20a61f8), private-API surface inventory | 07 rows predate the door era for IOKit bits | REUSE (naming/lookup) |
| `03-program-format-and-compile.md`, `04-runtime-and-memory.md` | program compile path + IOSurface/shared-mem grammar (feeds inputs/outputs field decode) | — | REUSE |
| `ARCHIVE-MAP.md`, `SOURCES.md`, `SPINE.md` | next-doc-number rule (15 is free — 14, 16 exist); source attribution rows incl. MDAITER-ANE, Phrack #72, ER-10 | — | REUSE (landing rules) |

## 3. Corpus: extracted kernel + shared cache (already on disk — no re-acquisition)

| Item | Gives | Caveats | Verdict |
| --- | --- | --- | --- |
| `results/EXP-033-door-map/raw/kext/kexts/com.apple.driver.AppleH16ANEInterface` (3,029,440 B Mach-O arm64e, 26A434 exact, kextstat-matched 10.19.2) | **the ground truth for C-83**: disassemble `ANEClientDeviceCore::ANE_ProgramChainingPrepare(ANEProgramChainingPrepareArgs*, …)` for the offset map | extractable slice only of the kernelcache; regenerate `ipsw download ipsw --macos --version 27.0.1 --kernel --extract-device Mac17,14` (~6 min) | **REUSE — primary C-83 input** |
| `…/kext/kexts/com.apple.driver.AppleANELoadBalancer` (49,296 B) | load-balancer class helpers, secondary callee corpus | small — callee may live in H16 kext | REUSE (secondary) |
| `…/kext/selector_matrix.tsv`, `deep_sel*.asm`, `raw_sel*.asm` | decoded 40 B entries + prior disasm windows (deep_sel1.asm already shows the `programChainingPrepare` log strings + the `bl ANEClientDeviceCore::ANE_ProgramChainingPrepare` site) | windows were bounded; C-83 needs the callee body, which is NOT yet extracted | EXTEND (extract the function) |
| `…/kext/PROVENANCE.md`, `kernelcache.sha256` | provenance + regenerate command | — | REUSE |
| `results/EXP-032-pulse-map/raw/ane_dsc.asm.gz` (108,871 lines, zcat; 26A434 dyld shared-cache extraction of AppleNeuralEngine) | **wire-format Rosetta stone**: `_ANEChainingRequest` @20321 (`initWithInputs:outputs:lbInputSymbolId:lbOutputSymbolId:procedureIndex:signalEvents:transactionHandle:fwEnqueueDelay:memoryPoolId:`), `encodeWithCoder:` key set (inputs/outputs/loopbackInputs/loopbackOutputs/procedureIndex/signalEvents/transactionHandle/fwEnqueueDelay/memoryPoolId), `_ANEProcedureData` (procedureSymbol/weightArray/mutableWeightsBufferID) @11654+, 22 `IOConnectCallMethod` call sites | extraction is `ipsw dyld disass`-style; data segments/strings only partially annotated — ivar layout NOT in text; may need `ipsw dyld swift`/class-dump pass on the same image | **REUSE — primary C-83(e)/C-84 input** |

## 4. Measurement + consumer machinery

| Item | Gives | Caveats | Verdict |
| --- | --- | --- | --- |
| `tools/enginemon/enginemon.c` (+README) | the meter: PMP0 `DCS BW` residency, M5 working counter = PMP0 SOC-NI9 "ANEXL U", per-eval calibration bands (0.488–0.503 parity kernel / 1.00–1.06 field / 2.889–2.915 CoreML, ±1.5–3%); `enginemon -- <cmd>` windowing | ambient ~30 MB/s DCS traffic confounds attribution for bookkeeping calls — engine-side work claims need eval-shaped bursts | REUSE (C-85 meter) |
| `results/EXP-025-ane-gpu-sync/harness/` (`ane_sync_harness.m`, `ane_surface_probe.m`, `ane_class_dump.m`, `ane_reqmethods.m`, `.d` dtrace scripts) | `IOSurfaceSharedEvent`/`_ANESharedEvents` mailbox measured (~62 µs hop) = the `signalEvents` field's purpose; class-dump + request-method dtrace tooling predates the door era | M5-era driver gave size=0 stats on _ANEInMemory (EXP-029) — unrelated to mailbox fds | REUSE (field-semantics evidence + C-84 tooling pattern: `ane_class_dump.m` is the right starting shape for probing `_ANEChainingRequest` at runtime) |
| `results/EXP-032-pulse-map/harness/mil_battery.m` + 20-case corpus, `run_battery.py` | scripted `_ANEInMemory` compile path (fresh process per case) — the template for C-84's "compile once, reuse program" probe | accept/reject taxonomy known (12/8, opaque errors) | EXTEND (compile-side harness) |
| ncm-run workspace consumer artifacts (ANECtx.swift `_ANEInMemory` path, `ANETrain.swift`, ctx weights; `ncm0 anectx --field` = 133 µs canonical baseline, bit-identical CPU parity 0/15,800 owner-ratified band) | the program + canonical logits the door eval must match (C-85 parity target) | consumer consumes handoff artifacts only — no door RE inside ncm-run (owner rule) | REUSE (parity oracle) |
| ipsw CLI (installed, 3.1.735) | `ipsw macho disass` / `dyld disass` / route-A kernelcache regeneration | — | REUSE |

## 5. Gap list (what this sweep does NOT already have)

1. **No disassembly of the `ANE_ProgramChainingPrepare` callee body** — only the caller
   window (`deep_sel1.asm:325` bl site). C-83 produces it.
2. **No runtime capture of a framework-built 3152 B blob** — `ane_class_dump.m` shows the
   pattern but never dumped chaining objects. C-84 produces it.
3. **ivar layout of `_ANEChainingRequest`/`_ANEProcedureData`** not extracted from the
   shared cache (need a `ipsw dyld info`/objc metadata pass, same image, offline). C-83 add-on.
4. lldb attach to hardened `aned` on 26A434 **untested** (C-64 checklist item 1 — only if
   C-84 in-process route dies; not executed this campaign).
5. No published-grammar prior-art row for `ANEProgramChainingPrepareArgs` yet — dated
   search logged before any novelty claim (C-83 first act).

## Gate dependency map

- C-83 ← §3 kext Mach-O + deep_sel windows + ane_dsc `_ANEChainingRequest` block; meter not needed (static).
- C-84 ← §2 doc 12 Q5 pack (fallback), §4 `ane_class_dump.m` pattern + mil_battery compile template + ncm-run program artifact; §4 enginemon optional.
- C-85 ← §1 probe4/probe6 lineage (probe8_replay), §4 enginemon meter + ncm-run parity oracle (133 µs baseline, 0/15,800 band).
