# SIP-session prep pack — Thread 1: framework-table vs kernel zero

Prepared 2026-10-23 (Builder pass after EXP-031 close). Nothing here has been
executed against `aned` yet — first live use is the owner's sudo/SIP-relief
session. Feasibility facts (SIP full, `ioreporter` absent on 27.0.1) are in
`knowledge/ane/12-perfstats-and-entitlements.md` §Q5 addendum — read that first.

Goal (doc 12 §Q3 open [U]): determine WHERE the third-party statsMask becomes
0 — inside `+[ANEPerformanceStats driverMaskForANEFMask:]` (AppleNeuralEngine
framework translation table) or in the kernel driver (`initStatsBufferSection`,
IOKit path). A poison value distinguishes them unambiguously.

## Act 0 — attach feasibility (test this BEFORE anything else)

```
sudo lldb -p $(pgrep -x aned) -o "image list -o aned"
```

- `aned` is a hardened platform binary and demand-spawned by launchd.
  Measured 2026-10-23 in the agent session: debugserver attach is refused
  even for the session's OWN freshly-spawned binaries (`attach failed (Not
  allowed to attach to process)`) — sudo is required for lldb here
  regardless of SIP state. If attach stays refused under sudo, boot a
  recovery session and enable debug only (keeps filesystem/seal protection):
  `csrutil enable --without debug` (fallback: `csrutil disable`), reboot,
  retry. Do NOT stay in a relaxed-SIP boot longer than the session.
- While `aned` is stopped at a breakpoint, ALL ANE clients on the box stall —
  keep agent workloads off the machine or pause them; the field probe below
  takes ~2.5 min of client time.
- If lldb is hopeless, fallback per external report: dtrace IOKit probes
  (`/usr/sbin/dtrace` present; untested for this purpose on 27.0.1).

## Act 1 — module slide

The `otool -tV` walk addresses (doc 12, EXP-031 raw `aned.text.asm.gz`) are
for canonical base `0x100000000`. After attach:

```
image list -o aned
```

Take the reported load address `L`; runtime address = `L + (addr - 0x100000000)`,
e.g. handoff call site 0x10001f290 -> `L + 0x1f290`. Key offsets:

| purpose | canonical addr | module offset |
|---|---|---|
| `unsignedIntValue` (mask becomes raw uint) | 0x10001cecc | 0x1cecc |
| `+[ANEPerformanceStats driverMaskForANEFMask:]` call | 0x10001ced8 | 0x1ced8 |
| `setPerfStatsMask:` | 0x10001cee4 | 0x1cee4 |
| `[self perfStatsMask]` fetch (pre-handoff) | 0x10001f1ac | 0x1f1ac |
| `createProgramInstanceForModel:...` call (kernel handoff) | 0x10001f290 | 0x1f290 |

Argument-passing facts from the disassembly (do not re-derive): at the
`driverMaskForANEFMask:` CALL SITE the mask is in **x2**; at the handoff call
the mask is **stack-passed** (`str w26, [sp, #0x4]` immediately before the
bl) — read **x26** and the stack slot, not x0/x1.

## Act 2 — poison-first client run

The ncm-run harness now takes the attach mask from env (added 2026-10-23):

```
NCM_ANE_KANE=1 NCM_ANE_KANE_MASK=FACE \
  ncm-run/bare/.build/release/ncm0 anectx --field
```

`0xFACE` replaces the normal `0xF`. Cache budget: a non-default mask changes
the program cache key (doc 12 §Q3) — first run recompiles; use the repo
canonical dump (default) or a scratch model path.

## Act 3 — breakpoints (lldb command file: `aned_breakpoints.lldb`)

Load with `command source aned_breakpoints.lldb` after attach, or
`sudo lldb -p $(pgrep -x aned) -s aned_breakpoints.lldb`. Symbolic form
first; if the class method is not resolvable, use the address form with
`L` substituted (see file header).

Decision table:

| observation at fetch @0x10001f1ac / handoff | zero happened in |
|---|---|
| x26 = 0xface at handoff; stack slot [sp,#0x4] = 0xface | **kernel** (`initStatsBufferSection`) — framework innocent; request reaches the IOKit boundary intact |
| x26 = 0 at fetch, x2 = 0xface at driverMask call | **framework translation table** `driverMaskForANEFMask:` — dump its returned mapping for third-party class |
| client never hits driverMask call | options payload never carried the mask — client-side bug, check `_ANEInMemory` option dict assembly |

Only after 0xface is located (or proven absent) at those points should any
third-party struct-layout claim be trusted — including Bryngelson arXiv
2606.22283 §33.1's `+0x6c` stats-offset claim: scan for the little-endian
poison bytes `ce fa 00 00` in the args blob/stack near the handoff
(`x/256xw $sp`, look for a `0x0000face` slot) before
dereferencing any fixed offset. Written-zero vs never-written discipline
applies: a zero found at `+0x6c` means nothing until the poison proves the
slot is on the write path.

## Act 4 — record

Transcript to this directory (`raw/sip-prep/session-<date>.log`), then update
doc 12 §Q3 [U] with the ruling (and, if the table is the culprit, dump its
third-party mapping). Per prior-art status: whole-engine unentitled surface is
already ours via enginemon PMP0 (EXP-022/EXP-024); tmc/aneperf (verified
2026-10-23, `ncm-run/docs/prior_art.md` §2) ships the same PMP channel family
in Go — no new capability expected from IOReport re-naming, only confirmation.
