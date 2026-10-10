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

## 7. CORRECTED: two GPU-power REGIMES under a continuous Screen-Share session (2026-10-10)

**Correction.** An earlier version of this section called the difference "screen share vs not
driving". That was wrong: the owner drives this Studio over Screen Share **throughout**
(owner-confirmed). Both captures below were taken under Screen Share. The variable is *within* the
sharing session, not sharing itself.

| capture (1 Hz) | GPU median | min | max |
|---|---:|---:|---:|
| 14:52 (n=29) | **26.9 mW** | 25.1 | 104.3 |
| 14:59 (n=43) | **85.0 mW** | 32.6 | 166.9 |
| 15:0x re-check (n=29) | **82.7 mW** | — | — |

Channel-level diff of the two regimes (medians per second):

| channel | 26.9 mW regime | 82.7 mW regime | delta |
|---|---:|---:|---:|
| `DISP*` / `DISPEXT0-3 RT RW` (display) | 24,001,052 | 23,997,442 | **−0.02 %** |
| `UT_EXT_THROTTLE_MGPU03/12` | 24,004,006 | 23,989,675 | **−0.06 %** |
| `AGX RD/WR` events | 114.6 | **303.0** | **2.6×** |
| `AGX.Count_UT_Engagement_Perf_State_1` | 127.1 | **316.2** | **2.5×** |
| `GPU Energy` | 26.9 mW | **82.7 mW** | **3.1×** |

So: **display/compositor traffic is identical across the regimes while real GPU engine activity
triples.** The high regime is genuine GPU *work*, not display pinning, and not the ML daemons.

- CPU hints in the worst second: `avconferenced` 13.3 % + `WindowServer` 13.2 % +
  `VTEncoderXPCService` 8.1 % — consistent with a capture/encode + compositing path, but CPU% does
  not prove GPU submission.
- **Next instrument, needs one-shot sudo (repo policy: user-run):**
  `sudo powermetrics -i 1000 -n 20 --show-process-gpu --samplers tasks` during a high regime, to
  name the task that owns the GPU time.
- Protocol consequence: gate each window on **its own** observed band; never compare numbers across
  regimes. A true headless floor is still **unverified** and needs an SSH-only session.

### Locale hazard found while arming the gate (same run)

`LANG=fr_FR.UTF-8` on this box, and Apple CLIs emit comma decimals here: `ps` printed `9,1`,
`sysctl` printed `3072,00M`. Consequences, both **silent**:
1. `power_correlate.sh` (first version) died on `float("9,1")` — loud, easy.
2. `bench/_power.py`, the single source of truth for every power A/B, matched `([\d.]+)` only, so a
   localized `1234,56 mW` **failed to match and the sample was dropped** — no error, just fewer
   samples. `_power.py` now accepts both separators (self-tested: `1234,56` → 1234.56; `1,234.56` →
   1234.56), and all harnesses export `LC_ALL=C` as the belt to that braces.

## 8. The Studio has NO physical display — the display is created BY Screen Sharing (2026-10-10)

`system_profiler SPDisplaysDataType` on this box:

```
Displays:
  Écran virtuel de partage d'écran:      Resolution: 2724 x 1532
  UI Looks like: 1362 x 766 @ 60.00Hz    Main Display: Yes   Online: Yes
```

There is no monitor attached. The single Main Display is a **virtual display instantiated by the
Screen-Sharing session**, scanned out at 60 Hz.

Consequences:
- The constant `DISP*` / `DISPEXT0-3 RT RD/WR` traffic measured earlier (~2.4001e7 events/s, and
  the "connected display pins VMAX" note in file 10 Q1) is **that virtual display's composition**,
  not a physical panel — and it exists **only while a Screen-Sharing client is connected**.
- Disconnecting Screen Share should **remove the display entirely** (no scanout, no compositor
  target). The true headless floor is therefore expected to be **lower than anything measured so
  far** (both previous regimes, 26.9 and 82.7 mW, had the virtual display up). That is the cleanest
  baseline for EXP-029 and it is still **unmeasured** [T].
- Practical: for energy arms, SSH in and close Screen Share; then re-run `quiet_probe.sh` and the
  canary and record the new band before trusting any joule number.

## 9. HEADLESS BASELINE (SSH-only) — and two analysis traps (2026-10-10)

The owner connected from the MacBook Air over **SSH only** (Screen Share closed). State:

| observation | value |
|---|---|
| displays | **none at all** (`system_profiler` shows no `Displays:` section) |
| `screensharingd` / `WindowServer` | **gone** (the compositor only exists with a display) |
| `sharingd`, `VTEncoderXPCService`, `avconferenced` | still resident |
| GPU Energy | **zero-delta in 22/28 and 53/56 seconds**; when non-zero: 1.3–3.0 mW |
| `AGX RD` events/s | 23.5 (was 114.6 with Screen Share) |

| regime | GPU idle |
|---|---|
| **SSH-only, no display** | **≈ 0–3 mW** (mostly no counter movement) |
| Screen Share, regime A | 26.9 mW |
| Screen Share, regime B | 82.7–85.0 mW |

So Screen Sharing costs **~25–85 mW of continuous idle GPU power** here, on a box whose headless
floor is essentially zero. **Mandate: energy arms run SSH-only.**

### Trap 1 — a missing channel means ZERO (enginemon JSON)

`tools/enginemon/enginemon.c:337` skips channels whose per-interval delta is 0 unless `--all`:
`if (!show_all && chans[i].total - chans[i].reported == 0) continue;`

Consequence for analysis: **never take a median over "present" samples** — a channel that is absent
in a sample had delta 0, and computing a median only over the samples where it appeared
over-estimates the rate (our first pass reported "1.5 mW median" from 6/28 samples). Rate = Σdelta /
Σdt over the window.

### Trap 2 — `DISP*` / `DISPEXT*` / `VDD_*` "RT" channels are FREE-RUNNING (~24 MHz), not activity

Measured with **no display attached**: `DISP RT RW` 23.992 MHz, `DISPEXT0 RT RW` 23.994 MHz,
`VDD_SOC_CI_VOLTAGE_CHANGE_COMPLETION` 23.988 MHz — all ≈24 MHz, the same free-running family as
enginemon's documented `ANE_*_TRIG` trap (file 10 Q1 / enginemon README). They were ~24 MHz *with*
the display too, which is exactly why they looked "identical between regimes".

**This invalidates the display-traffic control used in section 7** (GOTCHAS-079): the claim that
"display/compositor traffic is identical while AGX activity triples" rested on channels that carry
no display information. What survives from section 7 is the **AGX** evidence (event counts that can
genuinely be zero): `AGX RD/WR` 114.6 → 303.0 /s and `AGX.Count_UT_Engagement` 127.1 → 316.2
between the two regimes. The regimes are real; the *control* was bogus.
