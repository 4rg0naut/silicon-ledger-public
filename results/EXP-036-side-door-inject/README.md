# EXP-036 — Side-Door Injection Verdict: direct-path door CONFIRMED LOAD-BLIND (C-87 closed negative)

Campaign: **EXP-036 side-door-inject** (2026-10-25, studio M5 Max Mac17,14, macOS 27.0.1/26A434,
fingerprint `bda452aabd60bf26`). Predecessor: EXP-035 `results/EXP-035-chaining-blob/CAPTURE.md`
tail, which named the last untested setter as a bounded load-then-sweep of direct-path selectors
2–10 ("C-87 candidate"). This campaign RUNS that experiment and closes the named gap.
Owner ask behind it: can an unprivileged client push a program/chaining (weight-injection lane)
through the direct IOKit door after loading a program in-process, or is the door load-blind for us?

## Headline verdict

**CONFIRMED LOAD-BLIND — clean negative, 3/3 runs.** In-process compile+load of a real program
(handles minted 131251/131285/131303, all `state=3` loaded) changes the kr signature of **zero**
of the 9 unmapped direct-path selectors (2–10) on our type-1 `H1xANELoadBalancerDirectPathClient`
connection. The sel-2 Gate-A signature stays `0xe00002c2` for every arm including a fresh live
handle (P1-live), exactly reproducing EXP-035 probe8/probe9. No Gate-A setter exists inside the
11-entry `_sANEDriverDirectPathClientMethods` table. Per the pre-declared decision line in
CAPTURE.md: the direct-path door is closed for daemon-free program submit / weight refresh by
unprivileged clients, and the daemon-free lane is now officially the EXP-025
`_ANESharedEvents`/IOSurface mailbox (~62 µs hop). No entitlement spend was attempted.

Claim: MEASURE-164. Grammar refinement (sel0 echo attribution) in MEASURE-165 — appended to
`knowledge/ane/14-door-map.md` dated addendum.

## Experiment

Harness `harness/probe10_loadsweep.m` (built against `ncm-run/bare` ANEBridge, ad-hoc signed;
build line in file header). Per run, on ONE type-1 door connection:

1. `pre-load-handle-bogus` — CONTROL added after first run: fill structIn `+0x10` with a bogus
   same-magnitude handle (0x2000f, never loaded) and `+0x38` with 1 (poison-first discipline,
   EXP-031 C-64 rule: attribute offset semantics only via a fill that changes outcome).
2. `pre-load` — full 11-selector sweep, zeroed inputs, contracts from the 26A434 kext decode
   (probe4_grammar table).
3. **Load**: `ane_bridge_compile` + in-process load of `baseline.mil` (EXP-032 proven grammar),
   weights via `ane_bridge_build_int8_weight_blob2`; read back `programHandle` + `state`.
4. `post-load` — identical sweep again, same connection.
5. `post-load-handle` — sweep with the LIVE handle at `+0x10`, cnt=1 at `+0x38`.
6. Gate-A control ladder (probe8 canonical): sel-2 `N-zero` / `B-bogus` / `P1-live`.

Zero-residue witnesses: `ioreg -rc H1xANELoadBalancerDirectPathClient` instance count before and
after every run: **0 before, 0 after, all 4 invocations** (incl. the initial pre-control run).
Prewitness (`raw/prewitness_smoke.txt`): fresh clang rebuild + re-sign of probe4_grammar on
26A434 (contract-build match in `raw/prewitness_env.txt`); open kr=0, sel0 kr=0 (capability
words reproduce the EXP-034-corrected layout: 4 GiB/16 GiB at `+0x50`/`+0x60`, u32 1/4 at
`0x54`/`0x64`), sel1 kr=0 — door alive and grammar unchanged since 2026-10-23.

## Results (raw: `probe10_sweep_run1..3.jsonl`, plus initial run `probe10_sweep.jsonl`; analysis `raw/analysis.txt`)

| Question | Answer |
| --- | --- |
| Any kr delta on selectors 2–10 pre vs post load (or vs bogus-fill)? | **No** — 36/36 selector-phase cells identical across 3 runs (era codes: 2,3,4,5,7,8,9,10 `0xe00002c2`; 6 `0xe00002f0`) |
| Gate-A move with live handle? | **No** — sel-2 `0xe00002c2` on N-zero, B-bogus, P1-live, 3/3 runs; handle fresh-minted seconds earlier in the same process |
| Load attested? | **Yes** — `state=3`, kernel-minted sequential handles (131251/131285/131303); framework path unchanged from probe7/probe8 |
| sel0 output deltas? | **Fill-attributable only** (MEASURE-165): handler echoes caller input `+0x10` u64 and `+0x38` u32 verbatim into the output — appears identically with the pre-load BOGUS handle and with live handles (value tracks whatever was filled), capability words unchanged. No handle-validity semantics; nothing unlocked. |
| Door latency | 0.5–8.0 µs per call — consistent with MEASURE-161 band (1.2–7.1 µs); dispatch cost is not the blocker |
| Residue | Zero, every run |

## What this settles (and what it does not)

- **Settles**: the C-87 lead is dead within the direct-path table — no per-selector setter for the
  Gate-A credential exists for unprivileged clients on this door. ncm-run backlog §IOKit item 1
  ("door-side weight mutation NOT established; do not plan around it") upgrades from *unproven*
  to *measured negative*: an unprivileged weight-injection lane through this door is **closed**.
- **Does not settle / does not revoke**: the door itself remains open, sandbox-proof and cheap
  (EXP-033); the mailbox lane (EXP-025) remains the named daemon-free transport for consumers;
  a future entitlement grant (owner-gated, not tested here — pickpocket is AMFI-fatal, EXP-031)
  re-opens the question; the 120-load process-slot budget and OS-build scoping of all contracts
  still apply (26A434 only — re-run prewitness after any OS update).
- **For the NCM program**: ANE *training* stays where it was after EXP-035/night_index C7 —
  descriptor-recompile weight swap (<300 ms) or weights-as-inputs; the door side-door does NOT
  provide the hot-reload that would make ANE a training lane. Cost tables unchanged.

## Addendum 2026-10-25 — owner-run sudo arm (`raw/sudo_probe9_owner_20261025.txt`)

Root attains **no more than uid 501**: type 2 (and 0/3/5/8/16) stay `0xe00002c7`
`kIOReturnNotPrivileged` under `sudo` — the client-class gate keys on signing identity,
not uid. The self-run-root-daemon sidecar theory is CLOSED at the same Mach-permission
layer; entitlement/Apple-internal signing is the only known path to the type-2 class.
Bonus measurement: this is the first direct **type-4 ≡ type-1 equivalence** on the sel-2
ladder (zero/live/bogus arms byte-identical kr + oSz + poison round-trips); EXP-033 had
only established both spawn the same class. Load as root fine (handle 133260, state=3).

## Honest caveats

- One OS build (26A434), one client class reachable (types {1,4}); type-2 (aned's class)
  remains NotPrivileged (probe9) — verdict scoped to unprivileged reachability, not to the
  kernel's whole enforcement.
- Gate-A attribution is by elimination: the setter is not among the 11 direct-path entries;
  its exact mechanism (set by `newUserClient type=2` path on `ANE_AddClientForProgram` or by
  the entitlement check upstream of it) stays unmapped — callee-level, not source-level.
- sel0 echo was first misread at offset +0x18 during live analysis (two-hex-digit
  index slip); corrected here to the fill offsets +0x10/+0x38, with the bogus-fill control as
  proof. Raw jsonl unchanged; analysis reflects corrected offsets.

## Repro

```sh
cd tools/ane_door_probe
BARE=/data/OpenFox/AI_dev/ncm-run/bare
clang -fobjc-arc -O2 -o probe10_loadsweep probe10_loadsweep.m "$BARE/Sources/ANEBridge/ane_bridge.m" \
  -I "$BARE/Sources/ANEBridge/include" \
  -framework Foundation -framework IOSurface -framework IOKit -lobjc
codesign -s - -f ./probe10_loadsweep
ioreg -rc H1xANELoadBalancerDirectPathClient | grep -c class-io-service   # expect 0 (or pre-count)
./probe10_loadsweep > raw.jsonl   # 4 sweeps + load + 3 arms, then close
cd - && python3 results/EXP-036-side-door-inject/harness/analyze_sweep.py
```

## Contents

- `raw/prewitness_env.txt` — OS/machine/contract-build match (26A434)
- `raw/prewitness_smoke.txt` — fresh-built probe4_grammar live verdicts (door-alive witness)
- `raw/probe10_sweep_run1..3.jsonl` — full kr/latency/output matrices (3 runs)
- `raw/probe10_sweep.jsonl` — initial run (pre-control version), kept as failure-mode evidence
- `raw/probe10_stderr_run*.txt`, `raw/residue_pre*.txt`, `raw/residue_post*.txt` — witnesses
- `raw/analysis.txt` — cross-run comparison + verdict lines
- `harness/probe10_loadsweep.m`, `harness/analyze_sweep.py` — sources (private per PUBLISH-POLICY)

Session: 7bd7466c-eab5-4226-ab9f-a04212fdddef
