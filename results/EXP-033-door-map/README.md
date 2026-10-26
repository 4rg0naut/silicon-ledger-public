# EXP-033 — Door Map: fleet/sandbox door matrix, offline kernelcache, direct-path grammar (M5 Max + M4 mini)

Campaign: **EXP-033 door-map** (2026-10-23, studio M5 Max Mac17,14 + mini M4 Mac16,10,
macOS 27.0.1/26A434 both). Knowledge doc: `knowledge/ane/14-door-map.md` (Q1–Q5).
Predecessor: EXP-032 pulse-map (this campaign closes its two open caveats: M4 door
matrix and sandbox context — and supersedes its own kext NOT-REACHABLE verdict).
Prior art credited: BlackStorm ER-10 (Borges, 2026-10-06) first published door
openability (iOS {1,4}); Phrack #72 "Mapping IOKit Methods Exposed to User Space
on macOS" (Mazurek, 2025-08-19) published the method-mapping methodology with the
H11ANEIn class family as worked example — our grammar delta is the
H1xANELoadBalancerDirectPathClient door class on M5/26A434 (see doc 14 Q4 note,
2026-10-23); mrmacintosh restore DB + `ipsw` make the kernelcache routable;
hollance/Orion/maderix/tmc per `knowledge/ane/SOURCES.md`.

## Headline verdicts

| Question | Verdict | Claim |
| --- | --- | --- |
| Q1 Door identical across fleet? | **Y** — types {1,4} on M5 Max AND M4 mini, 68 other types `kIOReturnUnsupported`, zero residue both | MEASURE-158 |
| Q2 App sandbox blocks it? | **NO** — sandbox enforced (container HOME, EPERM witnesses) yet {1,4} still open, both machines; no iokit-user-client entitlement needed | MEASURE-158 |
| Q3 Kext offline-reachable? | **Y (EXP-032 verdict superseded)** — `ipsw download ipsw --macos --version 27.0.1 --kernel --extract-device Mac17,14`, exact build 26A434, kext versions == kextstat (10.19.2), ~6 min, no sudo | MEASURE-159 |
| Q4 Selector grammar? | **Mapped** — `_sANEDriverDirectPathClientMethods`, 11 entries x 40 B contracts; LIVE: sel0 SUCCESS (136B roundtrip, caps u64@88=1/u64@112=4), sel1 SUCCESS, sel6 NotReady; EXP-032's "wrong table" reading corrected (out-of-bound) | MEASURE-160 |
| Q5 What does it cost? | **1.2–7.1 µs** dispatch round-trip (~20x below daemon hop); program submit parked at payload token forge; weight-mutation trio absent from door table | MEASURE-161 |

## Repro

```sh
# fleet/sandbox matrix (studio + mini)
cd tools/ane_door_probe && clang -O2 -o probe2 probe2.c -framework IOKit -framework CoreFoundation \
  && codesign -s - -f ./probe2 && ./probe2 --scan-types
# sandboxed context: bundle + app-sandbox entitlement + open -W (probe3_sb.c header)
# kernelcache (route A):
ipsw download ipsw --macos --version 27.0.1 --kernel --extract-device Mac17,14 -y -o raw/kext
# grammar live verdicts:
clang -O2 -o probe4_grammar probe4_grammar.c -framework IOKit -framework CoreFoundation \
  && codesign -s - -f ./probe4_grammar && ./probe4_grammar
```

## Caveats (honest list)

- One OS build (26A434); contracts hardcoded in probe4 must be re-decoded after OS update.
- Handler semantics from callee symbols, not source; capability fields uninterpreted.
- Submit path parked: client token forge (`ANEClientInfo::create`, `_ANEProcedureData`)
  is the named next step — not attempted blind-fuzzing (budget).
- Engine-side attribution: ambient ANE DCS (~30 MB/s background) confounds per-call
  engine counters; verdicts rest on kr codes + zero-residue witnesses.
- Sandboxed client-class identity assumed = unsandboxed result (creator-diff not re-run
  in sandboxed context).

## Publish triage (PUBLISH-POLICY)

Publishable distilled (no secrets, first-party measurements on public OS
binaries, prior art credited): the macOS door characterization
(`ANEDriver`/ANEDriverRoot, unprivileged + sandbox-surviving), the iOS/macOS
**{1,4} type-pair convergence** (credited to BlackStorm ER-10, Borges
2026-10-06, for first iOS publication; our delta = fleet × sandbox ×
class-attribution matrix), the Phrack #72 methodology credit with our
LoadBalancer-class delta, the tmpDir **world-readable compiled-blob
leakage note** (EXP-032 C-71 lineage: any local process can read compiled
ANE program artifacts under the client tmpDir — privacy-relevant), and
headline latencies. Private by policy: `raw/kext/*.asm` bulk dumps and
harness `.c`/`.py` under `results/**/harness|raw/kext` stay private per
policy (prose pointers suffice); kernelcache blob itself is gitignored
regenerable. Distill don't push — owner decides what lands in
`4rg0naut/silicon-ledger-public`.

## Contents

- `raw/door_matrix.tsv` + 4 raw captures + `ioreg_zero_residue_witness.txt` (C-73)
- `raw/kext/PROVENANCE.md` + `kernelcache.sha256` (blob gitignored) + `kexts/` extracted
  kext + `deep_sel*.asm` + `live_grammar*.txt` + `selector_matrix.tsv` + scripts (C-74/75)
- `c76_directpath_parked.json` — stamped parked ledger with per-call µs (C-76)

## Addendum 2026-10-23 (EXP-034 follow-up)

- **Corrections applied here-by-reference** (details + evidence in
  `../EXP-034-full-access/README.md` + doc 14 dated addendum): sel-6 live code is
  `kIOReturnNotFound` (0xe00002f0), not NotReady; "u64@88=1/u64@112=4" were mislabeled
  — true words u32@0x54=1 / u32@0x64=4 with u64@0x50/0x60 carrying 4 GiB / 16 GiB(studio)
  / 10 GiB(mini).
- **EXP-025 cross-link (package-only restriction re-opened as daemon-mediated-unproven):**
  this campaign proved the unprivileged direct client exists and persists; what it does
  NOT prove is that nothing is enforced there. "Third-party eval must go through aned" is
  therefore **daemon-mediated, unproven-as-a-kernel-rule**. The daemon-free GPU↔ANE
  signalling half of that door is already measured in-house: EXP-025's
  `_ANESharedEvents`/`IOSurfaceSharedEvent` mailbox (~62 µs hop) — the same machinery
  sel-1's `retainSharedEvents` callee arms — is the named side-door for consumers while
  the sel-2 chaining blob stays unparsed (`../EXP-034-full-access/c80_chaining_parked.json`).
