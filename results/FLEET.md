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
| Mac Studio M5 Max | `Mac17,14`, 18C, 128 GB, macOS 27.0.1 (26A434) | h17c (CoreAI compile-target string; IOReport-visible board is the coarse `h17g` — per-die cores 32 vs 8 on h16g, arXiv 2606.22283 Ch24, `knowledge/ane/10` Q8) | calibration bench (`bda452aabd60bf26`, EXP-022) |
| Mac mini M4 | `Mac16,10`, base M4 + 10GbE, 16 GB | h16g (per-die 8 — arXiv 2606.22283 Ch24) | historical corpus (EXP-001..021, 716 `M4` rows) |
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
| power probes (×3) | run 2026-10-06 via sudo capture (`power_mlcore.py`, `power_coreai.py`; `m5-minilm-*`/`m5-granite-*` rows) | run (sudo powermetrics; energy rows 75 vs 4124 mW, 2.06 vs 11.45 mJ) | blocked: no powermetrics | — |
| `identity.py` | run 2026-10-03 | run — same schema, keys exist on any macOS | partial: needs app-side emit | — (non-Apple sysctl) |
| `to_openclaims.py --check` | run 2026-10-03: 679/679 valid | — (SDK venv not set up there) | — | — |

Asymmetry to close (known GAPs, em-dash policy):
- ~~M5 energy: no rows~~ CLOSED 2026-10-06 — sudo quiet capture (oMLX quit, euid 0):
  10 `m5-minilm-*`/`m5-granite-*` rows merged (MiniLM → GPU, 4.94 vs 11.40 mJ/emb;
  Granite ANE rail 261.1 mW lane-specific → S4 settled). M4 keeps its 3 `energy_mw`
  records of record; bands across instruments remain non-comparable.
- M4 through the Swift bench: never run; its 716 rows come from the Python/
  harness lineage, a different instrument — do not compare bands across them.
- iPad Air M2: zero probes. First useful artifact is an app-hosted `ane-probe`
  (class enumeration only); energy and IOReport arms stay Mac-only.

Regenerate matrix rows by running the cited commands on the cited machine and
appending dated lines here; never overwrite history.

**Operational rules (added 2026-10-06, user directive):**
- The Studio (M5 Max) production oMLX server is **never** probed with experiment models and
  **never** doubled by a self-started second server — a past doubling broke the production
  server and required a Mac reboot to clean (F-36). MLX-based measurement arms go *through*
  the existing server (API key via user), in a window of its own.
- **M5 metrics are measured only on the M5 Studio.** mini (M4) is plumbing/trivial-run
  convenience, never a stand-in machine for M5 numbers.
- Sudo on the Studio is human-terminal only: agents prepare one-shot scripts (pattern:
  `results/EXP-024-engine-attribution/raw/sudo/sudo_capture.sh` in the RE workspace); the user runs them.

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
- **GAP-1 — M5 energy rows**: ~~never run with sudo~~ **CLOSED 2026-10-06** — quiet
  window (oMLX quit, meta.txt euid 0 @07:30Z): `bench/power_mlcore.py` (coremltools-free
  Core ML re-host) + `bench/power_coreai.py` (granite97m, 3 lanes). 10 rows merged
  (`m5-minilm-*`, `m5-granite-*`); LADDER Rung 5 M5 column filled. Headline: MiniLM
  lands on **GPU** on M5 (4.94 vs CPU 11.40 mJ, ANE rail 0.0), Granite ANE rail moves
  only on `neuralEngine` (261.1 mW → S4 settled, EXP-022 thread 2). Raw:
  `results/EXP-022-m5max-baseline/raw/energy-close-2026-10-06/`.
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

## Threads — 2026-10-06 (h17-truth pass)

- **WATCH (D9a) — ANEForge release**: arXiv 2606.17090 artifact `comp-physics/ANEForge`
  is 404 as of 2026-10-06 (checked via api.github.com, `*.github.io` blocked here).
  Its release would walk the 24 per-task `kANE_*` counters end-to-end (B5 verified the
  name space live on h17c; values gated by the stats-descriptor mechanism) — unblocks
  per-dispatch telemetry without waiting on Apple.
- **RETEST (D9b) — R8 matmul2d multi-tile no-op on macOS 27.1 beta**: our evidence =
  stage4_load.log (GPUCompiler 32023, 27.0-beta, all multi-tile arms validation_failed,
  single 64×32 correct). Zakharko's harness runs tensor ops on **Xcode 26.1/26.x
  stable** ⇒ regression is beta-toolchain-local. Retest when 27.1 beta lands:
  `bench/na_tiles.py` extended to a multi-tile grid; optionally draft the FB report
  (our log + their working config = clean bisect). C6 harness is ready either way.
- **GAP stands (D9c) — Core AI placement-dump telemetry**: public web searched
  2026-10-06 (incl. Apple's MLX-M5 post re-fetch, D9 sources registered in
  `knowledge/ane/SOURCES.md`): no public surface dumps per-op placement decisions.
- **Ops note (D10), observed 2026-10-06**: network-service-order trap — default route
  stayed on dead Ethernet (gw 192.168.1.42, ARP dead) while a working Wi-Fi tether
  existed (en1, gw 10.137.121.147); unblocked fetches without config change via
  `curl --interface <en1-ip>`; permanent fix = unplug the dead uplink or reorder
  services with `networksetup -ordernetworkservices`.
- GAP-2 addendum 2026-10-06: the fork's `bench` MSL-gemm target was uncommitted and is
  gone after a `swift build` refresh of the upstream checkout (cd1f27f); C6's successor
  in-tree is `bench/na_tiles.py` (TorchMetalKernel route, proven pattern) — closes the
  MSL A/B driver port for the NA case specifically.
