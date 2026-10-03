# EXP-022 — M5 Max baseline and cross-check (complete)

**Date:** 2026-09-26/27 · **Machine:** Mac Studio **M5 Max** (`Mac17,14`), 18 CPU (6P+12E),
40-core GPU, 128 GB, macOS 27.0 (26A428), Xcode 27 · **Fingerprint:** `bda452aabd60bf26`
**Status:** COMPLETE. The 03:17 CEST scheduled capture ran clean end-to-end
(stability 3/3 GOOD first pass, max cross-run spread 3.66%): ssample/enginemon/xctrace/AOT
windows all present. See "Final capture" and the gate memo. The 21:30 abort (1 GOOD/20,
`$SSSAMPLE` unbound-var typo) remains documented under "Session contamination"; the
earlier 21:09Z degraded run and the 16:05 clean window still serve as the contamination
measurement. See "Open threads".

---

## Question

Does the M4 ANE porting recipe (fp16 everywhere, no fp32 ops/literals, RoPE as graph
inputs, 1×1 conv + BC1S, no scatter/RNN/control-flow) still hold on the M5 Max, and can
this machine's `silicon-ledger-bench` output be merged into the ledger on the same join
keys as the M4 corpus?

## Method — and the structural difference from every earlier EXP

On the M4 machine the agent ran on a **cloud** model, so the machine under test stayed
clean. Here the agent runs **locally via oMLX** (`omlx-server`, ~30 GB RSS): every token
the assistant generates is live GPU inference on the machine being measured. Measurement
windows therefore require the agent and oMLX to be **stopped**, enforced by a scheduled
(cron) capture with an idle guard: load average sampled 2× over 15 min, must stay < 4.0
before any measurement starts.

## Exact commands

```
# scheduled capture (crontab: 30 21 * * *), CWD fixed to the bench repo:
/bin/zsh exp022-raw/final_capture.sh
#  -> idle guard, bench probe, 3×GOOD stability loop (exp022_final),
#     bench all, bench diff vs examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json,
#     ssample windows (idle/bench ane/bench coreai), enginemon raw, xctrace --launch,
#     AOT region counts (coreai-build, h17g + h16g)
# s4 rerun in the 16:59Z quiet window:
/bin/zsh exp022-raw/s4_rerun.sh
# ane-probe build (note: -framework ObjectiveC fails to link here; Foundation carries libobjc):
clang -O2 -o ane-probe bench/ane-probe.m -framework Foundation
# ledger merge (non-destructive, one row per REPRODUCE.md claim):
python3 bench/import_bench_reports.py examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json \
    --as examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json --apply
```

Scripts and logs: `raw/` here, full (incl. traces) at `/Volumes/data/OpenFox/dev_m5max_re/exp022-raw/`.
Integrity of that scratch tree: `cd exp022-raw && shasum -a 256 -c MANIFEST.sha256` (3486 files).

## Numbers

**Ledger:** 19 M5 rows imported (`m5max-s1-*` … `m5max-s4-*`, `results/LADDER.md` walks
them). Headlines: GPU read [m5max-s1-gpu-read] 561.6 GB/s, fp16 GEMM
[m5max-s2-gemm8192-fp16-mps] 60750 GFLOPS, ANE int8 peak [m5max-s3-peak-int8-d128]
13.1 TOPS, dispatch floor [m5max-s3-dispatch-floor] 0.119 ms/eval, Core AI matmul
[m5max-s4-coreai-matmul] 88.1 TOPS at **0 ANE regions**.

**Cross-check (16:05–16:38Z quiet window, agent+oMLX stopped):** stability PASS — 3 GOOD
runs, max spread 9.43% (cpu_triad), 0 failures; `diff vs example`: every S1 GPU row and
every S2 claim row within ±1–2%; S3 dispatch floor 0.119→0.108 and SRAM cliff
reproduced, two peak rows +8.0%/+7.4% *fast* of reference (outside their ±5% tolerance,
explained by the dispatch-floor drop, not by load); S4 lost to a harness bug (wrong CWD
— `models/coreai/` not found), re-run in the 16:59Z window: matmul **60.9–66.3 TOPS
against the 75–95 band**, deep_fp16 0.49–0.52 against 1.8–2.1 — a real, systematic
slowness while S1–S3 reproduce; cause open (placement is GPU-only per the AOT artifacts).

**S4 at artifact level:** all three bench Core AI graphs × both boards (h17g, h16g) AOT to
**0 `*ANE_region*`** — pure MPSGraph bundles. The compiler *attempted* ANE:
`ANECCompileOffline() failed: OSStatus=0, aneCompileStatus=1` with an **empty ErrorList**
(logs: `raw/aot.log`, `raw/aot-region-counts/` note files).

**ANE observability on M5 (the M4 blind spot, solved):** Instruments `ane-hw-intervals`
counts **0 intervals under confirmed ANE load** (matches M4). `enginemon` is blind on M5
(M5 exposes PMP0, not the M4 `AMC Stats`/`PMP` groups; `ane 0` interrupts are gone —
only `dart-ane0 0`, which stays 0 even under load). A `ssample` harness built on the
SiliconScope (MIT) `SiliconScopeCore` library reads the live signal: **PMP0 `DCS BW`
residency histogram, "ANE" lane: 0.00 GB/s idle → 52–66 GB/s during `bench ane`,
156.80 GB in 10.4 s with the GPU at 5 GB**. Power rails on M5 Max report in a slow
regime (batched ~2.1 s for GPU, ~30 min for CPU/ANE/DRAM) — per-op energy rows on M5
are declared GAPs, not zeros.

**`_ANE` private API surface M4 → M5:** unchanged — 39 `_ANE` classes, 15/19 documented
names, all key signatures verbatim (including the `initWithDesctiptor:` typo),
**16 ANE cores on both chips**; new identifiers `h17g`/`h17`/board 544
(`raw/ane-probe.txt`, compare `knowledge/ane/`).

## Session contamination (measured, not assumed)

`gpu_copy` across windows: **380.5** (02:14Z example, pre-dawn) · **379.5** (14:27Z,
light activity) · **380.5** (19:47Z, run 1 of the scheduled capture, guard passed) ·
**72–91** (17:00Z, agent generating) · **59–85** (21:49–23:09Z, agent resumed mid-capture
→ stability ABORTED at 1/21 GOOD) · degraded `bench all` at 21:09Z: CPU/GPU rows −63%
to −81% vs reference. A local-inference agent and a clean measurement window are
mutually exclusive on this machine; every M5 row in the ledger comes from a
pre-dawn/quiet-window run.

## Final capture — 2026-09-27 03:17 CEST (cron, quiet)

`final_capture.sh` fired at 01:17:00Z and ran every step: idle guard passed first try,
stability 3/3 GOOD (attempt 1–3, no aborts), `bench all` + diff, three ssample windows,
enginemon raw, xctrace, AOT region counts. Artifacts: `raw/final-night/` (compact);
kept-complete original incl. 209 MB logs and the .trace at
`/Volumes/data/OpenFox/dev_m5max_re/exp022-raw/final-2026-09-27T01-17-00Z/`.

**Stability:** `gpu_copy` 380.57 / 380.47 / 380.52 GB/s across three independent runs —
max cross-run spread 3.66% (worst op `gpu_read`), everything else ≤0.17%. The stability
gate (3 GOOD, <10%) PASSES. All three runs classified **low band** by the band classifier.

**Cross-check vs the 02:14Z example (same machine, fresh-boot window) — the regime gap
is the headline:**

| suite | reproduces | diverges (low band) |
|---|---|---|
| S1 GPU memory | read +1.3%, write/copy/triad ≤0.1%, tensor_copy +0.3% | cpu_read −81.5%, cpu_triad −72.6%, cpu_write −5.3% |
| S2 GEMM | int8-msl +0.6%, fp8 −5% | 512-class mps/msl +60…+155% (worst gemm_1024_int8-mps +262%) |
| S3 raw ANE | shape/cliff reproduced (sram 94→168 MB 3.07→5.34 ms) | everything +43…+192% slower; dispatch floor 0.119→0.276 ms |
| S4 Core AI | — | deep_fp16 1.06→4.82 ms (+353%), regions still 0 |

GPU memory bandwidth is bit-stable while **CPU memory, GEMM dispatch and raw-ANE eval are
2–5× slower** with oMLX resident (~103 GB) and the agent process alive-but-idle. The
16:05 window reproduced S1/S2 within 2% *with oMLX loaded* — so residency alone is not
the cause; the discriminating factor is time-since-boot / memory-pressure history (this
window followed a night of 6–20 GB export workloads). Honest label for tonight's numbers:
**low band, stable, mechanism unresolved** — do not merge them over the clean-window rows.

**ssample (the reason the 21:30 window died): PMP0 ANE lane live and sharp.**
`bench ane`: peak 49 GB/s, **150.6 GB moved over 18.2 s with GPU lane at 0.00**;
idle control max 4 GB/s. ANE activity is measurable on M5 Max via DCS BW lanes even
though every energy/interrupt channel is dead.

**xctrace:** ANE intervals 0 (busy 0.00 ms) — the Core AI blind spot, artifact-confirmed
on both machines. **AOT probes:** `regions=0` on all six (matmul/deep_fp16/deep_int8 ×
h17g/h16g) with `ANECCompileOffline() failed OSStatus=0 aneCompileStatus=1`, ErrorList
empty — now reproduced in the quietest window, so it is system state, not load noise.
Counterpart: EXP-023 the same night compiled a *converted* (non-MPSGraph) Qwen3 bundle
to **2 ANE regions** and ran it on the ANE at 71 ms/pair — the ANE is reachable; the
MPSGraph→ANE offline path is what regressed.

## Verdict — gate memo (final)

**Conditional GO, scope narrowed.** (1) The M4 ANE authoring recipe still *validates*:
S3 private-API surface intact and reproducible in shape; a converted bundle gets real ANE
regions and real ANE bandwidth (EXP-023). (2) **Core AI dispatch via MPSGraph is NO-GO
on macOS 27.0 on this machine:** 0 regions across six probes and two machine states,
`ANECCompileOffline` fails with an empty error list, and the python runtime cannot load
AOT-specialized `.aimodelc` bundles at all (error 0 on every delegate) though it
JIT-specializes the same graph onto the ANE fine. (3) Absolute-speed bands (S3/S4) are
**regime-split** — fresh-boot vs memory-pressured differ 2–5× on CPU, GEMM and raw ANE;
published bands are only valid in the regime that produced them. REPRODUCE.md's S4 band
remains unverified (see Open threads). (4) Energy rails for the ANE: GAP stands;
bandwidth is the proxy. Net for the LADDER: M5 columns stand on the clean-window rows;
tonight's low-band report is filed as a regime artifact, not merged into the ledger.

## Open threads

1. ~~Quiet-hours `final_capture.sh` rerun~~ DONE 2026-09-27 03:17 CEST — gate memo
   written above. New follow-up from it: identify the fresh-boot → low-band mechanism
   (candidate: repeat one CPU-bandwidth op hourly for a day, oMLX resident throughout).
2. S4 systematic slowness: GPU-only placement explains the *where*, not the *how slow*.
3. REPRODUCE.md doc bug: `coreai_deep_int8` band "0.6–0.8" contradicts the committed
   example's own derived TOPS (2.28) and reference median (0.9421 ms) — the doc band
   matches neither its example nor the rerun (0.30–0.34 at bench's flops constant).
4. M4 has never run the bench suite → LADDER Rung 1 M4 column is GAP.
5. oMLX power draw during agent sessions makes idle-guard alone insufficient;
   next captures require the app actually quit (guard should check for it).

## Raw artifacts

`raw/` — capture scripts (clean_capture.sh, s4_rerun.sh, final_capture.sh), cron.log,
probe/env dumps, stability logs (both windows), diff-vs-example outputs, bench-all logs,
bench report JSONs (clean 16:37Z + degraded 21:09Z), enginemon/ssample/xctrace outputs,
aot.log, findings-so-far.md, plus `raw/final-night/` (the 2026-09-27 03:17 CEST capture:
stability.log, good-runs.txt, diff-vs-example.txt, aot.log, xctrace counts, ssample ANE
window, report.json, env). Kept-complete originals (incl. the 174 MB AOT bundle set,
209 MB capture logs and .trace files): `/Volumes/data/OpenFox/dev_m5max_re/exp022-raw/`.
The stability-run and cross-check reports also live in the public bench repo under `results/`.
