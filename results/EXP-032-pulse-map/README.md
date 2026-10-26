# EXP-032 — Pulse Map: per-eval observability, kernel door, MIL grammar, compiled blob (M5 Max + M4 mini)

**Status:** COMPLETE 2026-10-23. Campaign: ncm-run EXP-032 (home base claims;
ncm-native 029/030 untouched — see namespace row in `results/README.md`).
**Machines:** Mac17,14 M5 Max · macOS 27.0.1 (26A434) join key `bda452aabd60bf26`;
Mac16,10 M4 mini `057b28dd036ddbe8`.

## Headline numbers

| finding | number | claim |
| --- | --- | --- |
| M5 ANE interrupt counters at user level | **0 fires / 190,000 evals** across both client paths (70k direct-API anectx + 120k CoreML preds, ANE busy confirmed same captures) | MEASURE-153 |
| M4 same binary/workload | 29,299 fires = **1.465/eval** (idle bookend 2/9.1 s) | MEASURE-153 |
| M5 per-eval counter that works unprivileged | PMP0 **SOC-NI9 "ANEXL U"**: 0.488–0.503/eval (S=32 parity, ±1.5%), 1.00–1.06/eval (S=160 field, ±3%), 2.889–2.915/pred (CoreML minilm128, ±0.5%) | MEASURE-154 |
| Third-party `IOServiceOpen` on the live host door | **Y** — `ANEDriver` answers unprivileged at open types **1 and 4 of 70 probed**, creating `H1xANELoadBalancerDirectPathClient` (production class, `mediaanalysisd` holds ×8); type-0 (framework path) and every other type: `kIOReturnUnsupported` | CORE-010, MEASURE-155 |
| One harmless round-trip | dispatches: selector 0x12 → `kIOReturnBadArgument` (live kernel, wrong table) | MEASURE-155 |
| Framework door class `AppleVirtIONeuralEngineDevice` | **zero instances on-host** — VM-guest door; C-68 selector map (eval=0x13/16B) is the guest grammar | CORE-010 |
| raw-MIL battery (20 cases, `_ANEInMemory`, fresh process each) | **12 ACCEPT / 8 REJECT, verdicts identical M5 Max ↔ M4 mini**; hollance-44 #1 (softmax non-pow2) does NOT reproduce at compile; #3 (`reduce_mean`) confirmed absent, workaround rule = `reduce_sum` needs explicit `axes`+`keep_dims`; `slice_by_index` absent in all forms (#2 broader); `gelu` absent (tanh OK); fp32 io rejected; Cin 1088/1200 ACCEPT at compile (alignment cliff is runtime-only) | MEASURE-156 |
| Every compile rejection signature | **one opaque string** (`err=(InvalidMILProgram)`), shared even by out-of-range BLOBFILE offsets — battery is the only attribution instrument | MEASURE-156 |
| Compiled-program blob | **readable unprivileged** via client tmpDir: `<SHA256upper(model.mil)>_<B>_<SHA256upper("")>` dirs, `data` blob reuses RUNTIME-013 container (DEADBEEF chunk records mirroring weight regions 1:1); `/Library/Caches/com.apple.aned` EPERM + log paths `<private>` | MEASURE-157 |

## C-69 verdict lines (criterion wording)

- **Part 1 (enumerate + open, benign props): DONE, Y** — plain uid-501
  unsandboxed C tool enumerates every ANE class, reads props, and OPENS the
  production service without root/entitlement (types 1/4 → DirectPathClient).
  The Asahi-path question's first half: third-party code CAN hold a direct ANE
  kernel client on this OS/host.
- **Part 2 (one round-trip, conditional on C-68): DONE, Y** — single scalar
  `IOConnectCallMethod` returns BadArgument = live dispatch; the round-trippable
  selector grammar of the direct-path table remains open (kext NOT-REACHABLE:
  no kernelcache file on SPTM-era 27.0.1).
- Negatives recorded (virtio-class absence, kext extraction) are findings, not
  failures — documented in `harness/`/`raw/c69_doorprobe/` + doc 13; no new
  FAILURES.md row needed (no wrong assumption was load-bearing).

## Artifacts

- `pulse_table.tsv` — per-eval joined table (captures × stamped ledgers).
- `raw/` — 18 enginemon jsonl (idle/workload bookends), work logs, `ane_dsc.asm.gz`
  (26A434 shared-cache disasm, 108,871 lines), `ios_callsites.tsv` (29/29 sites),
  `c69_doorprobe/` (open-type matrix, creator diffs, hold logs),
  `c71_blob/` (compiled `data` + `model.mil` + `net.plist` + log capture + NOTES).
- `harness/` — `mil_battery.m` + `run_battery.py` (INSTR-152/153; citation re-pinned 2026-10-26
  after the append-only-registry fix — earlier text carried a drifted renumber-era id).
- `mil_battery_matrix_{studio,mini}.jsonl` — 20 rows + provenance each.
- Knowledge: `knowledge/ane/13-pulse-map.md` (Q1–Q4 + Claims
  MEASURE-153/154/155/156/157 + CORE-010 corrected). EXP-026 README carries the
  K2 accept/reject addendum (C-70 gate).

## Repro

    # per-eval counters (studio/mini)
    tools/enginemon/enginemon --interval 100 --json > cap.jsonl &   # see README addendum
    (cd <workspace> && ./ncm-run/bare/.build/release/ncm0 anectx --iters 20000)
    # door probe
    clang -O2 -o tools/ane_door_probe/probe2 tools/ane_door_probe/probe2.c \
      -framework IOKit -framework CoreFoundation && ./tools/ane_door_probe/probe2 --scan-types
    # MIL battery
    python3 results/EXP-032-pulse-map/harness/run_battery.py   # NCM0=<ncm0> for fingerprint

Caveats: single OS build (26A434); SOC-NI9 is a whole-engine lane (multi-client
attribution stays ambiguous, EXP-022 class); battery = compile-stage verdicts;
component-B hash (C-71) open. Push owner-held.

> 2026-10-26 packaging note: `raw/` jsonl + `ane_dsc.asm` gzip-compressed (44 MB → 4.8 MB, repo
> convention per EXP-031); read with `zcat`. `raw/MANIFEST.sha256` generated and verified post-hoc.
> Emitted claims (CORE-010) keep their historical pre-`.gz` path strings — append-only spine.
