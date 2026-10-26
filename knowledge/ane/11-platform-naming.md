# 11 — Platform naming: Apple's H-number scheme, our fleet, and who maps it wrong

Added 2026-10-11 (user-provided Apple Wiki + Asahi Linux cross-reference, verified where we can).
This file is the naming authority for the corpus: every `h1Ng`-style string we emit now carries its
meaning — **generation + tier**, never a core count. Fair-look rule for outside readers: if a number
in this corpus sits next to a platform name, this file says which quantity it is allowed to be.

## The rules (user table: The Apple Wiki + Asahi Linux docs, 2026-10-11)

| Element | Meaning | Verification |
|---|---|---|
| `H` prefix | main SoC (A-series + M-series) | ours: every arch string we resolve is `h1N[suffix]` (API-138) |
| number 4–19 | generation, **shared between A and M chips of the same year** | ours: paper glossary — "T8142 for the M5 base… maps to an ANE H-generation through the board-type sequence" + our M4 base = T8132 → gen 16 (FORMAT-062); M5 Max IORegistry `AppleT6050PMGR` → gen 17 |
| letter suffix | tier (below) | ours: both fleet parts resolve to the **G** letter = base tier per the table (mini is base M4; the **compiler** on the Max resolves `c` = Max) |
| `M` prefix (M7–M11) | co-processor (S/T-series) | unverified(user) — no fleet evidence |

**Tier letters — M-series:** `G` = base Mac · `S` = Pro · `C` = Max · `D` = Ultra · `M` = reduced-core
Max variant (M3 Max 14-core, H15M). **A-series:** `P` = standard, `A` = base non-Pro (since A18),
`G` = X-series (legacy), `I` = single-core, `T` = T-series coproc.
Codenames are island/geographic names; Pro/Max/Ultra share the root with a numeric modifier
(*Jade* Chop / *Jade* 1C / *Jade* 2C; *Sotra* / Sotra_S / Sotra_C).
SoC IDs: `T8xxx` phone/tablet-class, `T6xxx` desktop-class.

## M-series platform table (user rows; each tagged by how we verified it)

Tags: **ours** = confirmed by our own measurement on a fleet machine · **web** = confirmed by
Apple/Wikipedia during this round · **user** = supplied by the repo owner (Apple Wiki/Asahi table), not
independently re-verified here (theapplewiki.com 403s from this network).

| platform | chip | codename | SoC ID | tag |
|---|---|---|---|---|
| H13G / H13S / H13C / H13D | M1 family | Tonga / Jade Chop / Jade 1C / Jade 2C | T8103 / T6000 / T6001 / T6002 | user |
| H14G / H14S / H14C / H14D | M2 family | Staten / Rhodes Chop / Rhodes 1C / Rhodes 2C | T8112 / T602x | user |
| H15G / H15S / H15C / H15M / H15D | M3 family (+ 14-core Max) | Ibiza / Lobos / Palma | T8122 / T603x | user (`h15m` in our compiler target list is consistent) |
| **H16G** | **M4 base** | **Donan** | **T8132** | **ours+web** — our mini: T8132 and `h16g` on all four surfaces (API-138/FORMAT-062); Wikipedia Apple_M4 |
| H16S / H16C | M4 Pro / Max | Brava Chop / Brava | T6040 / T6041 | user (`h16c`, `h16s` names exist in our compiler surface) |
| H17G | M5 base | Hidra | T8142 | web — paper glossary names T8142 = M5 base |
| H17S | M5 Pro | Sotra_S | T6050 | user — **conflict flagged**: T6050 equals the Max below; Apple Wiki lists it for both, Apple's M1 generation used distinct T6000/T6001 |
| **H17C** | **M5 Max** | **Sotra_C** | **T6050** | **ours+web** — our Studio: `AppleT6050PMGR` IORegistry node, compiler target `h17c`; tier letter `c` = Max per rule |
| H17D | M5 Ultra | Sotra | T6052 | user (ship date web: Apple newsroom 2026/08 "M6 and M5 Ultra") |
| h17p (in compiler surface) | A18 Pro platform | Tahiti | T8140 | user — its presence in a Mac target list confirms targets span A+M of a generation |
| **H18G** | **M6** | Komodo | T8152 | web for the chip + our surface for the name; **user-only for H18G/T8152/codename** (Bloomberg leak lineage; theapplewiki 403 here) |
| H18A / H18P | A19 / A19 Pro | Tilos / Thera | T8150 | user |
| H19P | A20-class | Borneo | T8160 | user |

**M6 facts (web, Apple newsroom 2026/08 + Wikipedia Apple_M6):** announced 2026-08-25, released
2026-09-22 in the Mac mini (first base-only generation — Bloomberg 2026-06-25: M6 Pro/Max skipped,
high end continues at M7). 12-core CPU (2S+4P+6E), 12-core GPU with per-core Neural Accelerators,
**dual 16-core Neural Engine**, 16/24/32 GB at 153.6/170 GB/s, TSMC 2 nm, ~46 B transistors.
Mac mini board `J873gAP`, model A3534, `Mac18,5` — user-supplied, tag **user**.

## The tier-letter inversion — why the guide/paper rows keep disagreeing with our boxes

Paper 2606.22283's own silicon→target map (extract `ane_paper_sec20_sec33_extracts.md`, lines
~4225-4250) says: M3 Pro/Max → `h15g`, M4 base → `h16` (bare), M4 Pro/Max → `h16g`,
M5 Pro/Max → `h17s`. Under Apple's naming rules those Pro/Max rows land on the **base-tier letter G**,
and bare `H16` is not a platform name at all. Our measurements decide for Apple:

- M4 **base** (T8132) resolves `h16g` on all four surfaces — exactly the rule's G = base.
- M5 **Max** compiler resolves `h17c` — exactly the rule's C = Max.
- `coreai-build` rejects bare `h16` as `Unknown architecture` — the accepted names are platform
  names with tier letters, not base+generation alone.

Consequences recorded once here, pointed to everywhere else:
- **ane-guide issue #1** (`contrib/ane-guide-arch-table-correction.md`, follow-up draft in
  `contrib/ane-guide-issue1-followup.md`): both the 34.1 label "H17g = M5 Pro, Max" and the 34.3
  mapping "M5 Pro/Max → h17s" conflict with platform naming; 34.3 is half-right (S = Pro) and wrong
  for the Max (C). Our runtime `h17g` on the Max is the base-tier string for the right generation —
  a resolver behavior, not a table error on our side.
- **`num_nes` ladder** (`knowledge/ane/10` amendment #3): `base=4 g=8 s=16 c=32 d=64` reads NE
  counts off **tier letters**. Under platform naming the letters designate products, so the ladder is
  the guide/paper's per-tier estimate — and the paper itself states marketing core count ≠ physical
  compute sets (M1: marketing 16, measured 4 compute sets). Open question stays open;
  the probe got sharper, not smaller.
- M6 "dual 16-core Neural Engine" (Apple, web) shows the marketing count itself now goes dual-die:
  32 NE cores on one H18-class part. Any future `num_nes` reading must say which of
  {marketing cores, compute sets, NA lanes, per-package total} it is before any division.

## The 5-vs-21 compile-surface question — a menu artifact, not a machine difference (2026-10-11)

EXP-028 E6 (`results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt`) fed the AOT gate
**different menus per box**: mini got 5 names (`h15g h16c h16s h17c` + accepted `h16g`); the Max got
22 (21 named rejections + accepted `h17c`). Both boxes accepted **exactly one** target — their own
platform name. Nothing in the evidence says the acceptance *sets* differ beyond the menu difference.
Enumeration honesty: the paper claims a 28-target table; our 22-name menu was typed by hand from
known platform names, so the remaining ~6 (e.g. `h13p h14p h15p h16p h17a h18a h18p` under the rules)
were never fed anywhere. Equal-menu rerun on both machines is registered in
`results/EXP-028-apple-tracer/README.md` "Next"; do not cite "5 vs 21" as a machine property.

## ANE memory across M4 → M5 — what "bigger dedicated RAM" can and cannot mean (2026-10-11)

- **No dedicated ANE RAM chip exists on M-series** (Apple architecture, web-confirmed): CPU/GPU/ANE
  share the unified LPDDR5X pool ("All M5 chips use a unified memory architecture … the Neural
  Engine share the same single pool" — Wikipedia Apple_M5 §Memory).
- What Apple does state per generation (web): M5 **Pro/Max ANE has a higher-bandwidth connection to
  memory** (newsroom 2026/03); base M5 raises the pool to 153.6 GB/s vs M4's 120. This is the real
  "bigger pipe" behind user reports of more ANE memory bandwidth on M5 — a connection, not a chip.
- Paper measurements (pin `ane_paper_sec20_sec33_extracts.md`): ANE on-chip SRAM working set
  `max_operand_bytes @0x1b8` (compiler name **MemCacheSize** / L2Size) = **2 MB, constant across the
  H13→H17 line** (1 MB on M9); ANE DRAM share ~85–90 GB/s measured on M1-class; M5/H17s weight-stream
  ~145 GB/s over two DRAM read channels; M5 matmul peak ~9.5 fp16 TFLOP/s.
- Consequence for our ledger: mini(M4) vs Studio(M5) ANE rows are **not** comparable by core count
  alone (bandwidth regime differs); `results/MACHINES.md` fairness rules carry the rule.
- **GAP (declared):** per-machine ANE-reserve/SRAM values on our two fleet boxes are unread
  unprivileged; `max_operand_bytes` per-target read is folded into the EXP-028 probe registered
  in `results/EXP-028-apple-tracer/README.md`.

## Records

```jsonl
{"id":"NAME-001","claim":"Apple platform identifiers are H+generation+tier-letter (H16G = M4 base, H17C = M5 Max); the generation number is shared between A and M chips of the same year and tier letters for M-series are G=base, S=Pro, C=Max, D=Ultra, M=reduced-core Max, so no component of an h1N-style arch string encodes a core count.","kind":"fact","confidence":"documented","source":"user-provided Apple Wiki + Asahi Linux cross-reference 2026-10-11; ours: T8132+h16g mini (API-138), AppleT6050PMGR on Mac17,14, h17c compiler target; paper glossary T8142->H-generation (results/EXP-024-engine-attribution/raw/research-2026-10-06/ane_paper_sec20_sec33_extracts.md ~L20571)","source_type":"secondary","retrieved":"2026-10-11","topic":["naming","platform","tier","generation"],"entities":["H16G","H17C","H17S","H17D","H15M","tier letter","generation"],"caveat":"applewiki.com 403s from this network so the user table is verified by corroboration (our measurements + paper + Wikipedia), not by direct re-fetch; A-series rows and co-processor rows stay user-tagged","contested":false}
{"id":"NAME-002","claim":"Paper 2606.22283 and ane-guide map Pro/Max parts to the G tier letter (M3 Pro/Max->h15g, M4 Pro/Max->h16g, M5 Pro/Max->h17s) and use a bare 'h16' for M4 base; under Apple platform naming G is the base tier and bare H16 is not a platform name — our four-surface measurements (M4 base resolves h16g; coreai-build rejects bare h16 as Unknown architecture) side with Apple's naming, making the paper/guide map a tier-letter inversion, not our measurement error.","kind":"analysis","confidence":"inferred","source":"results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt + results/EXP-024-engine-attribution/raw/research-2026-10-06/ane_paper_sec20_sec33_extracts.md ~L4225-4250 + NAME-001","source_type":"our-own","retrieved":"2026-10-11","topic":["naming","coreai","compiler-target","ane-guide","paper-critique"],"entities":["h16g","h17c","h17s","h15g","coreai-build","tbl:c34-silicon"],"caveat":"we measured two parts (M4 base, M5 Max) on 26A434; the paper may apply 'h1Ng' as its own runtime-identifier convention consistently — the dispute is specifically about mapping product rows to tier letters","contested":false}
{"id":"NAME-003","claim":"Apple M6 (announced 2026-08-25, released 2026-09-22, Mac mini only; 12-core CPU 2S+4P+6E, 12-core GPU with per-core Neural Accelerators, dual 16-core Neural Engine, 153.6/170 GB/s, TSMC 2nm) is the first base-only M generation - M6 Pro/Max are skipped with the high end continuing at M7 - and the h18g name was already accepted in the 26A434 AOT compile-surface we tested before the chip shipped.","kind":"fact","confidence":"documented","source":"https://www.apple.com/newsroom/2026/08/apple-introduces-m6-and-m5-ultra-for-a-big-leap-in-performance-and-ai-compute/ ; https://en.wikipedia.org/wiki/Apple_M6 (fetched 2026-10-11); ours: h18g in e6 R4 menu (results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt)","source_type":"primary","retrieved":"2026-10-11","topic":["m6","generation","ane","naming","fleet"],"entities":["M6","H18G","Komodo","T8152","Mac18,5","A3534","J873gAP","dual 16-core Neural Engine"],"caveat":"platform name H18G, SoC ID T8152, codename Komodo and board ids are user-tagged (Apple Wiki / Bloomberg leak lineage) - the web-confirmed facts are the chip, date, product, and dual-16 ANE; h18g acceptance was in our menu, not a load test on H18 silicon","contested":false}
{"id":"NAME-004","claim":"The per-tier core ladder base=4 g=8 s=16 c=32 d=64 assigns NE counts to tier LETTERS, which under platform naming identify products not core counts; the paper itself separates marketing cores from physical compute sets (M1: marketing 16 vs 4 measured compute sets) and Apple now sells a dual-16-core ANE (M6), so num_nes and marketing counts measure different quantities and no division of one by the other is valid without first naming the quantity.","kind":"analysis","confidence":"inferred","source":"results/EXP-024-engine-attribution/raw/research-2026-10-06/ane_paper_sec20_sec33_extracts.md (28-target HAL table by byte offset; ~L21215 marketing-vs-compute-sets) + NAME-001/003 + CORE-003","source_type":"our-own","retrieved":"2026-10-11","topic":["num_nes","hal","core-count","open-question"],"entities":["num_nes","0x238","ladder","compute sets","M6"],"caveat":"this sharpens CORE-003, it does not close it: the exact quantity HAL counts remains open until the on-die probe runs","contested":false}
{"id":"NAME-005","claim":"The 5-target acceptance reported for the M4 mini versus 22 targets fed on the M5 Max is an artifact of the menus we chose to feed (mini: h15g/h16c/h16s/h17c + accepted h16g; Max: 22 named), not a machine-side difference: both boxes accepted exactly their own platform name and rejected everything else; ~6 further target names from the paper's 28-target table were never fed on either box.","kind":"measurement","confidence":"measured","source":"results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt (R4 blocks A and B)","source_type":"our-own","retrieved":"2026-10-11","topic":["aot-gate","compile-surface","compiler-target","test-design"],"entities":["h16g","h17c","coreai-build","28 targets"],"caveat":"equal-menu rerun on both boxes is registered (EXP-028 Next); until it runs, cite the e6 menus, not a 5-vs-21 machine contrast","contested":false}
{"id":"NAME-006","claim":"M-series has no dedicated ANE RAM chip - the Neural Engine shares the unified LPDDR pool; the real per-generation changes are (a) a higher-bandwidth ANE memory connection on M5 Pro/Max and (b) base-M5 pool bandwidth 153.6 GB/s versus M4's 120, while the ANE on-chip working set max_operand_bytes @0x1b8 (compiler name MemCacheSize) is 2 MB constant across the H13-H17 line; measured ANE-side DRAM throughput runs ~85-90 GB/s on M1-class versus ~145 GB/s weight-stream on M5/H17s.","kind":"fact","confidence":"documented","source":"https://en.wikipedia.org/wiki/Apple_M5 (fetched 2026-10-11, Memory + Neural Engine sections) + results/EXP-024-engine-attribution/raw/research-2026-10-06/ane_paper_sec20_sec33_extracts.md (~L1846, ~L21215, ~L21368)","source_type":"primary","retrieved":"2026-10-11","topic":["ane","memory","bandwidth","m4","m5","comparability"],"entities":["MemCacheSize","max_operand_bytes","0x1b8","unified memory","153.6 GB/s","145 GB/s"],"caveat":"user's 'dedicated RAM chip is bigger on M5' matches the connection-bandwidth change, not a discrete chip; per-machine ANE-reserve values on our two boxes are unread unprivileged (GAP, folded into the EXP-028 probe)","contested":false}
```
