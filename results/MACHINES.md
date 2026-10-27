# MACHINES — every machine this corpus has measured, and where its numbers live

Added 2026-10-11. Purpose: the fair-look table. A reader outside this project should be able to
take any number in the corpus, find which machine produced it, what that machine *is* under Apple
platform naming, and which comparability rules apply — without asking us. Naming rules and their
verification: `knowledge/ane/11-platform-naming.md` (NAME-001). Machine comparability protocol:
EXP-005 two-throughput-states, per machine — never one cross-machine table row.

## Tested (measurements in this corpus)

| platform | chip | codename / SoC ID | machine | board | CPU / GPU / ANE | OS | arch strings (runtime / compiler) | measurements live here |
|---|---|---|---|---|---|---|---|---|
| **H16G** | M4 base | Donan / T8132 | Mac mini, 16 GB, 10GbE | `Mac16,10` (anectype board 256) | 10 (4P+6E) / 10 (re-probe outstanding) / 16 | macOS 27.0.1 (26A434) | `h16g` / `h16g` | historical corpus: EXP-001…021 (~716 `M4` rows in `measurements.json`), `EXP-020` DMA notch, `EXP-028` e6 B-surface + `raw/p28_e1_anec/`, power rows 75 vs 4124 mW (powermetrics sudo), `EXP-013` gate, `EXP-018` 230/231; grounding `cache/` lives on this machine (FLEET GAP-3) || **H17C** | M5 Max (40-core bin) | Sotra_C / T6050 (`AppleT6050PMGR`) | Mac Studio, 128 GB | `Mac17,14` (board 544) | 18 (6S+12P) / **40** (probe.txt) / 16 | macOS 27.0.1 (26A434) | `h17g` / `h17c` | baseline fingerprint `bda452aabd60bf26` (`EXP-022`, `examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json`), energy close `raw/energy-close-2026-10-06/`, `EXP-024/025/026/027/028` (+`EXP-029` scaffold), `results/LADDER.md` C8, `measurements.json` `m5max-*`/`xval-*` rows |
| **H16G** | M4 base | Donan / T8132 | MacBook Air 15", 16 GB | `Mac16,13` | 10 (4P+6E) / 10 (on-machine verified 2026-10-27) / 16 | macOS **26.6.2** (25G83) | `h16g` / `h16g` | added 2026-10-27 (`EXP-044`): first pre-27 bench box — C2a/C2b load-gate matrix (`raw/gate-26.6.2-*.log`, `raw/c2b-air-local-compile-*.log`, GOTCHAS-093), C4 f16 bursts (`raw/air-f16-bursts2-*.log`), C5 wall counter-case ≥13.18 GiB (`raw/air-wall-26.6.2-*.log`, API-174); fleet-join receipt: `raw/air-identity-20261027T120913Z.txt` (`identity.py` JSON + `ane-probe` h16g/h16 + GPU 10-core, board 256) |

Runtime/compiler divergence on H17C (runtime reports the **base-tier** string of the right
generation, compiler reports the exact tier) is documented in `EXP-028` e6 and is expected behavior
under platform naming (NAME-001/002) — it is not a defect in either box.

## Known, untested (platform facts without measurements)

| platform | chip | codename / SoC ID | ships in | status for this corpus |
|---|---|---|---|---|
| H17S | M5 Pro | Sotra_S / T6050 (user-tagged; equals the Max id — flagged in NAME-001 caveats) | MacBook Pro 2026, Mac mini 2026 | not on fleet; `h17s` fed but not accepted on our boxes (NAME-005) |
| H17D | M5 Ultra | Sotra / T6052 (user-tagged) | Mac Studio 2026-08 | not on fleet; its ANE=32 is the H17 tier fact behind CORE-003 |
| H18G | M6 | Komodo / T8152 (user-tagged; chip itself web-confirmed) | Mac mini 2026 (`Mac18,5`, A3534, board J873gAP) | candidate fleet addition; its **dual 16-core ANE** is the first two-ANE-count marketing part — highest-value probe target for the num_nes question (NAME-003/004) |
| — | iPad Air M2 | — | — | planned; zero probes (FLEET) |
| — | Lenovo P11 Pro | Android/ARM | — | future contrast column; non-Apple |

## Fairness rules (binding for anyone reading or publishing our numbers)

1. **Never rank across generations.** M4 and M5 rows are separate comparability universes
   (`env.md`); ANE throughput differs by *memory regime*, not just cores: M5 Pro/Max got a
   higher-bandwidth ANE connection and the base pool moved 120 → 153.6 GB/s (NAME-006). "ANE
   bandwidth" numbers carry the machine, always.
2. **Never divide by a bare core count.** "16" means marketing ANE cores (both tested boxes), and
   it is *not* the same quantity as HAL `num_nes` (4 vs 16 vs 32 depending on target), GPU cores,
   or NA lanes (NAME-004, `EXP-027` xval CORRECTION 2026-10-10, GOTCHAS-087).
3. **Two throughput states per machine** (EXP-005): quiet-window vs loaded rows are different
   physics; the Studio's load source is local agents (env.md structural rule).
4. **Compile-surface claims quote menus, not counts** (NAME-005): "5 targets on the mini" was our
   input menu, not the machine's acceptance limit.
5. Every row above points at an EXP directory or `measurements.json` id prefix; a claim that
   cannot point there is not machine-attributed and should not be cited.

Machines join this table by running `python3 bench/identity.py` + `bench/ane-probe.m` and appending
a dated row with the outputs pinned under `results/EXP-*/raw/`. Never edit history here.
