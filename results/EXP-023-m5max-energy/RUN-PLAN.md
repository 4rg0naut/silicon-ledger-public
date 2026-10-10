# EXP-023-m5max-energy — RUN PLAN (reconstructed)

Goal: first per-engine per-unit energy baselines on M5 Max (Apple Silicon Studio,
macos 27.0-beta → 26.5 userland build host), closing 2024-era "GPU power not
measurable on M4" as far as the surface allows.

## Arms
1. quiet idle floor (105s, 1000Hz combined, no ScreenCapture, oMLX stopped by user) — DONE
2. minilm CPU batch (128-tok x300 + embed x1690/X2115) — DONE
3. minilm GPU metal (ane-off, x180 + embed x780/X285) — DONE (upper bound: thermal soak)
4. granite-31 CPU matched (795) + ANE matched (795, process ANE rail delta) — DONE
5. calibrations: gpu-clock 90/120/180, oc 6000 — DONE (all above floor; no clean sub-floor point yet)
6. cross-machine h16g vs h17c — deferred to paired run on M4 Studio

## Constraints honored
- sudo run by user via script (user-run sudo pattern), powermetrics -n (sample count, NOT -t timeout)
- oMLX stopped during capture; every session logs before/after idle check
- no fabricated rails: idle total 5920mW at "0 process breakdown" = unattributed (logged F-036)

## Incident (F-037)
Raw txt + original measurements.tsv lived in an untracked superproject results/ dir,
displaced during harness workspace-clone creation ~11:1x. Ledger reconstructed
same morning verbatim from session transcript (10 rows); raw captures lost.
Lesson: results land in the content repo (submodule), not in untracked paths.
