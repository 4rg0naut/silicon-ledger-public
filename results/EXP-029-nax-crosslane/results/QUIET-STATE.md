# Quiet-state survey + idle-power spread — 2026-10-10 (Mac17,14, macOS 27.0.1/26A434)

Why this exists: past sessions showed unexplained slowdowns and nobody could say what was
contending. oMLX can be quit; Apple's background daemons cannot. This is the "what else is
running?" instrument, and it immediately paid off — see the spread below.

Tools (this pack): `harness/quiet_probe.sh` (snapshot: processes/daemons/thermal/power/display +
canary + engines), `harness/canary.c` (fixed CPU/memory work, build **-O0** — `-O2` deletes the
loops as dead code, first version measured `0.0000 s` and `inf GB/s`).

## 1. Three adjacent 5 s windows — and a 40 % swing with the SAME process set

| shot (UTC) | oMLX | GPU Energy / 5.14 s | GPU idle power | suspects up |
|---|---|---:|---:|---:|
| 14:50:48 | **up** | 611.5 mJ | 118.96 mW | 20 |
| 14:51:13 | down | 437.9 mJ | **85.19 mW** | 18 |
| 14:51:44 | down | 616.0 mJ | **119.84 mW** | 18 |

oMLX was **not** the variable: with it down, adjacent windows read 85 and 120 mW.

## 2. The 30 s, 1 Hz follow-up — the real picture

`tools/enginemon/enginemon --interval 1000 --duration 30 --json --out …` (raw preserved:
`results/quiet-power-20261010T1452Z.jsonl.gz`). Per-second GPU power (mW):

```
31 26 26 27 25 27 25 26 28 26 26 26 27 26 26 35 28 25 26 35 104 82 34 33 33 34 56 60 25
```

| min | median | max | spread |
|---:|---:|---:|---:|
| 25.1 mW | 26.9 mW | 104.3 mW | **4.2×** |

**The idle band is ~25–27 mW; excursions to 56–104 mW appear inside the same 30 s.** The three 5 s
windows in §1 (85–120 mW) were therefore *all* taken during elevated regimes — i.e. every one of
them would have been an invalid measurement window, in *either* oMLX state.

Consequence: the quantity that breaks our benchmarks is **not** the loaded LLM, it is an
intermittent background GPU user. Any energy/joule number must be taken with the idle band verified
before and after the window, or it is noise dressed as a result.

## 3. Who is actually running (watchlist, activity not just presence)

Present and *moving* during the survey (18–20 suspects):

| process | observed | note |
|---|---|---|
| `VTEncoderXPCService` ×3 | **11.9 % CPU** on one instance | video encode — an active background encoder is a serious contender |
| `avconferenced` | top-5 CPU | conferencing daemon |
| `mediaanalysisd`, `photoanalysisd`, `photolibraryd` | up | Photos ML pipeline (GPU/ANE capable) |
| `cloudd` ×2, `bird`, `backupd` | up | iCloud + Time Machine (audit notes record TM never completing) |
| `mds` / `mds_stores` ×9 / `corespotlightd` | up | Spotlight indexing workers |
| `corespeechd`, `assistantd`, `modelcatalogd` | up | Siri / model catalog |
| `aned`, `ANECompilerService` | up | ANE services (idle: ANE floor duty 0.0 %) |

Also present: `ScreenTimeAgent`, `powerd`, `WindowManager`, Safari/WebKit, `omp` (this agent).
Assertion holders keeping the system awake: `powerd, screensharingd, sharingd, runningboardd, omp,
coreaudiod` — **screensharingd/sharingd** is notable: screen sharing can hold GPU/compositor work.

Display channels (`DISP*`/`DISPEXT0-3 RT RD/WR`) move continuously — consistent with the known
connected-display VMAX pin (file 10 Q1), i.e. a *constant* background, not a spike source.

## 4. Canary baseline (this machine, this session, oMLX down)

| metric | value |
|---|---|
| `scalar_loop_s` (2e8 iterations, volatile) | **0.1191 s** |
| `memcpy_GBps` (256 MiB × 4, single thread) | **36.43** |
| `hash_loop_s` (2e8 iter, LCG+xor) | **0.3798 s** |
| `acc` / `hash` (determinism check) | 5323371213918391040 / 2243151161 |

Re-run the canary before/after a benchmark: if it moved, the machine changed — not the workload.

## 5. Gate for every measurement window (adopted)

1. `sh harness/quiet_probe.sh <label>` → refuse if `oMLX=UP`, if suspect daemons are *active* (not
   merely present), or if the engine baseline is outside the idle band.
2. Require GPU idle power in **~25–30 mW** (this box) for ≥10 s before starting, and re-check after.
3. Discard any window whose pre/post idle differs by more than ~20 %, or whose within-window
   per-second series shows excursions beyond the baseline band.
4. Record canary + idle band **in the evidence file**, next to the results.

## 6. Caveats

- One machine, one OS build, one session; the specific band (25–27 mW) is *this box today* — the
  protocol is the deliverable, the numbers are context.
- Energy channels are cumulative; rates come from enginemon's `IOReportCreateSamplesDelta`.
- `CPU Energy`/`ANE0` rails stay 0 on this box (frozen/gated — see enginemon README); only
  `GPU Energy` is usable unprivileged here.
- The spike sources are *not* attributed in this pass (the observation captured power, not
  per-process GPU time). Attribution is a follow-up: correlate spikes with `VTEncoderXPCService` /
  `mediaanalysisd` / WindowServer activity.
