# EXP-031 — Unlock the odometer: who zeroes your ANE statsMask (EXP-031 namespace: perf-stats forensics)

**Date:** 2026-10-23. **Machine:** M5 Max Mac17,14 (fingerprint `bda452aabd60bf26`),
macOS 27.0.1 / 26A434; cross-check M4 mini Mac16,10 (`057b28dd036ddbe8`), same OS build.
**Provenance:** studio ncm workspace tip `d8095d0` (release build of `ncm0`,
`ncm-run/bare`), aned slice `otool -tV` (`raw/aned.text.asm.gz`, 132,380 lines,
sha256 in `raw/MANIFEST.sha256`). Prior chain: EXP-024 B5 (counter names) →
EXP-029 (harness, size=0 finding, ncm-run side) → EXP-030 (bit-identity, ncm-run side).

## Question

EXP-029 measured that the driver hands our `_ANEInMemory` client a
**zero-length perf-stats buffer** (kANE counters unreachable, rc=138 in the
loaded-model context). External reports (tmc/apple, Bryngelson arXiv:2606.22283
§33.3, maderix) all point at a `statsMask` cleared for unentitled clients.
Unverified links: (1) what field feeds the client classification, (2) whether
the gate is entitlement-key presence (copyable) or platform identity
(not copyable), (3) where the mask actually zeroes.

## Method + findings (details: `knowledge/ane/12-perfstats-and-entitlements.md`)

1. **Live witness (unprivileged):** aned logs, in cleartext, for every load:
   `coreAnalyticsClientType=ThirdPartyAppUsingANE StatsMask=0`. Captured for
   **three client classes on the same box**: our private-API ncm0
   (`raw/logA-ncm0-aned.log`), vanilla CoreML `MLModel`
   (`raw/logB-coreml-aned.log`), CoreAI `GraphModel` 200-eval run
   (`raw/logF-coreai-aned.log`). Identity inputs themselves are `<private>`
   without a sudo `log config` (no unattended sudo on this box — honest gap);
   the debug line `SecTaskCopyTeamIdentifier() returned teamIdentity=""`
   confirms ad-hoc clients present an empty team.
2. **Disassembly walk** (`raw/aned.text.asm.gz`, addresses in doc 12 §Q3):
   XPC-acceptance gate = entitlement presence + `boolValue` (@0x10000e4bc,
   soft, never fires against us). Inside `loadModel`, the client's
   `kANEFPerformanceStatsMaskKey` is translated via
   `+[ANEPerformanceStats driverMaskForANEFMask:]` and forwarded to the kernel
   **unconditionally** — the zero lives in that framework-side translation or
   the IOKit path, not in an aned branch. Classification value comes from
   `+[__ANEDataReporter reportClient:modelName:]` fed by the XPC audit-token
   **signing identity** (`SecTaskCopySigningIdentifier`,
   `+[__ANEModelToken teamScopedCodeSigningIDFor:processIdentifier:]`
   @0x10001d448).
3. **Soft-or-hard verdict (C4):** acceptance gate soft; **perf-stats
   classification identity-bound = hard for third parties**. The observable
   label is written by the server from your code signature; you cannot request
   your way in.
4. **Pickpocket test (C5, negative = passing):** ad-hoc re-sign `ncm0` with
   candidate entitlements → AMFI kills both ANE-feature keys
   (`com.apple.ane.iokit-user-access`, `com.apple.ANECompilerService.allow`)
   with `rc=137 "code signature validation failed fatally"`;
   only `com.apple.security.*` survives ad-hoc; the surviving-key build runs
   the field lane identically (median 320.1 µs, parity counters unchanged) and
   the kANE probe is unchanged: `size=0`, `rc=138`, same
   `ThirdPartyAppUsingANE StatsMask=0` — on **both** boxes
   (`raw/kane-run-c5-signed-studio.txt`, `raw/kane-run-c5-signed-mini.txt`,
   `raw/logD-c5-signed-aned.log`, `raw/logE-mini-c5-aned.log`).
   Failures entry: `FAILURES.md` → F-ane-perfstats-pickpocket.
5. **Dev-team escalation (C-63 kit, ran 2026-10-23 12:53 local):** owner
   provisioned a free-Apple-ID "Apple Development" identity (WWDR **G3**
   intermediate was missing from the keychain — imported from
   apple.com/certificateauthority; in zsh use `/usr/bin/log`, the `log`
   builtin shadows it). `dev/ane_teamid_test.sh` signed the scratch binary
   (`Authority=Apple Development: <user>knight@mailbox.org (989JU35U77)`,
   `TeamIdentifier=G7Z3WCMGZ6`, chain to Apple Root CA) and re-ran the kane
   probe: **identical outcome** — `ThirdPartyAppUsingANE StatsMask=0` at the
   12:53:45 loadModel, kANE `t0.5 size=0`, SIGBUS in the factory handshake
   (`raw/kane-run-devteam-studio.txt`, `raw/logG-devteam-aned.log`).
   Verdict: a non-empty team ID does NOT promote the class; per-eval counters
   require Apple-platform entitlement. Unlock candidate (e) CLOSED
   (claim CORE-009). Note: key-use from a headless session raised a keychain
   consent dialog — refused once by owner by design; the kit is meant to be
   run in the owner's own terminal.

## Headline numbers

- 3/3 unentitled client classes → `coreAnalyticsClientType=ThirdPartyAppUsingANE`,
  `StatsMask=0` (macOS 27.0.1 both fleet boxes).
- 2/2 ANE-feature entitlements AMFI-restricted under ad-hoc signing (rc=137);
  dev-team escalation subsequently RAN (2026-10-23 evening): free-Apple-ID
  developer signature, `TeamIdentifier=G7Z3WCMGZ6` → still
  `ThirdPartyAppUsingANE StatsMask=0`, kANE size=0 — no non-Apple route
  promotes the class (CORE-009).
- aned userspace forwards the mask to kernel unconditionally: 0 conditional
  branches between the mask install (@0x10001cee4) and the kernel handoff
  (@0x10001f290); remaining zero-candidates: framework `driverMaskForANEFMask:`
  table or IOKit `initStatsBufferSection` (needs sudo to separate).

## Open after this campaign

- (c) kernel/IOKit trace to split framework-table vs kernel zero (sudo).
- (d) whole-engine channel naming (Bryngelson §33.3 unentitled-readable claim —
  still unreproduced by tmc and by us; enginemon/PMP0 lane remains our hedge).
- ~~(e) owner-provisioned dev-team signature → does any non-empty team
  promote?~~ **CLOSED 2026-10-23: NO — dev-team signature classified
  `ThirdPartyAppUsingANE StatsMask=0`, size=0 unchanged (Method-5, CORE-009).
  The entitlement wall is now mapped end-to-end: ad-hoc (Method-4) and
  dev-team (Method-5) both fail; only Apple-platform entitlement remains,
  untestable by us. Remaining opens are (c) kernel forensics and (d) channel
  naming, neither of which changes the verdict.**

## Publish triage (PUBLISH-POLICY)

Publishable distilled (no secrets, all first-party measurements + public OS
binary disassembly): headline numbers, client-classification finding, AMFI
bisect table, platform device string (h17c). Private: full aned disassembly
dump (bulk, tooling artifact), workspace paths. Distill don't push — owner
decides what lands in `4rg0naut/silicon-ledger-public`.

## Files

- `raw/logA-ncm0-aned.log` … studio kane baseline window (08:25:48–08:28:10Z)
- `raw/logB-coreml-aned.log` … CoreML client window
- `raw/logD-c5-signed-aned.log` … signed-re-sign probe window (studio)
- `raw/logE-mini-c5-aned.log` … mini C5 window (filtered)
- `raw/logF-coreai-aned.log` … CoreAI client window
- `raw/logG-devteam-aned.log` … dev-team signature window (12:53 local, 2026-10-23)
- `raw/kane-run-devteam-studio.txt` … dev-team kane probe stdout (Method-5)
- `raw/sip-prep/` … Thread-1 kernel-trace prep pack (Act-0 checklist + lldb file)
- `raw/aned.text.asm.gz` + `raw/MANIFEST.sha256` … full otool -tV arm64e dump
- `raw/kane-run-*.txt` … probe transcripts, three arms
- `raw/coreai-client-run.txt`, `raw/coreml-client-run.txt` … client workloads
- `raw/*.plist` … the three entitlement plists used
