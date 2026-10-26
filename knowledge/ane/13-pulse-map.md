# 13 — The pulse map: counting ANE evaluations from user space without the key

Document number rationale: fills the deliberate gap 13–15 in this series; doc 16 is an
imported standalone line (`16-neural-accelerators.md`) and stays what it is. Campaign:
**EXP-032 pulse-map** (2026-10-23, studio M5 Max + mini M4). Evidence root:
`results/EXP-032-pulse-map/`. Sibling mechanism doc: `12-perfstats-and-entitlements.md`
(why the kANE door is policy-locked); this doc is the "what we can read anyway" half.

## Q1 — Can user space count ANE evaluations on M5? **[V]**

Two candidate lanes exist in the IOReport export on 27.0.1/26A434:

1. **Interrupt handler counters** (`Interrupt Statistics (by index)`): subgroup `ane 0`
   on M4, `dart-ane0 0` on M5 Max. Measured (18 captures, dual client path, joined
   table `results/EXP-032-pulse-map/pulse_table.tsv`):
   - M4, direct `_ANEInMemory` path, 20,000-eval `anectx --iters`: **29,299 handler
     fires = 1.465/eval** (idle bookend 2 over 9.1 s) — the interrupt lane is live on
     M4 for direct-API work too, which MEASURE-012 had only established for CoreML.
   - M5 Max, same binary + workload (×3), 30k under `--all`, and CoreML 40,000
     predictions ×3 (26.9 s/run, ANE lanes in the same captures confirm the engine
     was busy): **zero fires on every channel of `dart-ane0 0`**. Dual-path control +
     same-workload cross-machine positive control ⇒ the zeros are gated, not
     misread. On M5 there is no modulation to measure: the doorbell lane is closed at
     user level, both through the direct path and through CoreML.
2. **SOC-NI interconnect utilization lanes** (`PMP0 SOC-NI Util BW`), the lanes
   EXP-002/MEASURE-152 flagged as ANE-exclusive (`SOC-NI9 "ANEXL U"`, corroborated by
   `SOC-NI8 "ANE UP"`): these **do count per eval on M5**, at shape-dependent
   coefficients — 0.488–0.503/eval (S=32 parity kernel, n=3, ±1.5%), 1.00–1.06/eval
   (S=160 unified kernel, n=8, ±3%), 2.889–2.915/prediction (CoreML minilm128,
   n=3, ±0.5%; two ANE regions per prediction). Corroborating event lanes
   (`PMP0 DCS BW → ANE L0/L1 RD+WR`) scale with program shape too (0.8→86 events/eval
   across the two kernels) — they count DMA events, so they track the program, not
     the eval; use them as a shape fingerprint, not an eval meter.

So the answer is path-dependent: **the per-eval interrupt counter is M4-era
instrumentation, gated out on M5; the per-eval counting job is taken over by the
SOC-NI9/NI8 lanes on M5**, with a fixed-program caveat (coefficient is a property of
the program, not a universal constant) and whole-engine attribution (shared-engine
multi-client ambiguity, same class as EXP-022).

## Q2 — What DCS floor states show during the same windows **[V]**

`DCS Floor → ANE-DCS-BW` and `SOC Floor → ANE-LNK0/1-AF-BW` tick lanes rise off
their idle floor synchronized with the eval bursts (ticks, duty-cycle semantics —
the EXP-022/EXP-024 calibrated signal, not event counts; they corroborate busy/idle
windows, they do not add per-eval resolution). M5 does not export the M4-style
`AMC Stats` per-master byte counters at user level (known, EXP-024), and the M4
`DCS RD` total lane is system-wide (~1.9 GB/s even at desktop idle) — recorded so
nobody mines the M4 row in `pulse_table.tsv` for ANE bytes.

## Q3 — The kernel door: which IOKit service, which selectors **[V]**

Branch decision by measurement (C-68): `AppleNeuralEngine.framework` (dyld shared
cache 26A434, `ipsw dyld disass`) imports and calls the standard IOKit user-client
API — branch **(a) confirmed**, no Mach-message pivot needed. Every kernel-facing
call site is classified (`raw/ios_callsites.tsv`, full disasm `raw/ane_dsc.asm.gz` (read with zcat)):

| service name (IOServiceMatching) | where | role |
| --- | --- | --- |
| `AppleVirtIONeuralEngineDevice` | `-[_ANEVirtualClient initWithSingletonAccess]` → `IOServiceGetMatchingServices` → `IOServiceOpen(type 0)` | virtio frontend door in the framework — **dormant on bare-metal hosts**: zero instances of this class in the host IORegistry (C-69 probe); the selectors talk "hosts" (`transferFileToHostWithPath:`), i.e. this is the VM-guest door that speaks to the virtio-NE backend |
| `ANEDriver` / `H11ANEIn` | static `getANEDeviceProperties(CFString)` → `IOServiceGetMatchingService` + property reads only | device-info property path; no `IOServiceOpen` in the framework — but the service itself answers unprivileged opens (C-69, below) |

Selector map (all `IOConnectCallMethod`; **inScalarCnt is always 0 — every payload
is a struct**, sizes = captured `mov w5` immediates; conn handle read from
`_ANEVirtualClient+0x30`):

| sel | method (enclosing function) | inStruct |
| --- | --- | ---: |
| 0x00 | init handshake (`IOConnectCallScalarMethod`) | — |
| 0x0e | sendGuestBuildVersion | 0x28 |
| 0x0f | exchangeBuildVersionInfo | — |
| 0x10 | callIOUserClientWithDictionary | — (dict path) |
| 0x11 | validateNetworkCreate | 0x7f8 |
| 0x12 | getDeviceInfo | — |
| **0x13** | **doEvaluateWithModel — the eval door** | **0x10** |
| 0x14 | sessionHintWithModel | 0x138 |
| 0x15 | createValidationResultForNetworkCreateMLIR | 0x20 |
| 0x16 | transferFileToHost / transferDirectoryMetaDataToHost | 0x2c8 |
| 0x17 | loadModelNewInstance | 0x20 |
| 0x18 | compileModel | 0x940 |
| 0x19 | loadModel | 0xce8 |
| 0x1a | compiledModelExistsFor / purgeCompiledModel | 0xa8 |
| 0x1b | assetExistsOnHost | 0x84 |
| 0x1c / 0x1d / 0x1e | doMapMutableWeights / doSyncMutableWeights / doUnmapMutableWeights (+map-complete) | 0x210 / 0x218 / 0x208 |
| dyn | `callIOUserClient:inParams:outParams:` — selector from caller argument (generic escape hatch; out-struct 0xa50 sized on stack) | — |

Eval is a 16-byte input struct on selector 0x13 — the smallest, hottest door; this
is the door the pulse map (Q1) counts from the other side, and the door a C-69-style
direct client must speak. The weight-mutation trio (0x1c–0x1e) is the delta-path
machinery our T4/anetrain harness exercises through the framework.

**Kernel side:** kextstat confirms `com.apple.driver.AppleH16ANEInterface` 10.19.2
+ `com.apple.driver.AppleT6050ANEHAL` 10.19.0 loaded; **no kernelcache file exists
on this OS** (`/System/Library/KernelCollections/` absent, Preboot has no kernel
im4m) — SPTM-era kernel composition leaves the kext offline-unextractable without a
restore image or live-memory read (sudo). Verdict: honest NOT-REACHABLE for kext
disassembly on-box; selector→kext-routine crossmap deferred to a restorable image.
**Host reality (C-69 live probe, same day — corrects the virtio assumption above):**
a plain unprivileged process (our `tools/ane_door_probe`, no entitlement, no sandbox,
uid 501) against the running host finds `AppleVirtIONeuralEngineDevice` with **zero
instances** — the framework's virtio path is the VM-guest door, dormant on bare
metal. The live host door is the service matched by `IOServiceMatching("ANEDriver")`
(instance `ANEDriverRoot`, kernel classes `ANEDriver`/`H1xANELoadBalancer` under
IOResources; hardware below it: `ane0@8000000` AppleARMIODevice + `dart-ane0`):

| open type | result | server-side object |
| --- | --- | --- |
| 0 (framework's type) | `kIOReturnUnsupported` (0xe00002c7) on every ANE service | — |
| **1** | **OPENED** | `H1xANELoadBalancerDirectPathClient` — same class as the 8 clients held by `mediaanalysisd` |
| **4** | **OPENED** | also `H1xANELoadBalancerDirectPathClient` (hold-captured live) |
| all other 70 probed types (2,3,5–0x48,0x50…0x8000) | `kIOReturnUnsupported` | — |

`aned`'s own `H1xANELoadBalancerClient` is **not** reachable by any unprivileged
open type we can produce (its creation path predates or exceeds our context's
rights — boot-time or entitlement-gated).

`IOConnectCallMethod(sel=0x12, 1 scalar in, 8 scalar out)` on the type-1 connection
returns `kIOReturnBadArgument` (0xe00002c2): the call **dispatches** — the virtio
selector table above is not the load-balancer's table. Client objects appear and
disappear cleanly with close (zero residue). So: production eval traffic goes
process → `aned` XPC → type-4 client → kernel (our direct-API ncm0 evals create no
IOKit object for their own pid — verified by `IOUserClientCreator` inspection),
while `mediaanalysisd` runs an unmediated direct path (type 1) that **any unprivileged
third-party process can replicate** — `IOServiceOpen` answers without root, without
entitlement, on the same class. The M5 door is open; what remains closed is the
selector grammar of the type-1 direct-path table (needs kext-side crossmap, above).
*Amendment 2026-10-23 (EXP-033 C-75, doc 14 Q4): the kext crossmap landed — the
type-1 table is 11 entries (`_sANEDriverDirectPathClientMethods`); the probe's
selector 0x12 was out of table bound (BadArgument = bound check), not "the wrong
table"; grammar mapped (chaining/lifecycle, no eval-submit; sel 0/1 succeed live).*
*Note 2026-10-23 (post-campaign web cross-check, logged in ncm-run prior_art): the
door family's openability was previously published in an iOS attack-surface context —
BlackStorm Security, "Exploiting Reversing (ER) series Article 10" (Alexandre Borges,
2026-10-06, pp. 107–108): an `IOServiceOpen` type sweep 0..15 over every IOService
from a **sandboxed iOS app** (iOS 27.0 GA) prints `TYPEOPEN H1xANELoadBalancer
type=1` and `type=4` — **the identical type pair** we measured on macOS, corroborating
a stable cross-platform driver policy rather than a probe artifact. Our surviving
deltas: macOS host context (theirs iOS/sandboxed/types≤15), client-class attribution
(`IOUserClientCreator` diff → DirectPathClient == `mediaanalysisd` production class),
framework type-0 closure proof, the live selector-dispatch round-trip, 70-type
breadth, and the virtio VM-guest finding. Their kernelcache mining
(`AppleH16ANEInterface`: `ANEScheduler`, `ANEProgramRTResource` symbols, iOS IPSW)
also shows the kext crossmap that is NOT-REACHABLE on-box here is obtainable from an
iOS restore image if that corpus is acceptable.*

## Door artifacts (C-71) — the compiled-program blob is ours to read

While C-69/C-70 ran, `/usr/bin/log stream` + tmpDir forensics named the compiled
artifact: `results/EXP-032-pulse-map/raw/c71_blob/NOTES.md` (naming = SHA256uppercase
of model.mil = `hexStringIdentifier`; `data` blob reuses the RUNTIME-013 chunk
grammar with DEADBEEF records mirroring our weight regions one-for-one).
`/Library/Caches/com.apple.aned` stays EPERM unprivileged and aned log paths render
`<private>` at --info — the readable copy is the client-staged one. Claim: MEASURE-157.

## Claims

```jsonl
{"id":"MEASURE-153","claim":"On the M5 Max studio (27.0.1/26A434) the ANE interrupt handler counters at user level are dead on BOTH client paths — 0 fires on every 'Interrupt Statistics (by index)' subgroup dart-ane0 0 channel across 70,000 direct-API anectx evals (3×20k + 30k under --all) and 120,000 CoreML predictions (3×40k minilm128, 26.9 s/run, ANE busy confirmed by SOC-NI lanes in the same captures) — while the identical binary and workload on the M4 mini fires 29,299 handler counts (1.465/eval, idle bookend 2/9.1 s) on subgroup 'ane 0', extending MEASURE-012 (CoreML-only, M4) to the direct _ANEInMemory path and dual-path-controlling the M5 gate conclusion first stated as an EXP-024 calibration note.","kind":"measurement","confidence":"measured","source":"results/EXP-032-pulse-map/pulse_table.tsv + raw/ (18 enginemon --interval 100 --json captures, 2026-10-23)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","interrupts","observability","m5","regression"],"entities":["enginemon","Interrupt Statistics","dart-ane0","ane 0","anectx","coreml_run","minilm128"],"evidence":"M5 all-zero across 4 direct + 3 CoreML captures; M4 29,299 fires/20,000 evals same workload; idle controls 0 and 2; joined per-run table with eval counts from stamped ncm0 ledgers 11-34/11-35/11-37Z-bda452aabd60bf26 + 11-39-23Z-057b28dd036ddbe8","caveat":"one machine pair, one OS build 26A434; 'dead' = user-level IOReport read path; kernel-side counters may still count behind sudo/SIP (Thread-1 question, EXP-031 C-64 pack)","contested":false}
{"id":"MEASURE-154","claim":"The M5 per-eval ANE counter that works unprivileged is PMP0 SOC-NI Util BW lane 'SOC-NI9 ANEXL U' (corroborated by 'SOC-NI8 ANE UP'): counts are per-eval exact within ±1.5–3% at shape-fixed coefficients measured as 0.488–0.503/eval on the S=32 parity kernel (20k evals ×3), 1.00–1.06/eval on the S=160 unified field kernel (100 evals ×8 fresh processes), and 2.889–2.915/prediction for the CoreML-compiled minilm128 program (40k ×3, ±0.5%, two ANE regions per prediction) — upgrading MEASURE-152's zero-vs-nonzero existence proof into a calibrated per-eval meter; the coefficient is a property of the ANE program shape, so a fixed-program calibration is the standing precondition for using it as an eval count.","kind":"measurement","confidence":"measured","source":"results/EXP-032-pulse-map/pulse_table.tsv + raw/ + ANALYSIS-C67.md","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","observability","m5","attribution","instrumentation"],"entities":["SOC-NI9","ANEXL U","SOC-NI8","ANEXL","enginemon","anectx","minilm128","ANECompiler"],"evidence":"18-capture joined table; per-eval coefficients with per-run spreads; DCS BW ANE L0/L1 event lanes fingerprint the program shape (0.8→86/eval across kernels)","caveat":"whole-engine lane events under a fixed program — a per-eval proxy, not per-task named counters; multi-client shared-engine attribution stays ambiguous (EXP-022 class); M4 exports no SOC-NI8/NI9 rows on this OS","contested":false}
{"id":"CORE-010","claim":"The ANE kernel door on macOS 27.0.1 (26A434) is IOKit, in two doorways: (a) AppleNeuralEngine.framework speaks a virtio frontend protocol — service class 'AppleVirtIONeuralEngineDevice', opened with type 0 in -[_ANEVirtualClient initWithSingletonAccess] with struct-passed payloads everywhere (all 29 kernel-facing sites resolved, inScalarCnt=0; selector map 0x00–0x1e, evaluate=0x13/16B, loadModel 0x19/0xce8, compileModel 0x18/0x940, weight-mutation trio 0x1c/0x1d/0x1e), but this class has ZERO instances in the bare-metal host IORegistry — it is the VM-guest door; (b) the live host door is the service matched by IOServiceMatching('ANEDriver') (instance ANEDriverRoot, classes ANEDriver/H1xANELoadBalancer), which answers UNPRIVILEGED IOServiceOpen at exactly two of 70 probed open types (1 and 4 — both create class H1xANELoadBalancerDirectPathClient, the same class mediaanalysisd holds ×8 in production; aned's own H1xANELoadBalancerClient is not producible from our unprivileged context); all other types return kIOReturnUnsupported, and a scalar IOConnectCallMethod round-trip on the type-1 connection dispatches (kIOReturnBadArgument on the virtio selector table, proving live kernel dispatch).","kind":"fact","confidence":"measured","source":"results/EXP-032-pulse-map/raw/ane_dsc.asm + raw/ios_callsites.tsv (ipsw dyld disass + a2f over 26A434 cache) + raw/c69_doorprobe/ (tools/ane_door_probe, live IORegistry + IOServiceOpen + IOConnectCallMethod results)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","iokit","protocol","virtio","direct-path","reverse-engineering"],"entities":["_ANEVirtualClient","AppleVirtIONeuralEngineDevice","ANEDriver","H1xANELoadBalancer","H1xANELoadBalancerDirectPathClient","H1xANELoadBalancerClient","mediaanalysisd","aned","IOServiceOpen","IOConnectCallMethod","ipsw"],"evidence":"per-site table with selector immediates (mov w1), input-struct sizes (mov w5), enclosing symbols via a2f; conn handle at _ANEVirtualClient+0x30; kextstat AppleH16ANEInterface 10.19.2 + AppleT6050ANEHAL 10.19.0 loaded; probe: open type 0/1/2/3/0x10/0x20/0x30/0x32/0x7100/0x7101/0x8000 results table, IOUserClientCreator ioreg diff before/hold/after (zero residue)","caveat":"selector semantics named by enclosing Objective-C method, not by kernel-side routine identity — no kernelcache file exists on this SPTM-era OS for offline kext crossmap; type-1 direct-path selector grammar unexplored beyond one dispatch probe; probe run from unsandboxed uid-501 shell only (sandboxed app context not tested)","contested":false}
{"id":"MEASURE-155","claim":"The M5 Max production ANE door is reachable by unprivileged third-party code without root or entitlement: a plain uid-501 unsandboxed C tool opening IOServiceMatching('ANEDriver') succeeds at exactly two of 70 probed open types (1 and 4), and BOTH create server-side class H1xANELoadBalancerDirectPathClient — verified by ioreg IOUserClientCreator diff before/during/after connection hold, the same class mediaanalysisd (pid 22631) holds ×8 in production; aned's (pid 23399) own H1xANELoadBalancerClient is not producible from any unprivileged open type probed; direct-API ncm0 evals create no IOKit user-client object for their own pid (eval traffic is aned-XPC-mediated), and the one scalar round-trip issued on the type-1 connection (selector 0x12, 1-in/8-out scalars) returned kIOReturnBadArgument — live kernel dispatch, wrong selector table for the load-balancer (virtio table is the framework-guest grammar).","kind":"measurement","confidence":"measured","source":"tools/ane_door_probe/ (main.c probe2.c roundtrip.c hold.c + outputs, captured raw/c69_doorprobe/)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","iokit","direct-path","observability","m5"],"entities":["ANEDriver","ANEDriverRoot","H1xANELoadBalancerDirectPathClient","H1xANELoadBalancerClient","mediaanalysisd","aned","IOServiceOpen","kIOReturnUnsupported","kIOReturnBadArgument"],"evidence":"open-type matrix over {0–0x48,0x50,0x60,0x6c,0x70,0x80,0x100,0x7100,0x7101,0x8000}: only 1 and 4 succeed; ioreg -l IOUserClientCreator diff (raw/c69_doorprobe/creator_diff.txt) shows hold-pid client appearing as DirectPathClient for both types and removed at close (zero residue); mediaanalysisd 8× DirectPathClient + aned 1× LoadBalancerClient observed as production reference","caveat":"unsandboxed uid-501 context only — sandbox/entitlement behaviour in app processes not probed; selector grammar of the direct-path table unexplored (one dispatch probe); M4 cross-check not run for the open-type matrix","contested":false}
{"id":"MEASURE-156","claim":"The raw-MIL accept/reject grammar of the working _ANEInMemory compile door on 27.0.1 (26A434) is individually measurable and cross-machine identical: a 20-case one-feature-per-program battery (fresh process per case) gives 12 ACCEPT / 8 REJECT with identical verdicts on M5 Max and M4 mini — conv-chain grammar with int8-affine BLOBFILE weights accepts softmax over non-power-of-2 dims (hollance-44 gotcha #1 does NOT reproduce at compile on this door/OS), tanh activation, Cin non-128-multiples and non-power-of-2 spatial at compile (alignment cliff is runtime-only), S in {16,32,48,100}; it rejects reduce_mean (gotcha #3 confirmed absent) while accepting reduce_sum ONLY with explicit axes+keep_dims (the community 'reduce_sum+mul workaround' fails bare), rejects slice_by_index in all three probed forms including full axes/begin/end signature on a constexpr (gotcha #2 is op-absence, not function-input position), rejects gelu (tanh stands in), rejects fp32 function inputs (fp16-only io), and rejects inline constexpr fp16 array literals (BLOBFILE is the accepted weight carrier); every rejection carries the SAME opaque signature 'ANECCompile FAILED: err=(InvalidMILProgram)' with zero op attribution, and out-of-range BLOBFILE weight offsets produce the identical signature — the one-feature-per-process battery is therefore the only attribution instrument at this door.","kind":"measurement","confidence":"measured","source":"results/EXP-032-pulse-map/harness/mil_battery.m + run_battery.py; matrices mil_battery_matrix_studio.jsonl (fingerprint bda452aabd60bf26, commit 893326b) + mil_battery_matrix_mini.jsonl (fingerprint 057b28dd036ddbe8)","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","mil","compiler","op-grammar","m5","m4","hollance44"],"entities":["_ANEInMemory","ANEBridge","ANECCompile","InvalidMILProgram","reduce_mean","reduce_sum","slice_by_index","gelu","softmax","BLOBFILE","hollance-44","EXP-026 K2"],"evidence":"20-JSON-row matrices per machine with per-case error strings and geometry stamps; cross-machine delta set empty (python diff, 20/20); EXP-026 README K2 addendum carries the full accept/reject table","caveat":"compile-stage verdicts only — accepted programs' runtime numeric correctness not re-established here (softmax non-pow2 accepted at compile may still land in the runtime instability class); MIL surface probed is the subset reachable from the proven ctx grammar; the 'op absent' readings are relative to this door/OS (legacy C door and MilAneflow are different grammars)","contested":false}
{"id":"MEASURE-157","claim":"The compiled ANE program artifact on the _ANEInMemory path is world-readable WITHOUT sudo via the client's own tmpDir even though aned's cache volume is mode-blocked: compiles stage $TMPDIR/<A>_<B>_<C>/ containing model.mil, a byte-identical net.plist, weights/weight.bin, and 'data' — the compiled program blob (17,408 B for the 128x64x128 conv pair) — where A = SHA256(model.mil) uppercase (this is the hexStringIdentifier, verified byte-exact 3/3 cases), C = SHA256(empty string) uppercase, and B is constant across programs sharing identical weight bytes yet differs from SHA256(weight.bin) (descriptor-class hash, formula unresolved); /Library/Caches/com.apple.aned itself returns EPERM to unprivileged ls and every aned log path renders <private> at --info level; the compiled 'data' blob reuses the RUNTIME-013 weight-container grammar exactly: 64-byte file header (u32[0]=chunkCount=6, u32[1]=2) then six DEADBEEF(efbeadde)-marked 64-byte chunk records whose payload sizes (8192/64/128/8192/64/128) mirror the input int8 weight regions W1/zp/scale per conv layer, with per-chunk type field (4 = weight-class, 1 = scale/metadata-class) and rising d3 offsets, the chunk walk closing exactly at EOF.","kind":"measurement","confidence":"measured","source":"results/EXP-032-pulse-map/raw/c71_blob/ (c71_aned.log + data + model.mil + net.plist + NOTES.md); harness runs 2026-10-23T14:36 local","source_type":"our-own","retrieved":"2026-10-23","topic":["ane","compiled-program","blob-format","tmpdir","observability","m5"],"entities":["_ANEInMemory","hexStringIdentifier","DEADBEEF","RUNTIME-013","/Library/Caches/com.apple.aned","net.plist","ANEBridge","ane_bridge_compile"],"evidence":"hash crack 3/3 cases (python, uppercase sha256 vs dir components); format walk parse closing at 0x4400=17408 EOF; cmp model.mil net.plist identical; EPERM ls captured in NOTES; StatsMask=0 coreAnalyticsClientType=ThirdPartyAppUsingANE line witnessed for the unsigned battery client","caveat":"naming crack verified for this bridge's invocation pattern (fresh process, _exit teardown preserving dirs) — aned's own /Library cache layout remains unseen (EPERM + privacy-redacted, sudo/SIP session reserved for EXP-031 pack); component-B hash formula open; type-field semantics inferred from one program family (conv/int8), other op classes unprobed","contested":false}
```

## Provenance

- Captures: `results/EXP-032-pulse-map/raw/` (18 enginemon streams + 16 work logs),
  2026-10-23T11:34–11:40Z session; enginemon v2.1 rebuilt in-tool this session.
- Workload builds: ncm-run workspace commit e7536a5, release; stamped ledgers listed
  in ANALYSIS-C67 §Protocol (studio 11-34/11-35/11-37Z-bda452aabd60bf26; mini
  11-39-23Z-057b28dd036ddbe8 on-box + stdout witness fetched).
- Bench sanity run before timing windows per box-journal rule.
- Cross-links: doc 10 (M5 attribution signals), doc 12 (why kANE is policy-locked;
  CORE-009), MEASURE-012 (M4 CoreML interrupts), MEASURE-152 (ANEXL U existence).

> **2026-10-23 (EXP-034):** the door's payload is now partly decoded and era-keyed —
> `DeviceProperties` unprivileged (single key `ANEDevicePropertyNumANEs=1`), sel-0 field
> offsets corrected in doc 14 addendum, and the daemon-mediated-only status re-opened as
> *unproven, not proven-absent*; EXP-025's `_ANESharedEvents` mailbox is the named
> daemon-free side-door pending the chaining-blob parse. See
> `results/EXP-034-full-access/README.md`, doc 14 addendum, MEASURE-162/163.
