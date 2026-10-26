# EXP-034 — Full Access: DeviceProperties decode, field-key map, chaining spike (M5 Max + M4 mini)

Campaign: **EXP-034 full-access** (2026-10-23, studio M5 Max Mac17,14 + mini M4 Mac16,10,
macOS 27.0.1/26A434 both). Follow-on to EXP-033 door-map: decode what the door actually
returns, and test the hot-submit (chaining) path end-to-end. Lanes: home-base RE here;
ncm-run consumes handoff artifacts only (dual-path A/B — NOT-TRIGGERED this round, see
`c80_chaining_parked.json` + ncm-run backlog §T4).
Prior art credited: mdaiter/ane (pushed 2026-02-01 — knocked the same door earlier,
H11-era), BlackStorm ER-10, Phrack #72 (methodology).

## Headline verdicts

| Item | Verdict |
| --- | --- |
| C-79 door decode | **size(-era), not entitlement** — `DeviceProperties` readable unprivileged on both boxes (exactly one key: `ANEDevicePropertyNumANEs=1`, matching u32@0x54=1 in the sel-0 response — the only exact key-value match); u64@0x50=4 GiB identical both boxes; u64@0x60 = **16 GiB studio / 10 GiB mini** (machine-dependent; Metal recommendedMaxWorkingSetSize 107.52/11.84 GiB REFUTED as source — apertures/generation-constant hypotheses open, no more precise source measured). mdaiter arm: their exact **104 B (0x68)** struct send → **kr=0xe00002c2 (BadArgument) both boxes**, not their NotFound (H11-era — the H11ANE instance is all-70-Unsupported here, EXP-033 sweep line 72); our **136 B (0x88)** contract send → **kr=0x0** same session. |
| C-79 corrections | sel-6 live code is **kIOReturnNotFound (0xe00002f0)**, not "NotReady" (0xe00002d8) as EXP-033 prose said; probe4's "u64@88=1 / u64@112=4" were mislabeled — true words u32@0x54=1 / u32@0x64=4. Both corrected in doc 14 dated addendum. |
| C-80 chaining spike | **PARKED-WITH-NAMED-GAP** — sel-2 3152B payload: uniform BadArgument across 12 word[0] handle candidates; successful sel-1 pre-arm does NOT change the verdict → first gate is upstream of handle/chaining state: the `ANEProgramChainingPrepareArgs` blob grammar (callee deserializer embeds `OSValueObject<ANEClientDevice*>` + device-type switch; no scalar compare in the dump window). Named gap + next step in `c80_chaining_parked.json`. |
| C-81 consumer lane | **NOT-TRIGGERED** (gate allows parked outcome) — dual-path door-vs-aned A/B awaits a chaining-proven handoff or the EXP-025 shared-events mailbox route. |
| Zero residue | All probe runs, both boxes: `raw/ioreg_zero_residue_witness.txt` (studio 707/707 md5-stable, mini 448/448 md5-stable). |

## Repro

```sh
cd tools/ane_door_probe
clang -O2 -o probe5_devprops probe5_devprops.c -framework IOKit -framework CoreFoundation \
  && codesign -s - -f ./probe5_devprops && ./probe5_devprops | tee raw/p5_studio_ANEDriver.txt
# mini: same source on ~/night/exp034 (ssh, tar-pipe transfer per FLEET protocol)
clang -O2 -o probe6_chain probe6_chain.c -framework IOKit -framework CoreFoundation \
  && codesign -s - -f ./probe6_chain && ./probe6_chain        # sel-2 handle ladder
clang -O2 -o probe6b_chain probe6b_chain.c -framework IOKit -framework CoreFoundation \
  && codesign -s - -f ./probe6b_chain && ./probe6b_chain       # ladder + sel-1 pre-arm
# zero-residue: count + sorted-set md5 of IOUserClientCreator strings pre/post
ioreg -l -w 0 | grep -c IOUserClientCreator
```

## Caveats (honest list)

- Field-key map is **partial**: one exact match (NumANEs). The 4 GiB / 16 GiB / 10 GiB
  trio is named by numeric pattern only; no published or measured source pins them yet.
- The 0x68 (104 B) arm tests struct size + the two documented mdaiter variants on the
  current door only; their H11ANEIn selector-0 (Phrack-documented 96 B contract; their own
  struct is 104 B) was not reproduced from user space.
- C-80 ladder probes word[0] of the blob; other words were zeroed — a valid blob could
  fail on any of the remaining 3145 bytes, which is exactly why the verdict names the
  serializer grammar, not a field.
- One OS build (26A434). Mini chaining not attempted (studio-only spike per budget).
- "M1-era comparison" (H11ANEIn selector archaeology, mdaiter's home stack) **parked by
  owner decision 2026-10-23**: does not serve the newer-stack door program; re-open only
  if a fleet M1 machine joins.

## Publish triage (PUBLISH-POLICY)

Publishable (distill): unprivileged DeviceProperties readability + single-key content,
machine-dependent u64@0x60 aperture observation, sandbox-independence already public via
EXP-033 row. Private: chaining blob-grammar internals (named gap), our probe inventory.
Credit mdaiter/ane (door opened unprivileged before us, Feb 2026; era-scoped misattribution
of the failure named politely) and ER-10/Phrack #72 (method).

## Contents

- `c79_devprops.json` — decode + field-key map + mdaiter ruling (stamped)
- `c80_chaining_parked.json` — chained-submit spike verdict (stamped)
- `raw/p5_studio_ANEDriver.txt`, `raw/p5_mini_ANEDriver.txt` — DeviceProperties + sel-0 hexdump + 0x68 arms (the two files differ ONLY in the u64@0x60 line)
- `raw/p6_chain_studio.txt`, `raw/p6b_prearm_studio.txt` — sel-2 handle ladder, unarmed + sel-1 pre-armed
- `raw/ioreg_zero_residue_witness.txt` — per-run witnesses, both boxes
- Claims: MEASURE-162/163 (doc 14 Claims block → appended via `knowledge/ane/tools/openclaims_append.py`; records in `knowledge/ane/records/14-door-map.jsonl`)
