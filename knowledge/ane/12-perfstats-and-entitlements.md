# 12 — ANE perf-stats and entitlements: who zeroes your statsMask, and why (EXP-031)

Compiled 2026-10-23 from EXP-031 (`results/EXP-031-ane-perfstats-spy/`): live
`aned` unified-log captures on the M5 Max studio (macOS 27.0.1 / 26A434), a
disassembly walk of `/usr/libexec/aned` (arm64e slice, `otool -tV`, 132,380
lines), and an ad-hoc-codesign pickpocket test on both fleet boxes. Inputs we
already owned: EXP-024 B5 (kANE_* counter-name map), EXP-029 (in-process
`_ANEPerformanceStats` harness, driver grants size=0 on the `_ANEInMemory`
route), EXP-022 (observability floor). External prior art used as
cross-check AFTER the home-base check (AGENTS.md §1): tmc/apple perf-stats
notes (measured zeros 2026-08-15, masks 0xF/^0, re-verified 2026-10-23),
Bryngelson arXiv:2606.22283 §33.3 (re-verified v2), maderix `test_perf_stats`
(commit 893f58e, 2026-03-01). Confidence tags follow doc 10: **[V]** verified
locally this session · **[C]** credible external, consistent with local
evidence · **[U]** unresolved.

## Q1 — The classification label is written in the open, and it is derived from your code signature **[V]**

- Every `loadModel` aned serves logs, unprivileged, in the `com.apple.ane:aned`
  subsystem (our capture, ncm0 `_ANEInMemory` client, 2026-10-23T08:25Z):
  `START: <private>: csIdentity=<private> : model=<private> :
  isPreCompiledModel=0 : existsInCache=1 : coreAnalyticsClientType=ThirdPartyAppUsingANE StatsMask=0`
  — `coreAnalyticsClientType` and `StatsMask` are **not** privacy-scrubbed; only
  the identity/model strings are `<private>` (needs `log config` + sudo, which
  we do not have unattended; recorded honestly).
- The same line appears for a vanilla CoreML client (`MLModel` on
  `minilm128.mlmodelc`, computeUnits=cpuAndNeuralEngine, 2026-10-23T08:28Z):
  **CoreML apps get `ThirdPartyAppUsingANE StatsMask=0` too**. The label is not
  aimed at private-API users specifically — everyone outside Apple's internal
  profiling clients is ThirdPartyAppUsingANE.
- How the value is computed, from the disassembly (§Q3): aned pulls the caller's
  code-signing identity through the XPC audit token —
  `SecTaskCopySigningIdentifier()` (log lines `returned csIdentity="…"`,
  and the code path `+[__ANEModelToken teamScopedCodeSigningIDFor:processIdentifier:]`
  @0x10001d448 feeding the same `%@` slot) and `SecTaskCopyTeamIdentifier()`
  (observed `teamIdentity=""` for our ad-hoc clients). The client-type label
  itself is produced by `+[__ANEDataReporter reportClient:modelName:]` @0x10001dc6c
  (framework-side implementation; aned logs its return value).
- Consequence: **the classification input is the caller's signing identity /
  team ID, not anything in the request payload**. You cannot ask for a
  different class; you present it. Ad-hoc signature → team `""` → ThirdParty.

## Q2 — The XPC-acceptance gate is entitlement-presence and soft; the stats path is identity-bound and hard **[V]**

- `-[__ANEXPCServiceHelper allowRestrictedAccessFor:entitlementString:]`
  @0x10000e4bc: `[connection valueForEntitlement:<name>]`; nil → false, else
  `boolValue`. `listener:shouldAcceptNewConnection:` consults the service's
  `requiresEntitlement` property and calls the helper (reject path 0x10000e81c).
  This is **presence + truthiness of a caller code-signing entitlement** —
  in principle copyable by re-signing.
- It never fires against us in practice: our connections are accepted (models
  load, programs run). The zeroing happens **after** acceptance, so acceptance
  is not the blocker.
- The stats path (Q1 + Q3) keys off signing identity, and identity/team is
  **not** ad-hoc-copyable — confirmed by the pickpocket test (§Q4).
  Verdict: for per-eval kANE counters, the gate is effectively **hard** for
  third parties on this OS: an Apple-issued signature (provisioned or
  Apple-internal), not a wish.

## Q3 — What the disassembly shows the mask actually does (and does not do) inside aned **[V]**

Walk of `-[__ANEServer loadModel:sandboxExtension:options:qos:withReply:]` and
friends (addresses are file-offets+`__TEXT` base in the arm64e slice;
`otool -tV` dump kept in the EXP-031 dir):

- Client option extraction: `options[kANEFPerformanceStatsMaskKey]` →
  `isKindOfClass:NSNumber` → `unsignedIntValue` @0x10001cecc →
  `+[ANEPerformanceStats driverMaskForANEFMask:]` @0x10001ced8 →
  `[instance setPerfStatsMask:]` @0x10001cee4. Identical
  extract-translate-install triple repeated at 0x10001e730 (loadNewInstance
  path) and at 0x100024860 / 0x10002a004 (compile + chaining paths).
- **No client-conditional branch between the loadModel entry and the kernel
  handoff.** The handoff `[_ANEProgramForLoad createProgramInstanceForModel:
  …statsMask:…]` receives `[self perfStatsMask]` fetched directly @0x10001f1ac
  and passed unmodified at the call @0x10001f290. The `START … statsMask=%u`
  kernel-side log @0x10000385c prints what was forwarded — our capture shows
  `statsMask=0` there, matching the post-translation value.
- So inside aned, the only userspace transform of the client's mask is
  **`+[ANEPerformanceStats driverMaskForANEFMask:]`** — an AppleNeuralEngine
  framework function (dyld shared cache; not in the aned binary). If the mask
  our client asked for (0xF in EXP-029 runs) arrives at the kernel as 0, the
  zero happened in that translation table or in the kernel driver
  (`initStatsBufferSection` per tmc, IOKit path) — **not** in a branch we can
  patch-bypass inside aned. [U: which of the two — needs an
  `IOKit`-level trace or the framework disassembly from the shared cache.]
- Mask is part of the program cache key
  (`_ANEProgramCacheKey initWithModelPath:modelKey:modelPerfStatsMask:bundleID:`):
  requesting a live mask invalidates cached programs — budget accordingly when
  testing.
- Adapter-weights gate (the other "No entitlement!" voice, loadNewInstance):
  `[ANEConfig adapterWeightsAccessEntitlementBypassBootArg]` +
  `isBoolBootArgSetTrue:` → skip; else
  `[ANEConfig adapterWeightsAccessEntitlement]` (key name is CONFIGURABLE at
  runtime) → `valueForEntitlement:` @0x1000211ec → `boolValue`
  @0x100021200, `tbz → 0x100021630`. The **"No entitlement!" log @0x1000228a0
  is diagnostic, not fatal** (the `cbnz` at 0x100021644 only gates the
  log-enabled check; execution continues at 0x10002164c). Anyone treating that
  string as a load failure is reading the wrong line.
- `ThirdPartyAppUsingANE` does NOT appear as a literal in this OS's aned
  strings — the label string lives in the framework reporter
  (`__ANEDataReporter`). tmc/Bryngelson §33.3 naming is consistent in substance
  (client-class policy), differs in location detail on 26A434. Delta stated: our
  observation is from the live log + binary; theirs from internal sources.

## Q4 — The pickpocket test failed exactly where Q2 predicts (C5 negative) **[V]**

Ad-hoc re-sign of our `ncm0` with candidate entitlements, kane probe re-run:

| build | entitlements | launch | kANE buffer | clientType / StatsMask |
| --- | --- | --- | --- | --- |
| ncm0_ent #1 | `com.apple.ane.iokit-user-access` + `com.apple.ANECompilerService.allow` + 2 private stats guesses | **SIGKILL rc=137** — AMFI "code signature validation failed fatally", kernel "load code signature error 4" | never reached | — |
| key-by-key bisect | each ANE key alone | iokit-user-access **137**, ANECompilerService.allow **137**, `com.apple.security.cs.disable-library-validation` OK | — | — |
| ncm0_ent #2 | `com.apple.security.cs.disable-library-validation` only (the ad-hoc-safe survivor) | OK, full field run | **size=0, rc=138 — unchanged** | `ThirdPartyAppUsingANE StatsMask=0` (log window 08:34Z) |
| mini (M4, 26A434) | same survivor plist | OK | **size=0 — unchanged** | (log capture see EXP dir) |

- Both ANE-feature keys are **AMFI-restricted**: they require an Apple-issued
  signature/profile; asserting them ad-hoc kills the binary outright (worse
  than not having them — the pre-existing ANE access our ad-hoc binary already
  gets comes from the unprivileged user-client path, not from those keys).
- The classification did not budge: still `ThirdPartyAppUsingANE`, still
  `StatsMask=0`, still `size=0` buffer, same rc=138 crash signature.
- Failures entry: FAILURES.md "F-ane-perfstats-pickpocket" (symptom →
  assumption → cause → rule).
- No Apple Development codesigning identity exists on either box
  (`security find-identity -v -p codesigning` → 0 valid), so the one remaining
  cheap escalation — a dev-team signature to test whether ANY non-empty team
  promotes the class — is blocked until the owner provisions one. Flagged, not
  silently dropped.
- **RESOLVED 2026-10-23 (evening): the dev-team test ran and the answer is
  NO.** Owner provisioned a free-Apple-ID "Apple Development" identity
  (chain: `Apple Development: <user>knight@mailbox.org (989JU35U77)` →
  WWDR G3 → Apple Root CA; codesign `TeamIdentifier=G7Z3WCMGZ6` — the box
  initially lacked the WWDR **G3** intermediate; imported from
  apple.com/certificateauthority, then `find-identity -v` showed 1 valid).
  Dev-signed scratch binary (`ncm0_cert`, via `dev/ane_teamid_test.sh`) got
  the **identical** classification at the 12:53:45 loadModel:
  `coreAnalyticsClientType=ThirdPartyAppUsingANE StatsMask=0`, and the kANE
  probe was unchanged (`t0.5 probe st=0x0 size=0`, SIGBUS in the factory
  handshake — same behavior as ad-hoc). Per-eval counters therefore require
  Apple-platform entitlement, not merely a non-empty team ID. Evidence:
  `raw/logG-devteam-aned.log`, `raw/kane-run-devteam-studio.txt`; claim
  CORE-009. (Operational note: in zsh the `log` builtin shadows
  `/usr/bin/log` — use the full path for unified-log captures.)

## Q5 — What this changes for the kANE counter program **[V-rule]**

1. EXP-029's "driver gap" is now a **mechanism**: per-eval counters are an
   entitlement/identity policy keyed on signing identity at `loadModel` time;
   third-party class zeroes the mask before the kernel sees it (via
   `driverMaskForANEFMask:` and/or the IOKit path). Not a bug, not
   fixable in-process. The unlock candidates this kills: (a) more entitlement
   guessing ad-hoc, (b) re-signing with public ANE keys. What stays open:
   (c) kernel-level trace of `initStatsBufferSection`/IOKit (needs sudo),
   (d) whole-engine channel naming (Bryngelson §33.3 claims readable
   unentitled channels on M1/M5 — tmc could not reproduce; our enginemon/PMP0
   lane already holds an independent whole-engine signal),
   (e) owner-provisioned dev-team signature (one-command test, blocked on cert)
   — **CLOSED 2026-10-23: ran, answer NO (see §Q4 resolution + CORE-009);
   nothing short of Apple-platform entitlement promotes the class.**
2. Do not bake ANE-counter expectations into any runtime: the PMP0 `DCS BW`
   residency lane (EXP-022) remains our only zero-permission ANE activity
   signal, per-engine attribution stays heuristic.
3. Any future entitlement test must budget the cache-key effect (Q3): mask
   changes recompile programs; use a scratch model path.

### Q5 addendum — open-thread feasibility, measured on-box 2026-10-23 **[V]**

External cross-check report received 2026-10-23 (post-home-base check, per
§1): proposes (1) a two-breakpoint lldb/dtrace split of framework-table vs
kernel zero, (2) IOReport channel naming as the unentitled surface,
(3) dev-team-cert promotion test. Feasibility facts measured here before
adopting any of it:

- **SIP: enabled (full)** — `csrutil status`. dtrace present
  (`/usr/sbin/dtrace`) but no unattended sudo on either box; lldb present.
  Attaching a debugger to the hardened platform daemon `aned` under full SIP
  is untested and may need a SIP-relief boot session — testing attach is the
  first act of any Thread-1 session, not the breakpoints.
- **`ioreporter` is absent on macOS 27.0.1** (`which ioreporter` → not
  found). The report's `ioreporter -l | grep -i ane` recipe cannot run on
  this OS as written; an IOKit/IOReport programmatic path (or the Energy
  Model channels we already enumerate via enginemon) is the substitute.
- **Register-passing correction to the proposed breakpoints**: at the
  `driverMaskForANEFMask:` call site (@0x10001ced8) the mask argument is in
  **x2** (post-`unsignedIntValue`), not x0/x1 as the report assumes; and at
  the kernel handoff (@0x10001f290) the mask is **stack-passed**
  (`str w26, [sp, #0x4]` after the `[self perfStatsMask]` fetch @0x10001f1ac)
  — a breakpoint reading argument registers at the call would miss it.
  Breakpoints must use ASLR-slide-adjusted addresses or ObjC-symbol form.
- **Poison-first rule for the §33.1 `+0x6c` struct-offset claim**: treat the
  offset as **[U]** until proven by a poison request (client mask `0xFACE`,
  scan the args blob/stack for `0xface` at the handoff); do not trust a
  third-party offset against a different OS build blind — this is the same
  written-zero-vs-never-written discipline as the M5 matmul findings.
- **Thread 2 is already ours by a different route**: the report's channel
  names (`ANE_CORES`/`ANE_NOCP`) match nothing in our 12-channel PMP0
  inventory (EXP-024 B5); our enginemon PMP0 `DCS BW` residency lane
  (EXP-022) is a measured, on-box, unentitled whole-engine ANE activity
  signal. Any IOReport re-surfacing is a naming/delta exercise, not new
  capability, unless it yields per-eval counters.

## Claims

```jsonl
{"id":"CORE-004","claim":"aned logs the ANE perf-stats client classification in the open for unprivileged processes: every loadModel START line carries coreAnalyticsClientType and StatsMask in cleartext, and both our ad-hoc private-API client (ncm0 on the _ANEInMemory route) and a vanilla CoreML client (MLModel cpuAndNeuralEngine on minilm128) are labeled coreAnalyticsClientType=ThirdPartyAppUsingANE with StatsMask=0 on macOS 27.0.1/26A434 — the label is written by +[__ANEDataReporter reportClient:modelName:] (@0x10001dc6c) from the caller's audit-token signing identity (SecTaskCopySigningIdentifier; SecTaskCopyTeamIdentifier returns teamIdentity=\"\" for ad-hoc), not from anything in the request payload.","kind":"measurement","confidence":"measured","source":"results/EXP-031-ane-perfstats-spy/raw/logA-ncm0-aned.log ; results/EXP-031-ane-perfstats-spy/raw/logB-coreml-aned.log ; disassembly of /usr/libexec/aned arm64e slice (raw/aned.text.asm.gz in same dir)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","perfstats","entitlements","observability","client-classification"],"entities":["aned","coreAnalyticsClientType","ThirdPartyAppUsingANE","StatsMask","__ANEDataReporter","SecTaskCopySigningIdentifier","SecTaskCopyTeamIdentifier"],"evidence":"logA 2026-10-23 10:25:53.785 START line with coreAnalyticsClientType=ThirdPartyAppUsingANE StatsMask=0; logB same for CoreML pid; teamIdentity=\"\" debug line at 10:28:40.391","caveat":"csIdentity/model strings remain <private> without a sudo log config; the classification VALUE is public, the identity inputs are not fully unmasked on this box","contested":false}
{"id":"CORE-005","claim":"On macOS 27.0.1 (26A434) aned performs no client-conditional zeroing of the perf-stats mask inside loadModel: the client-supplied options[kANEFPerformanceStatsMaskKey] is extracted, run through +[ANEPerformanceStats driverMaskForANEFMask:] (@0x10001ced8, framework-side translation), installed via setPerfStatsMask:, and forwarded unmodified to the kernel handoff createProgramInstanceForModel:...statsMask: (fetch @0x10001f1ac, call @0x10001f290); the only userspace candidate for the third-party zero is therefore the driverMaskForANEFMask translation table or the kernel IOKit path (initStatsBufferSection), and the mask participates in the program cache key, so mask experiments recompile cached programs.","kind":"measurement","confidence":"measured","source":"results/EXP-031-ane-perfstats-spy/raw/aned.text.asm.gz (otool -tV, arm64e slice) — walk documented in knowledge/ane/12-perfstats-and-entitlements.md Q3","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","perfstats","disassembly","aned","kernel-handoff"],"entities":["ANEPerformanceStats","driverMaskForANEFMask:","createProgramInstanceForModel","_ANEProgramCacheKey","kANEFPerformanceStatsMaskKey"],"evidence":"extract-translate-install triple at 0x10001cecc/ced8/cee4 (repeat 0x10001e730, 0x100024860, 0x10002a004); no branch between entry and handoff; statsMask=%u log @0x10000385c prints forwarded value","caveat":"which of framework-table vs kernel zeroes the mask is unresolved without an IOKit trace (needs sudo); the XPC-acceptance entitlement gate (@0x10000e4bc, presence+boolValue) is separate, soft, and never the blocker for us — our connections are accepted","contested":false}
{"id":"CORE-006","claim":"Ad-hoc re-signing cannot buy ANE perf-stats: on both M5 Max and M4 mini (26A434) asserting com.apple.ane.iokit-user-access or com.apple.ANECompilerService.allow on an ad-hoc binary gets it SIGKILLed by AMFI (rc=137, 'code signature validation failed fatally', kernel load error 4), only com.apple.security.* keys survive ad-hoc, and the surviving-key build's kANE probe is unchanged (stats buffer size=0, rc=138, coreAnalyticsClientType=ThirdPartyAppUsingANE, StatsMask=0) — the gate is bound to the Apple-issued signing identity (team ID ''), which ad-hoc signatures cannot forge.","kind":"measurement","confidence":"measured","source":"results/EXP-031-ane-perfstats-spy/README.md §Method-4 + raw/kane-run-c5-signed-studio.txt + raw/kane-run-c5-signed-mini.txt ; AMFI/kernel log lines in raw/","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","perfstats","entitlements","codesign","ad-hoc"],"entities":["AMFI","codesign","com.apple.ane.iokit-user-access","com.apple.ANECompilerService.allow","com.apple.security.cs.disable-library-validation"],"evidence":"key-by-key launch bisect: iokit-user-access rc=137, ANECompilerService.allow rc=137, disable-library-validation rc=0; security find-identity: 0 valid identities on box","caveat":"the one untested escalation is a real (dev-team) certificate: whether a NON-Apple but non-empty team ID promotes the client class is unknown — both fleet boxes have zero codesigning identities; owner decision to provision one closes this in one command","contested":false}
{"id":"CORE-007","claim":"The adapter-weights entitlement check in aned is soft, configurable, and its 'No entitlement!' log line is diagnostic rather than fatal: loadModelNewInstance consults an ANEConfig-provided boot-arg bypass (adapterWeightsAccessEntitlementBypassBootArg + isBoolBootArgSetTrue:) and an ANEConfig-NAMED entitlement key (adapterWeightsAccessEntitlement) via valueForEntitlement:+boolValue (@0x100021134-0x100021204), and the 'No entitlement!' emitter at 0x1000228a0 sits on a log-enabled check (cbnz @0x100021644) with execution continuing at 0x10002164c — loads proceed regardless.","kind":"measurement","confidence":"measured","source":"results/EXP-031-ane-perfstats-spy/raw/aned.text.asm.gz walk in knowledge/ane/12-perfstats-and-entitlements.md Q3","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","adapter-weights","entitlements","disassembly"],"entities":["ANEConfig","adapterWeightsAccessEntitlement","adapterWeightsAccessEntitlementBypassBootArg","valueForEntitlement:"],"evidence":"cbnz @0x100021644 gates only os_log type check; fallthrough continues @0x10002164c","caveat":"practical relevance: third parties reading 'No entitlement!' in aned logs as a failure are misreading a debug line; the actual denial semantics for adapter weights live further down the kernel path we did not walk","contested":false}
{"id":"CORE-008","claim":"The Core AI runtime on the studio rejects the h17g-AOT reranker bundle with incompatibleCompiledAssetArchitecture(device: \"h17c\", asset: [\"h17g\"]) at GraphModel load — a runtime-measured confirmation, from a CoreAI GraphModel error string rather than compiler inspection, that this M5 Max's platform device string is h17c (consistent with doc 11 platform naming: H+generation+tier-letter, C=Max) — while the source (non-AOT) .aimodel JIT-compiles and runs on the same box.","kind":"measurement","confidence":"measured","source":"results/EXP-031-ane-perfstats-spy/raw/coreai-client-run.txt ; results/EXP-031-ane-perfstats-spy/raw/logF-coreai-aned.log","source_type":"our-own","retrieved":"2026-10-23","topic":["coreai","platform-naming","aot","ane"],"entities":["h17c","h17g","GraphModel","incompatibleCompiledAssetArchitecture","qwen3-reranker"],"evidence":"GraphModel(contentsOf:) fatal error string names device \"h17c\"; AOT asset targeted h17g (M4-era bundle)","caveat":"incidental to the perf-stats question; recorded because it corroborates doc 11 and doc 10 CORE-002 with an independent 2026-10-23 datapoint and closes 'which target name does an M5 Max claim at runtime'","contested":false}
{"id":"CORE-009","claim":"A real Apple-issued developer-team signature does NOT promote the ANE perf-stats client class on macOS 27.0.1 (26A434): an ncm0 signed as 'Apple Development: <user>knight@mailbox.org (989JU35U77)' (codesign TeamIdentifier=G7Z3WCMGZ6, full chain to Apple Root CA after importing the missing WWDR G3 intermediate) received the identical aned classification 'coreAnalyticsClientType=ThirdPartyAppUsingANE StatsMask=0' at loadModel (12:53:45 local, 2026-10-23) and an unchanged kANE probe (t0.5 probe size=0, SIGBUS in the factory handshake) — closing the last non-entitled unlock candidate: per-eval kANE counters require Apple-platform entitlement, not merely a non-empty team ID.","kind":"measurement","confidence":"measured","source":"results/EXP-031-ane-perfstats-spy/raw/logG-devteam-aned.log + raw/kane-run-devteam-studio.txt (dev/ane_teamid_test.sh run on the studio)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","perfstats","entitlements","codesign","dev-team"],"entities":["codesign","Apple Development","WWDR G3","ThirdPartyAppUsingANE","StatsMask","ane_teamid_test.sh"],"evidence":"logG 12:53:45 START line coreAnalyticsClientType=ThirdPartyAppUsingANE StatsMask=0 for the dev-signed pid; probe log t0.5 size=0; codesign -dvv Authority chain + TeamIdentifier=G7Z3WCMGZ6","caveat":"free personal-team identity (7-day cert); an Apple-internal/entitled build was not testable by us — that is exactly the remaining boundary this claim draws","contested":false}
```

## Provenance

- Doc number: 12 is the next free slot (00–11, 16 exist; 13–15 held per
  ARCHIVE-MAP convention of leaving gaps for re-framings — decision recorded
  here, 2026-10-23).

- Studio: M5 Max Mac17,14, macOS 27.0.1 (26A434), fingerprint `bda452aabd60bf26`,
  workspace tip `d8095d0`, release build of `ncm0` (`ncm-run/bare`).
- Mini: M4 Mac16,10, 26A434, fingerprint `057b28dd036ddbe8`, tree
  `/Users/<user>/night/ncm` @ `4cde731`.
- Binaries/artifacts retained: `aned.text.asm` (full otool dump), raw log
  windows A–D, mini capture, pickpocket plists, cdpkg driver source.
- Heavy scratch (kane field dumps ~1 GB) gitignored per policy; names in
  README.
