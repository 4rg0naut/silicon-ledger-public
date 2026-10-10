# enginemon — NX-D slice proposals (for the tools/enginemon owner; this session did NOT edit that tree)

Source evidence: results/p27_nxd_nax_lenses.txt + raw/p27_nxd_*.jsonl (EXP-027, 2026-10-08, M5 Max 27.0.1).

## P1 — Correct PS13 semantics in README "M5 Max (v2.1)" calibration table
README/NAX notes treat `AGX.Count_UT_Engagement_Perf_State_13` activation as the
matmul2d (NAX) lens. Measured today: it fires identically for plain MSL
`simdgroup_matrix` dispatch (1.32M dispatches / 30 s → idle 0 → 125,798/tick).
It is a **top-perf-state UT engagement lens** (any saturated GPU compute), still
useful as GPU-vs-ANE discriminator (stays 0 under full-ANE work — AN-POS), but it
cannot separate matmul2d from classic tensor kernels. Suggest wording fix + note
that the only matmul2d-vs-simdgroup discriminator today is the matched-A/B
`GPU Energy` Δ.

## P2 — Document the 4096-channel JSON subscription cap
`--unfiltered` windows carry 4096 channels and DROP the `GPU UT AggD Stats`
AGX.Count_* gpu-na set that default mode carries (default set = 248/281
channels). Suggest: (a) print a truncation warning when the subscription
caps, (b) optionally a `--only <regex>` / `--exclude <regex>` filter so a
single run can carry the union of UT engagement + PMP0 breadth.

## P3 — Wall-clock channel guard
High-idle `24Mticks` channels (`GPUPH`, `GPU_CLTM`, `PWRCTRL`, floor
`*_BW` residency, PWRS0/1 TICKS/STRESS_LIM*) rise exactly with wall time — a
naive idle/load diff reports ~2.4× for them with zero activity. Suggest
marking them as residency class in the table output (or a `--activity-only`
mode filtering channels whose idle rate ≈ constant).

## P4 — Co-tenant Metal note (ops)
While a Metal surface-heavy server owns the GPU pool (oMLX ~25 GB loaded),
ANY enginemon subscription (wrapped or side-by-side process) makes the
coreai NDArray `ioSurface` allocation path fatal (NDArray+Pool.swift:77,
4096 B). MTLBuffer-only children are immune. Suggest a README ops line: coreai
harness windows on the Studio need surfaces headroom (user unloads oMLX
models); prefer MTLBuffer harnesses for calibration windows otherwise.

## Non-goals
No channel-classification changes requested: gpu-na tagging already matches
the "engagement, not verdict" stance (knowledge/ane/10 Q lines 19–25).
