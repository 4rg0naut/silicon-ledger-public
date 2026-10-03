# FLEET — cross-M-chip instrument matrix

The project is cross-M-chip low-level RE and tool development. This file is
the standing answer to: *does the instrument run, on which machine, with what
evidence?* Every cell is `run (ref)`, `build-only`, `planned`, `blocked (why)`,
or `—` (never attempted / unknown). Numbers cited here trace to
`results/measurements.json` row ids or EXP records; this document adds no
measurements.

Machines of record (comparability protocol: never a single table row across
machines — EXP-005 two-throughput-states applies per machine):

| machine | identity | ANE | role |
|---|---|---|---|
| Mac Studio M5 Max | `Mac17,14`, 18C, 128 GB, macOS 27.0.1 (26A434) | h17g | calibration bench (`bda452aabd60bf26`, EXP-022) |
| Mac mini M4 | `Mac16,10`, base M4 + 10GbE, 16 GB | h16g | historical corpus (EXP-001..021, 716 `M4` rows) |
| iPad Air M2 | — (not powered for RE yet) | — | planned; constrained target |
| Lenovo P11 Pro | Android/ARM (non-Apple) | n/a | future contrast column |

## Unified identity schema (2026-10-03)

Every instrument emits the same keys — `chip, hw_model, cores, arch, os,
os_build` — so outputs are machine-attributable without human memory:

- `bench/identity.py` — shared Python helper (CLI + import). Emits the dict.
- `bench/ane-probe.m` — `identity:` header line via `sysctlbyname`.
- `bench/ane-dma-test.m` — `hw_model`/`os_build` added to both machine records.
- `tools/enginemon/enginemon.c` — `identity` line at startup.
- `bench/syswide_ane.py`, `bench/power_ab.py`, `bench/power_coreai.py`,
  `bench/power_phase_probe.py` — print `identity: {...}` at start.

Live capture on the Studio (re-run costs seconds, `python3 bench/identity.py`):
`chip=Apple M5 Max hw_model=Mac17,14 cores=18 arch=arm64 os=27.0.1 os_build=26A434`
(ane-probe and enginemon emit the identical line; verified 2026-10-03).
Note: build is `kern.osversion`; `kern.osbuildversion` does not exist as an OID.

## Readiness inventory (machine-specific assumptions, 2026-10-03 pass)

Fixed in this pass:
- Hardcoded `/Volumes/data/local_ai_stack` paths removed from code:
  `bench/power_ab.py`, `bench/power_coreai.py`, `bench/power_phase_probe.py`
  (usage lines now `cd "$(git rev-parse --show-toplevel)"`),
  `knowledge/ane/tools/kb_ground.py` (dead `LOCAL_ROOT` removed; repo root
  added as local-path candidate), `knowledge/ane/tools/wice_to_openclaims.py`
  (`WICE_SRC` env override + missing-input guard). `to_openclaims.py` was
  fixed earlier (T1). Historical strings in `results/EXP-*/README.md` are
  records, not code — untouched.
- `ane-probe` build line: `-framework ObjectiveC` fails to link on the current
  SDK (framework is implicit); header updated to plain `-framework Foundation`.

Standing requirements per instrument (declare, do not paper over):
- `sudo` + `powermetrics`: `power_ab.py`, `power_coreai.py`,
  `power_phase_probe.py` — macOS with root only; no iPad equivalent exposed.
- Xcode (not CLT) via `DEVELOPER_DIR`: `xctrace` in `syswide_ane.py`,
  `coreai-build` AOT flows.
- `libIOReport.dylib` private: `enginemon` — macOS only (verified euid-501
  read works on macOS 27.0.1, no sudo needed for these channels on the Studio).
- AppleNeuralEngine private framework via `dlopen`: `ane-probe`,
  `ane-dma-test`, direct-path harnesses — macOS only from CLI; on iPadOS the
  same framework exists but only reachable inside a signed app.
- Conversion venvs (`.venv-conv`: coreai-torch; `.venv`: openclaims SDK from
  `git+https://github.com/openclaims-ai/openclaims.git#subdirectory=python`,
  not on PyPI) — Mac hosts only.

## Matrix

| instrument | M5 Max (Mac17,14) | M4 mini (Mac16,10) | iPad Air M2 | P11 Pro |
|---|---|---|---|---|
| `silicon-ledger-bench` (Swift S0–S5) | run `bda452aabd60bf26` (EXP-022; 19 rows T5-merged) | — not yet run through this instrument | blocked: needs macOS host for xcodebuild | — |
| `ane-probe.m` | run 2026-10-03, exit 0 (identity verified) | run (M4/macOS_27 scan, first upstream CSV row — README open thread) | planned: app wrapper, no CLI | — |
| `ane-dma-test.m` | build OK 2026-10-03 (full run is long; EXP-022 used enginemon instead) | run (EXP-020 DMA notch) | blocked: IOSurface app-host | — |
| `enginemon` | run 2026-10-03 (euid 501, IOReport channels read) | run (per-row protocol + Laya, CONSISTENCY-PLAN C) | blocked: IOReport macOS | — |
| `syswide_ane.py` | ready: identity wired, compiles 2026-10-03; xctrace arms not re-run this session | run historically (EXP-004 lesson: xctrace blind to Core AI) | blocked | — |
| power probes (×3) | build-only here — no sudo in this session | run (sudo powermetrics; energy rows 75 vs 4124 mW, 2.06 vs 11.45 mJ) | blocked: no powermetrics | — |
| `identity.py` | run 2026-10-03 | run — same schema, keys exist on any macOS | partial: needs app-side emit | — (non-Apple sysctl) |
| `to_openclaims.py --check` | run 2026-10-03: 679/679 valid | — (SDK venv not set up there) | — | — |

Asymmetry to close (known GAPs, em-dash policy):
- M5 energy: no rows — powermetrics never run on the Studio (sudo pending);
  M4 has 3 `energy_mw` records of record (plus mJ/mW metric rows). Closing
  this is `power_ab.py` + sudo here.
- M4 through the Swift bench: never run; its 716 rows come from the Python/
  harness lineage, a different instrument — do not compare bands across them.
- iPad Air M2: zero probes. First useful artifact is an app-hosted `ane-probe`
  (class enumeration only); energy and IOReport arms stay Mac-only.

Regenerate matrix rows by running the cited commands on the cited machine and
appending dated lines here; never overwrite history.

---

## Appendix (2026-10-03, P2 THE NEED): requirements ↔ instruments

Every low-level need stated in `knowledge/ane/*.md` mapped to the instrument that
answers it, with fleet status from the matrix above. Items without a working
instrument are listed as GAPs — no hand-waving.

| # | Need (knowledge source) | Instrument | Status |
|---|---|---|---|
| 1 | Private class/selector discovery — `_ANEClient`, `_ANEModel`, `_ANERequest`… (`02-private-api`) | `bench/ane-probe.m` class enumeration → CSV | run on M4 + M5 (rows above) |
| 2 | MIL program text + BLOBFILE format, in-memory compile (`03-program-format`) | `bench/ane-dma-test.m` self-contained MIL generator (Orion/zoo-fork conventions) | M4 (EXP lineage); M5 buildable |
| 3 | compile → load → evaluate chain in user space (`02`, `07-private-api-verified`) | `bench/ane-dma-test.m`; original M4 op-scan driver lived in the harness | PARTIAL — see GAP-2 |
| 4 | IOSurface tensor passing, incl. 1 MiB streaming sizes (`04-runtime-and-memory`) | `bench/ane-dma-test.m` IOSurface arms | M4 (erratum verdict) |
| 5 | Power-rail probing without dead-counter lies — F-24 (`06-measurement`) | `tools/enginemon` (IOReport) + `bench/power_ab.py`, `power_coreai.py`, `power_phase_probe.py` | enginemon rebuilt + run on M5 Max 2026-10-03 (identity + channel table emitted); power scripts M4-proven |
| 6 | System-wide activity attribution — F-23 (`06`) | `bench/syswide_ane.py` (`--no-prompt` honoured; `--help` checked 2026-10-03) | M4-proven (EXP-004/005) |
| 7 | Silent-fallback + region counting without glob double-count — F-25/26/27 (`03`, `05-gotchas`) | `bench/probe_ane_regions.py`, `bench/aot_verify.sh` | M4-proven (EXP-005) |
| 8 | Controlled-arm contention with MUST-FIRE positive control — F-21 (`04`) | `bench/power_ab.py` arm control, `bench/interference_coreai.py` | M4-proven (EXP-004) |
| 9 | Latency protocol, cold-vs-warm discipline — F-12/13 (`06`) | `bench/latency_protocol.py`, `bench/jevbench_ane.py` | M4 + M5 (EXP-022 rows) |
| 10 | 1 MiB kernel-DMA erratum check (Yoon M3 → our M4/M5) (`05`) | `bench/ane-dma-test.m` | M4 negative result (EXP-001/022 lineage) |
| 11 | QoS ladder arms (`01`, `02`) | `--qos` flag in `bench/ane-probe.m` + `bench/ane-dma-test.m` | arms exist; ladder sweep only run in harness era — see GAP-2 |
| 12 | Oracle-fidelity gate for re-authored ports ("a port without gates is a guess") (`03`, `09-origins`) | `bench/gate_reranker_ane.py`, `bench/correctness_head.py`, `bench/jevbench_ane.py` | M4-proven (EXP-013 gate; EXP-018 230/231) |
| 13 | Machine identity attribution on every instrument (`FLEET` hygiene) | `bench/identity.py`, wired into power probes + enginemon | both machines verified |
| 14 | Bench-report import from external harness runs | `bench/import_bench_reports.py` + inbox (`HUB/bench`) | working (m5max-s* rows) |

**GAPs (stated plainly):**
- **GAP-1 — M5 energy rows**: `power_ab.py` never run with sudo on the Studio
  (already a known GAP above; unchanged).
- **GAP-2 — harness-era drivers not in-tree**: the original M4 op-scan driver and
  the QoS-ladder sweep ran inside the old harness; their successors here cover
  the primitives (`ane-probe.m` full scan, `--qos` arms) but the sweep scripts
  themselves live only in the archive (`M4-Partage/local_ai_stack/work/ane_probe/`,
  mapped in `ARCHIVE-MAP.md`). Porting them in-tree is a candidate follow-up.
- **GAP-3 — grounding-span re-derivation**: `knowledge/ane/grounding/cache/`
  lives on the mini only; a Studio re-emit cannot re-pin spans (observed 2026-10-03:
  a cache-less re-emit rewrites 342 span-bearing lines — guarded against by
  append-only emission; see `09-origins` commit). The instrument to close this is
  a cache-sync pass from the mini clone (read-only side is safe).
