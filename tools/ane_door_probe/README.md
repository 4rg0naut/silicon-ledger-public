# ane_door_probe — EXP-032 C-69 (2026-10-23)

Can a plain (unsandboxed, uid-501, no-entitlement) process reach the ANE IOKit
door on macOS 27.0.1 / M5 Max? **Yes — via the load balancer, not virtio.**

Build (all tools, same recipe):

    clang -O2 -o main main.c -framework IOKit -framework CoreFoundation   # -> ane_door_probe
    clang -O2 -o probe2 probe2.c -framework IOKit -framework CoreFoundation
    clang -O2 -o roundtrip roundtrip.c -framework IOKit -framework CoreFoundation
    clang -O2 -o hold hold.c -framework IOKit -framework CoreFoundation
    clang -O2 -o whoami whoami.c -framework IOKit -framework CoreFoundation
    codesign -s - -f <each>   # ad-hoc re-sign after any rebuild

Findings (raw captures: `results/EXP-032-pulse-map/raw/c69_doorprobe/`):

- `AppleVirtIONeuralEngineDevice` (the class `AppleNeuralEngine.framework`
  opens, C-68) has **zero instances** on this bare-metal host — VM-guest door.
- `IOServiceMatching("ANEDriver")` → `ANEDriverRoot` answers unprivileged
  `IOServiceOpen` at exactly **two of 70 probed types (1, 4)**; both create
  server-side `H1xANELoadBalancerDirectPathClient` — the same class
  `mediaanalysisd` holds ×8. `aned` holds one `H1xANELoadBalancerClient`
  (not producible unprivileged from any probed type).
- One harmless round-trip (selector 0x12, 1-in/8-out scalars, type-1 conn):
  `kIOReturnBadArgument` — live kernel dispatch, wrong selector table
  (0x00–0x1e is the framework's virtio grammar, not the load-balancer's).
- Client objects vanish cleanly at close (zero residue).
- `H11ANEIn` (hardware nub under `ane0@8000000`) accepts no probed open type.
- Direct-path selector grammar of the type-1 table remains unexplored
  (kext crossmap NOT-REACHABLE: no kernelcache file on this SPTM-era OS).

Claims: MEASURE-155, CORE-010 (corrected) — see `knowledge/ane/13-pulse-map.md`.

## probe10_loadsweep — EXP-036 C-87 load-then-sweep (2026-10-25)

`probe10_loadsweep.m`: in-process compile+load via ncm-run/bare ANEBridge (`baseline.mil`,
blob2 int8 weights), then three full 11-selector sweeps on one type-1 conn (bogus-handle
pre-fill control, post-load zero, post-load live handle) + probe8's sel-2 Gate-A ladder.
Build line in file header; run from this dir (needs `baseline.mil`). Verdict + claims:
`results/EXP-036-side-door-inject/` (MEASURE-164/165): door CONFIRMED LOAD-BLIND for
unprivileged clients, 3/3 runs, zero residue. `probe10` also exposed the sel0 input-echo
grammar (MEASURE-165). Residue witness recipe: `ioreg -rc H1xANELoadBalancerDirectPathClient
| grep -c class-io-service` around the run.
