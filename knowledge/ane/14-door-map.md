# 14 — The door map: who can open the ANE kernel door, and from where

Document number rationale: fills the next gap in this series (13 = pulse map; 16 is an
imported standalone line and stays what it is). Campaign: **EXP-033 door-map**
(2026-10-23, studio M5 Max + mini M4). Evidence root: `results/EXP-033-door-map/`.
Predecessor: `13-pulse-map.md` (EXP-032 C-69 opened the first door probe from an
unsandboxed shell only and left sandbox behaviour as its own caveat — this campaign
closes it, plus the fleet dimension). Prior-art anchor: BlackStorm ER-10
(Alexandre Borges, 2026-10-06) published first *openability* of `H1xANELoadBalancer`
at types 1+4 from a sandboxed **iOS** app in an attack-surface sweep
(`results/EXP-032-pulse-map/raw/er10_blackstorm_extract.txt`); this doc is the macOS
characterization with client-class context and the cross-silicon fleet result.

## Q1 — Is the door machine-specific? **[V]**

Same binary family (`tools/ane_door_probe/probe2.c`, 70-value open-type set) run on
both fleet Macs, macOS 27.0.1 (26A434):

- **M5 Max studio** (`bda452aabd60bf26`): opens `ANEDriverRoot` at exactly types
  **1 and 4** (both `ANEDriver` and `H1xANELoadBalancer` matchings hit the same
  instance); all other 68 types `kIOReturnUnsupported` (0xe00002c7).
- **M4 mini** (`057b28dd036ddbe8`): **identical result** — same two types, same
  error code everywhere else, same service instance names.

Zero residue both runs (sorted `ioreg IOUserClientCreator` diff before/after,
`raw/door_*_unsandboxed.txt` + witnesses). The `{1,4}` pair also matches BlackStorm's
iOS numbers — cross-platform, cross-silicon stable driver policy.

## Q2 — Does the app sandbox kill it? **[V] — no**

`tools/ane_door_probe/probe3_sb.c`: same 70-type sweep from inside a sandboxed
ad-hoc-signed `.app` (`com.apple.security.app-sandbox` = true, launched via `open -W`
so launchd applies the container). Enforcement witnessed in-process:
`sandbox_check(getpid(),NULL,0)=1` (observed semantics: 1 = sandboxed), `HOME` =
`~/Library/Containers/uk.4rg0naut.doorprobe/Data`, writes to `/Users/<user>` and
`/tmp` return EPERM. Result on **both** machines: types **1 and 4 still OPEN**
(kr=0x0), all others unchanged `0xe00002c7`.

A third-party App-Sandbox-style process can hold a direct-path ANE user client with
no entitlements at all. What remains unprobed: Mac App Store distribution profile /
hardened-runtime layering, and the selector grammar (below in later sections).

## Matrix

`raw/door_matrix.tsv` — 4 rows: {studio, mini} x {unsandboxed, sandboxed}, identical
verdicts; raw captures alongside.

## Q3 — Is the kext really offline-unreachable? **[V] — no (EXP-032 verdict superseded)**

`ipsw download ipsw --macos --version 27.0.1 --kernel --extract-device Mac17,14`
pulls the kernelcache straight from the UniversalMac_27.0.1_26A434 restore — partial
remote extract, no full-IPSW download, ~6 min. The cache is board-set
`Mac17,6/7/8/9/14/15/16` (covers this Mac17,14) and its kext versions match the live
box exactly: `AppleH16ANEInterface 10.19.2 == kextstat 10.19.2`,
`AppleT6050ANEHAL 10.19.0 == 10.19.0`. Route A, zero drift, no sudo, no restore
image mounted. The EXP-032 "NOT-REACHABLE on SPTM-era OS" verdict was true only for
*on-box file* extraction; the update feed defeats it. (Method prior art: macOS
restore IPSWs are publicly indexed [mrmacintosh DB, searched 2026-10-23]; the
corpus-side workflow ER-10 demonstrated on iOS. Our delta: exact-build remote
partial extract + kext version equality proof, applied to the ANE door.)

## Q4 — What does the direct-path selector grammar say? **[V] — mapped, 11 entries**

Kernel truth (`com.apple.driver.AppleH16ANEInterface`, extracted kext):
`H1xANELoadBalancerDirectPathClient::externalMethod` is
`H11ANEInDirectPathClient::externalMethod` @0xfffffe00092cb97c, dispatching through
`_sANEDriverDirectPathClientMethods` @0xfffffe00080a1e00 — **11 entries** (count
`w4=0xb`), 40 B/entry: PAC func ptr, flags, structInSize, scalar counts,
structOutSize. Per-entry contracts decode cleanly (sel0 136B↔136B; sel2 3152B→64B+1
scalar; sel6 2088B; …). Live verdicts with exact decoded contracts
(`tools/ane_door_probe/probe4_grammar.c`):

- **sel 0: SUCCESS** — 136-byte struct roundtrip; bytes back all-zero except
  `u64@88 = 1`, `u64@112 = 4` (capability fields, uninterpreted — first values ever
  read off this door by third-party code).
- **sel 1: SUCCESS** zero-arg; kernel callees `retainSharedEvents` +
  `ANEClientDeviceCore::setDataChainingClient` + `ANE_ProgramChainingPrepare`.
- **sel 6: kIOReturnNotReady** — contract accepted, handler state machine reached.
- sels 2/3/4/5/7/8/9/10: `BadArgument` at handler level (zeroed payloads fail
  internal validation) — contracts correct, payloads need real tokens.
- **sel 11 (control): BadArgument** — first selector beyond the 11-entry table.
  This *supersedes* the EXP-032 reading of the type-1 probe result (selector 0x12
  was out of table bound, not "wrong table"): the door answer is now explained
  kernel-side.

Verdict line: **the reachable door exposes the chaining/lifecycle grammar
(`ANE_ProgramChainingPrepare` trio 2/3/4 + init/close/died/free), NOT eval-submit —
program submit stays inside aned.** Eval-submit-class candidate = sel 2 (chaining
prepare), confidence medium; no eval selector is producible from an unprivileged
type-1/4 client. Full per-row matrix: `raw/kext/selector_matrix.tsv`; handler
disassembly `raw/kext/deep_sel*.asm`; live captures `raw/kext/live_*.txt`.
Meter note: ambient ANE DCS traffic (~30 MB/s, some background client) confounds
engine-counter isolation for bookkeeping calls — verdicts rest on kr codes +
zero-residue witnesses, stated honestly (no probe-attributable engine work claimed).

**Prior art, logged 2026-10-23 (C-77 audit):** **Phrack #72, "Mapping IOKit
Methods Exposed to User Space on macOS", Karol Mazurek (AFINE), 2025-08-19** —
the method-mapping methodology is published with ANE as its worked example:
`H11ANEIn::newUserClient` type branch (type 1 → `H11ANEInDirectPathClient`),
`H11ANEInUserClient::sMethods` (0x32 entries) and
`H11ANEInDirectPathClient::sMethods` locations, the 0x28 dispatch-entry stride,
per-selector size extraction from the table, selector-bounds checking, and a
successful live call `IOVerify -n H11ANEIn -t 1 -y "0:[0,96,0,96]"`
(Sequoia-era). Project Zero, "Oops, I missed it again!" (2020-11-13) shows
`sMethods[selector]` dispatch on the same class family. OUR DELTAS: the
**H1xANELoadBalancerDirectPathClient** class behind the `ANEDriver`/
`ANEDriverRoot` door — a different service from H11ANEIn (their selector 0
takes 96 B; ours takes 136 B) — mapped completely for M5/26A434 (11 entries,
live per-selector verdicts incl. sel 6 = `kIOReturnNotReady`), µs latencies,
and the EXP-032 0x12 out-of-bound re-read of our own earlier error. The
novelty claim is the load-balancer door on this generation, not the mapping
method.

## Q5 — What does the door cost? **[V] (C-76, parked-with-measurement)**

Per-call round-trip latency measured in-process (`mach_absolute_time`) across three
runs: successful dispatches **sel 0 = 3.5–4.1 µs, sel 1 = 3.2–7.1 µs**; error paths
0.6–5.2 µs. Against reference points (maderix ~95 µs dispatch, aned XPC-mediated
framework eval hop at the ~100s-µs scale, EXP-025 class), **the raw kernel door is
~20× cheaper than the daemon hop** — the cost of going direct is payload forging,
not dispatch. Submit attempt on the identified candidate (sel 2, 3152B/64B+1
contract) returned `BadArgument` at handler payload validation: the client token
forge (`ANEClientInfo::create(task*,uint,bool,bool)`, guest-path
`_ANEProcedureData`/`_ANEWeight` serializers) is the next real step, named not
guessed. Bounded single-session attempt, parked per criterion —
`c76_directpath_parked.json`. Weight-mutation trio (virtio 0x1c–0x1e) has **no
counterpart** in this table: door-side weight mutation NOT established.

## Claims

```jsonl
{"id":"MEASURE-162","claim":"The ANEDriverRoot kernel door's payload is era-keyed, not entitlement-gated: DeviceProperties on ANEDriverRoot is readable unprivileged on M5 Max studio and M4 mini (27.0.1/26A434) and carries exactly one key, ANEDevicePropertyNumANEs=1 — matching u32@0x54=1 in the successful sel-0 136B response (the only field-key match found); remaining non-zero words u64@0x50=4 GiB (both boxes) and u64@0x60=16 GiB studio vs 10 GiB mini are machine-dependent with Metal recommendedMaxWorkingSetSize (107.52/11.84 GiB) measured and REFUTED as source; probe4's published 'u64@88=1/u64@112=4' labels were mislabeled scalar reads of u32@0x54/u32@0x64, and sel-6's live code is kIOReturnNotFound (0xe00002f0), not kIOReturnNotReady (0xe00002d8) as EXP-033 prose said. Refutation arm vs mdaiter/ane (pushed 2026-02-01): their exact 0x68 struct send on the current type-1 door returns kIOReturnBadArgument (0xe00002c2) on both boxes (also with their int32@0x18=-1 variant) while the correct-era 0x88/0x88 send succeeds kr=0x0 in the same capture — their NotFound-and-blame-entitlement belongs to the H11-era service their header targets, whose selector-0 takes 96 B; door openability without com.apple.ane.iokit-user-access stands confirmed (agreement).","kind":"measurement","confidence":"measured","source":"results/EXP-034-full-access/ (c79_devprops.json, raw/p5_studio_ANEDriver.txt, raw/p5_mini_ANEDriver.txt, raw/ioreg_zero_residue_witness.txt)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","iokit","direct-path","device-properties","prior-art","reverse-engineering"],"entities":["ANEDriverRoot","DeviceProperties","ANEDevicePropertyNumANEs","mdaiter/ane","H11ANEIn","com.apple.ane.iokit-user-access","recommendedMaxWorkingSetSize","kIOReturnNotFound","kIOReturnBadArgument"],"evidence":"full property-tree XML + sel-0 hexdumps both boxes (files differ ONLY in the u64@0x60 line); per-run zero-residue witnesses studio 707/707 md5-stable, mini 448/448 md5-stable; dsc instruction addresses for the ANEDriver-first/H11ANEIn-fallback service query verified in EXP-032 raw/ane_dsc.asm lines 3182/3207","caveat":"field-key map partial: one exact match only; 4/16/10 GiB trio named by numeric pattern, no source pinned; 0x68 arm covers struct size + two documented variants on the current door only, H11ANEIn-era selector-0 not reproduced from user space; one OS build","contested":false}
{"id":"MEASURE-163","claim":"Hot submit through the direct-path chaining door is blocked at a named upstream grammar, not at token size: on M5 Max the sel-2 3152B ANEProgramChainingPrepareArgs payload is rejected uniformly kIOReturnBadArgument (0xe00002c2, oSz_back=64, poison scalar 0xface0000face returned unmodified) across a 12-candidate word[0] handle ladder (0x0..0xffff incl. pid-derived values), and a successful zero-arg sel-1 pre-arm (kr=0x0, arming setDataChainingClient/ANE_ProgramChainingPrepare) on the same connection does NOT change the outcome — so the first rejection gate lies upstream of chaining-client/handle state, in the blob grammar itself whose validation is delegated to the callee deserializer, whose first visible checks are a device-type switch (cmp w8,#3) and OSValueObject<ANEClientDevice*>::init() with no direct compare of any input word in the dump window (EXP-033 deep_sel2.asm). Verdict PARKED-WITH-NAMED-GAP: the gap is the user-mode serializer that embeds serialized ANEClientDevice value-object references into the 3152B blob, not a scalar field; zero-residue witnesses per run; no probe-attributable ANE engine work claimed; mini not attempted (studio-only spike per budget).","kind":"measurement","confidence":"measured","source":"results/EXP-034-full-access/ (c80_chaining_parked.json, raw/p6_chain_studio.txt, raw/p6b_prearm_studio.txt)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","iokit","direct-path","chaining","reverse-engineering"],"entities":["ANE_ProgramChainingPrepare","ANEProgramChainingPrepareArgs","OSValueObject","ANEClientDevice","setDataChainingClient","H1xANELoadBalancerDirectPathClient"],"evidence":"12-candidate ladder identical kr pre/post pre-arm (p6 vs p6b captures differ only in word0=0xb4fe vs 0xbad4); disasm window shows no scalar compare; zero-residue witness studio 707/707 md5-stable across both probes","caveat":"ladder probes word[0] only — a valid blob could fail on any of the remaining 3145 bytes, which is precisely why the verdict names the serializer grammar not a field; handler semantics from callee symbols, not source; one OS build","contested":false}
{"id":"MEASURE-159","claim":"The EXP-032 kext NOT-REACHABLE verdict is superseded: the macOS 27.0.1 (26A434) kernelcache is obtainable offline without sudo or mounted restore via 'ipsw download ipsw --macos --version 27.0.1 --kernel --extract-device Mac17,14' (remote partial extract of UniversalMac_27.0.1_26A434_Restore.ipsw, ~6 min, 123 MB Mach-O arm64e, board set Mac17,6_7_8_9_14_15_16 covering this Mac17,14), and kext versions match the live box exactly — ipsw kernel kexts reports com.apple.driver.AppleH16ANEInterface 10.19.2 == kextstat 10.19.2 and AppleT6050ANEHAL 10.19.0 == 10.19.0; zero version drift, route A, no proxy corpus needed (iOS IPSW corpus remains a documented alternative per BlackStorm ER-10's workflow).","kind":"measurement","confidence":"measured","source":"results/EXP-033-door-map/raw/kext/ (PROVENANCE.md, kernelcache.sha256; blob gitignored, regenerate via recorded command)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","kernelcache","tooling","ipsw","reverse-engineering"],"entities":["ipsw","UniversalMac_27.0.1_26A434_Restore.ipsw","AppleH16ANEInterface","AppleT6050ANEHAL","Mac17,14"],"evidence":"Mach-O file magic verified; kextlist version equality against kextstat; 218 symbols resolved via ipsw kernel cpp on extracted cache","caveat":"one OS build; extraction depends on Apple's update CDN keeping the signed restore available; mrmacintosh DB confirms macOS restores are publicly indexed (searched 2026-10-23)","contested":false}
{"id":"MEASURE-160","claim":"The unprivileged direct-path ANE door grammar is fully mapped on macOS 27.0.1/26A434: H1xANELoadBalancerDirectPathClient (IOServiceOpen ANEDriver type 1) dispatches via H11ANEInDirectPathClient::externalMethod @0xfffffe00092cb97c through _sANEDriverDirectPathClientMethods @0xfffffe00080a1e00, 11 entries x 40 B (PAC func ptr + flags + structIn/scalarIn/structOut/scalarOut contract fields); with decoded exact contracts (tools/ane_door_probe/probe4_grammar.c) sel 0 SUCCEEDS (136B struct roundtrip returning u64@88=1 and u64@112=4, capability fields uninterpreted) and sel 1 SUCCEEDS zero-arg (kernel callees retainSharedEvents + ANEClientDeviceCore::setDataChainingClient + ANE_ProgramChainingPrepare), sel 6 returns kIOReturnNotReady (handler state machine reached), sels 2/3/4/5/7/8/9/10 BadArgument at handler-level payload validation (contracts pass the table bound), and selector 11 is BadArgument as first out-of-table index — which supersedes the EXP-032 interpretation of the 0x12 probe (out-of-bound, not wrong-table); the reachable door exposes the chaining/lifecycle grammar (ANE_ProgramChainingPrepare argument trio 2/3/4), NOT eval-submit: third-party direct-path program submit candidate = sel 2 (3152B in / 64B out + 1 scalar out), confidence medium; program eval submit remains aned-mediated. Zero residue on every ioreg witness; engine-counter isolation confounded by ambient ANE DCS traffic (~30 MB/s background) so no engine-side work is claimed from these calls.","kind":"measurement","confidence":"measured","source":"results/EXP-033-door-map/raw/kext/ (selector_matrix.tsv, deep_sel*.asm, live_grammar_verdicts.txt, live_grammar_flat416.txt, PROVENANCE.md, kexts/com.apple.driver.AppleH16ANEInterface)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","iokit","direct-path","selector-grammar","reverse-engineering","chaining"],"entities":["H1xANELoadBalancerDirectPathClient","H11ANEInDirectPathClient","_sANEDriverDirectPathClientMethods","ANE_ProgramChainingPrepare","setDataChainingClient","ANEDriver","AppleH16ANEInterface","kIOReturnNotReady","ipsw"],"evidence":"table bound w4=0xb in disassembly; entry stride 0x28 measured via PAC-pointer scan; per-selector live kr codes (live_grammar_verdicts.txt); ioreg IOUserClientCreator zero-residue witnesses before/after every probe run","caveat":"handler semantics named from callee symbols, not source; capability fields uninterpreted; chaining-prepare payload tokens (client id etc.) not yet forged — sel 2 candidate unproven as submit path; type-4 client (aned-mediated) not cross-probed in this run","contested":false}
{"id":"MEASURE-161","claim":"Raw ANE kernel-door method dispatch is ~20x cheaper than the daemon hop: in-process round-trip latency for direct-path user-client calls on the M5 Max (open type 1, tools/ane_door_probe/probe4_grammar.c, mach_absolute_time, 3 runs) is 3.5-4.1 us for the successful sel-0 136B struct roundtrip and 3.2-7.1 us for the successful zero-arg sel 1, with handler-error paths 0.6-5.2 us — against maderix's ~95 us documented dispatch and the aned-XPC-mediated framework eval hop at the ~100s-of-us scale (EXP-025 class); the door itself is not the cost of going direct, payload forging is (sel-2 chaining-prepare contract accepted at table level, rejected at handler payload validation: kIOReturnBadArgument with zeroed args — client token construction via ANEClientInfo::_create/guest-path _ANEProcedureData serializers is the named next step); the virtio weight-mutation selectors 0x1c-0x1e have no counterpart among the 11 direct-path entries, so door-side weight mutation is NOT established.","kind":"measurement","confidence":"measured","source":"results/EXP-033-door-map/c76_directpath_parked.json + raw/kext/live_grammar_verdicts.txt","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","direct-path","latency","iokit","observability"],"entities":["probe4_grammar","ANEDriver","H1xANELoadBalancerDirectPathClient","ANEClientInfo","maderix","aned"],"evidence":"per-selector lat_us stamped across 3 x 12-call runs in live_grammar_verdicts.txt; dispatch contract table in selector_matrix.tsv","caveat":"dispatch latency, not end-to-end program submit (submit payload unforgeable this round — parked); latency excludes IOSurface setup and engine wait; ambient engine load does not affect kernel-round-trip comparison","contested":false}
{"id":"MEASURE-158","claim":"The unprivileged ANE kernel door is stable across the fleet AND survives the macOS app sandbox: the same 70-type IOServiceOpen sweep (tools/ane_door_probe/probe2.c) on M5 Max studio (bda452aabd60bf26) and M4 mini (057b28dd036ddbe8), both 27.0.1/26A434, opens service ANEDriverRoot (matched by both ANEDriver and H1xANELoadBalancer classes) at exactly open types 1 and 4 with all 68 other types kIOReturnUnsupported (0xe00002c7), zero residue (sorted ioreg IOUserClientCreator before/after diffs); re-run from inside an ad-hoc app-sandbox (probe3_sb.c, com.apple.security.app-sandbox=true via embedded entitlement, launchd-spawned, sandbox_check=1 observed with container HOME redirect and EPERM on real-home and /tmp writes) yields the IDENTICAL {1,4} pair on both machines — no iokit-user-client entitlement is needed for the direct-path client class even under sandbox; corroborates BlackStorm ER-10's iOS {1,4} finding into a cross-platform stable-policy verdict.","kind":"measurement","confidence":"measured","source":"results/EXP-033-door-map/raw/ (door_studio_unsandboxed.txt, door_studio_sandboxed.txt, door_mini_unsandboxed.txt, door_mini_sandboxed.txt, door_matrix.tsv)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","iokit","direct-path","sandbox","fleet","observability"],"entities":["ANEDriver","ANEDriverRoot","H1xANELoadBalancer","H1xANELoadBalancerDirectPathClient","probe3_sb","com.apple.security.app-sandbox","IOServiceOpen","kIOReturnUnsupported"],"evidence":"4 raw captures (70 type rows x 2 class matchings x 2 machines x 2 contexts); zero-residue witnesses studio unsandboxed+sandboxed and mini unsandboxed+sandboxed; sandbox enforcement witnessed via HOME=/Users/<user>/Library/Containers/uk.4rg0naut.doorprobe/Data + write DENIED errno=1 rows","caveat":"ad-hoc signing, no hardened runtime, no provisioning profile — Mac App Store distribution constraints and AppleInternal sandbox profiles unprobed; one OS build (26A434); sandboxed-context client-class identity not re-attributed via creator-diff in this run (class assumed = unsandboxed result; probe3 does not create the ioreg hold witness)","contested":false}
```

### Addendum 2026-10-23 (EXP-034 full-access) — dated corrections, decode, cross-links

**Dated corrections to this document (measured 2026-10-23, `tools/ane_door_probe/probe5_devprops.c`,
studio + mini; raw: `results/EXP-034-full-access/raw/p5_*_ANEDriver.txt`):**

1. **sel-6 return code.** Q4/prose cited `kIOReturnNotReady`. The live code is
   `kIOReturnNotFound` (0xe00002f0 per SDK `IOReturn.h`); `kIOReturnNotReady` is
   0xe00002d8. "Handler reached, state-dependent" stands; the name did not.
2. **sel-0 payload labels.** "u64@88=1 / u64@112=4" (Q4) were probe4 scalar-output
   mislabels. True non-zero words in the 136 B response: `u32@0x54 = 1`,
   `u32@0x64 = 4` (low dwords of two u64s), `u64@0x50 = 0x1_00000000` (4 GiB, both
   boxes), `u64@0x60 = 0x4_00000000` (16 GiB — studio M5 Max 128 GB) vs
   `0x2_80000000` (10 GiB — mini M4 16 GB); all other words zero on both.
3. **Q5 gap sharpened (C-80):** the sel-2 rejection is not a token-size problem — a
   successful sel-1 pre-arm does not change it; the first gate is the
   `ANEProgramChainingPrepareArgs` blob grammar (callee deserializer; device-type
   switch `cmp w8,#3` + `OSValueObject<ANEClientDevice*>::init()` visible, no scalar
   compare in the dump window — `raw/kext/deep_sel2.asm`). Verdict:
   `results/EXP-034-full-access/c80_chaining_parked.json`.
   *Dated correction 2026-10-23 (EXP-035 C-83/C-84, `results/EXP-035-chaining-blob/OFFSET_MAP.md`):
   superseded by full callee-body disassembly. Format verdict **PLAIN fixed struct** —
   zero OSUnserialize in the whole consumption chain; the `cmp w8,#3` is the GLOBAL
   `_fAneSubType` jump-table read, not a payload field, and the
   `OSValueObject<ANEClientDevice*>` symbols were adjacent-window noise from the bounded
   EXP-033 extract. First gate = `ANEClientProgramHandle` u64 @args+0x10
   (`ANEDriver::getProgramResource`, log "Could not find program for handle 0x%llx");
   handle table is global in ANEDriver, and C-84 minted live handles in-process
   (5842/5883/5924, `probe7_capture`) — gap collapsed to offset-map fill for C-85.*

**Decode (C-79).** `DeviceProperties` on `ANEDriverRoot` is readable **unprivileged**
on both boxes and carries exactly one key, `ANEDevicePropertyNumANEs = 1` — the only
field-key match found against the sel-0 payload (u32@0x54=1). No mapping for the
4 GiB / 16 GiB / 10 GiB trio; Metal `recommendedMaxWorkingSetSize` (107.52 / 11.84 GiB)
measured and REFUTED as the source. MEASURE-162.

**Umbrella-naming footnote.** The shared-cache framework accessor
`getANEDeviceProperties` queries service name **"ANEDriver" first** (@0x1a20a619c,
`results/EXP-032-pulse-map/raw/ane_dsc.asm.gz:3182`) with a legacy **"H11ANEIn"
fallback** (@0x1a20a61f8, same file:3207) — matching the door finding: the current
service is the live door, H11 names survive as compatibility labels. The `H11ANE`
instance (`class ANEHWDevice`) exists on-host and was already in the EXP-033 sweep:
**all 70 open types `kIOReturnUnsupported`** on 26A434
(`results/EXP-033-door-map/raw/door_studio_unsandboxed.txt:72`) — so the H11 service
is visible but its user client is not; no door missed there.

**mdaiter/ane (era-scoped credit + refuted misattribution).** Marcus Daiter's
`mdaiter/ane` (pushed 2026-02-01, found via dated web search 2026-10-23, home base
read first) opened the ANE IOKit door **without** `com.apple.ane.iokit-user-access`
months before EXP-032/033 and published H11ANEIn open types {1,4} — agreement on the
**no-entitlement openability principle**; on 26A434 the H11ANE service instance itself
answers `kIOReturnUnsupported` on all 70 open types
(`results/EXP-033-door-map/raw/door_studio_unsandboxed.txt:72`), and the numeric pair
we measure now lives on `ANEDriverRoot`/`H1xANELoadBalancer` (MEASURE-158). Its failure
verdict (NotFound ⇒ "needs entitlement") is era-scoped and REFUTED for the 26A434 door:
our same-session arm sends the **104 B (0x68)** struct they code, exactly, at selector 0
and gets `kIOReturnBadArgument` (0xe00002c2, both boxes; also with their
`int32@0x18 = -1` variant), where our **136 B (0x88)** contract send succeeds `kr=0x0`.
Three distinct sizes are in play, none interchangeable: **96 B/96 B** is the Phrack
#72-documented selector-0 contract of the H11-era service (Q4; ncm-run prior_art §log),
**104 B** is their header's struct, **136 B** is this door's contract. Entitlement was
never the gate; struct size (era) is what mismatches. *Spine note: the MEASURE-162 sentence "whose selector-0
takes 96 B" attributes the Phrack-documented H11-era contract size to that service; the
emitted spine event is not rewritten — this note is its dated correction.* SlideShare talk "Exploiting Apple's Neural Engine"
(@_simo36) likewise names `H11ANEInDirectPathClient` "for Xcode apps" — same-era
framing, no measured kr codes. MEASURE-162.

**EXP-025 cross-link (package-only restriction re-opened as daemon-mediated-unproven).**
EXP-033/034 establish that an unprivileged direct client exists and persists; whether
Apple enforces anything at that layer is **unproven, not proven-absent** — the
"third-party programs must go through aned" status is *daemon-mediated*, and the
kernel-door alternative is now a characterized target, not a closed question. The
machinery for daemon-free GPU↔ANE signalling already exists in our measurements:
EXP-025's `_ANESharedEvents` / `IOSurfaceSharedEvent` mailbox (sel 1's
`retainSharedEvents` callee, mach-port bridge, ~62 µs hop) is the named side-door for
consumers while the chaining blob remains unparsed (ncm-run backlog §T4/§G5 pointers).

## Dated addendum — EXP-036 (2026-10-25): C-87 CLOSED — direct-path door CONFIRMED LOAD-BLIND

The C-87 candidate named by EXP-035 (`results/EXP-035-chaining-blob/CAPTURE.md` tail) — a
load-then-sweep of direct-path selectors 2–10 watching for a Gate-A setter — was run as
`results/EXP-036-side-door-inject/` (probe10, 3 runs, studio, 26A434). In-process compile+load
(state=3, fresh kernel-minted handles) produces **zero kr deltas** on all 9 unmapped selectors
and leaves the sel-2 Gate-A signature `0xe00002c2` unmoved even with the live handle minutes-fresh
in the same process; zero residue every run. No setter exists inside the 11-entry table for
unprivileged clients. The door-side weight-injection/submit lane is a **measured negative**
(upgrade from "NOT established, do not plan around it" in ncm-run backlog §IOKit item 1), and
the daemon-free lane is officially the EXP-025 `_ANESharedEvents` mailbox per the pre-declared
decision line. Grammar note from the same sweep: the sel0 136 B handler echoes the caller's own
input struct (`+0x10` u64, `+0x38` u32) into its output — fill-attributable, reproduced with a
never-loaded bogus handle pre-load, so sel0 carries no handle-validity semantics. Type-2
openability (aned's class) remains NotPrivileged (probe9); entitlement remains the untested
owner-gated frontier. MEASURE-164, MEASURE-165.

{"id":"MEASURE-164","claim":"The direct-path door (H1xANELoadBalancerDirectPathClient, open types {1,4}) is load-blind for unprivileged clients on 26A434: after an in-process compile+load of a real program (state=3, kernel-minted handles 131251/131285/131303 via _ANEInMemory), all 9 unmapped direct-path selectors (2-10) return kr codes byte-identical to their pre-load values across 3 runs and 4 fill phases (zero, bogus-handle pre-load, post-load zero, post-load live handle), and the sel-2 chaining-prepare Gate-A signature 0xe00002c2 is unchanged for every arm including a live handle in the same process; zero user-client residue before and after every run. The Gate-A setter is therefore NOT among the 11 entries of _sANEDriverDirectPathClientMethods; door-side program submit / weight refresh by unprivileged clients is a measured negative, closing EXP-035's C-87 lead.","kind":"measurement","confidence":"measured","source":"results/EXP-036-side-door-inject/README.md + raw/probe10_sweep_run1..3.jsonl + raw/analysis.txt + raw/prewitness_smoke.txt","source_type":"our-own","retrieved":"2026-10-25","topic":["ane","direct-path","iokit","chaining","weights"],"entities":["H1xANELoadBalancerDirectPathClient","_sANEDriverDirectPathClientMethods","probe10_loadsweep","ane_bridge","EXP-025 mailbox"],"evidence":"36/36 selector-phase kr cells identical across 3 runs (analysis.txt VERDICT line); Gate-A ladder N-zero/B-bogus/P1-live identical 3/3; residue pre=0 post=0 all invocations","caveat":"one OS build (26A434); scoped to unprivileged reachability — type-2 (aned's class) is NotPrivileged (probe9) and entitlement-granted behavior is untested; Gate-A mechanism by elimination, callee-level not source-level","contested":false}
{"id":"MEASURE-165","claim":"Direct-path selector 0 (136 B capability roundtrip) partially echoes the caller's input struct into its output: u64 at structIn+0x10 and u32 at structIn+0x38 reappear verbatim at the same offsets of structOut, observed with both a never-loaded bogus handle (0x2000f, pre-load) and kernel-minted live handles (131251/131285/131303, post-load) — the echo is fill-attributable, not load- or validity-attributable; the capability words (4 GiB/16 GiB u64 at +0x50/+0x60 with u32 1/4 at 0x54/0x64, EXP-034-corrected labels) are invariant across all 12 (run,phase) cells. Selector 0 therefore cannot serve as a handle-validity probe at the door.","kind":"measurement","confidence":"measured","source":"results/EXP-036-side-door-inject/raw/analysis.txt + probe10_sweep_run1..3.jsonl","source_type":"our-own","retrieved":"2026-10-25","topic":["ane","direct-path","iokit","grammar"],"entities":["probe10_loadsweep"],"evidence":"nonzero-byte dumps per phase per run (README results table); bogus-fill control added after first-run live misread (documented at corrected offsets +0x10/+0x38)","caveat":"echo coverage beyond +0x10/+0x38 untested (only those offsets were filled); one OS build","contested":false}
