# C-71 — compiled-program blob capture (2026-10-23)

Method: `/usr/bin/log stream --predicate 'process == "aned"' --info` (full path —
zsh builtin shadow) for a 25 s window while running three battery compacts
(`ref`, `s_16`, `gelu_tanh`).

## Naming + readability verdict (measured, better than the NOT-REACHABLE floor)

- `/Library/Caches/com.apple.aned` — `ls: Operation not permitted` (mode-blocked,
  as predicted); no sudo attempted.
- aned's own log lines reference URLs but every path field is `<private>`-redacted
  (`modelURL=<private>`, `outputURL=<private>`; unmask needs the SIP/log-config
  session held for EXP-031 C64) — no cache paths leak through the log at --info.
- **The readable artifact is ours:** the `_ANEInMemory` path (ANEBridge) stages
  `$TMPDIR/<hex>_<hex>_<hex>/` per compile and, because the battery process exits
  via `_exit`, they survive. Naming cracked:
  - component 1 = **SHA256(model.mil bytes), uppercase** — this is what the
    framework calls `hexStringIdentifier` (verified 3/3 cases byte-exact);
  - component 3 = SHA256(empty string), uppercase (`E3B0C4…`);
  - component 2 = constant across programs sharing identical weight bytes but
    NOT sha256 of `weights/weight.bin` itself (`469FB3EF…` vs file `8787B624…`)
    — tracks the weight payload's descriptor/serialization, formula unresolved
    (honest open end).
- Contents per dir, all world-readable (owner rw): `model.mil` (echo of the input
  MIL), `net.plist` (byte-identical copy of the MIL — the "net" slot for
  pre-compiled consumers), `weights/weight.bin` (our blob), and **`data` — the
  compiled program blob** (17,408 B for the ref geometry).

## Format walk vs RUNTIME-013 family

`data` opens with the SAME 64-byte file header as our weight blobs
(`u32[0]=chunkCount=6, u32[1]=2`) — then six chunks, each a 64-byte record
starting `DEADBEEF` (LE `efbeadde`) + size/u64 fields, walk closes exactly at
EOF (0x4400). Chunk payload sizes 8192/64/128/8192/64/128 **mirror our int8
weight regions W1/zp/scale × 2 layers** — the compiled program reuses the
RUNTIME-013 container grammar and carries per-chunk `type` (4 = int8-weight
class, 1 = scale/metadata class on this sample) and a rising `d3` field that
reads as intra-file offset bookkeeping. `wiredMemory=98304` (anectx big program)
matches `modelSize` lines in the same capture.

## Ancillary (EXP-031 corroboration, free from the same stream)

`coreAnalyticsClientType=ThirdPartyAppUsingANE StatsMask=0` on our own battery
client — the aned gate line witnessed live for a raw bridge client (unsigned
tool), matching the EXP-031 entitlement-gate verdict.
