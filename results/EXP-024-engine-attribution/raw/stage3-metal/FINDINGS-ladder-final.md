# #8 fallback ladder — FINAL verdict (2026-10-06)

Goal (restated): find a **calibrated, discrete positive signal for the M5 GPU neural
accelerator ("GPU-NA")** at any reachable privilege level. All five stages executed; the
budget-gate ("stop at the first stage yielding a calibrated GPU-NA signal") was never
satisfied because **no stage produced one**. That is the answer, not a failure to look.

| stage | instrument | privilege | GPU-NA discrete counter? | verdict |
|---|---|---|---|---|
| 1 | UT Engagement centi-% histogram (`UT_EXT_THROTTLE_*`) | user | No — PMGR util, 2.6× under shader not tensor; failed calibration | trick, not metric |
| 2 | IOAccelerator PerformanceStatistics (ioreg keys) | user | No tensor/NA/UT key names present | dead |
| 3 | MTLDevice counterSets / MTLCounterSampleBuffer | user | Only `timestamp` set on BOTH M5 + M4; AtDispatchBoundary=False | dead (rich sets entitlement-gated) |
| 4 | powermetrics gpu_power + performance counters | **root** | **No** — gives whole-GPU `HW active residency` + `GPU Power` only; no `performance counters` block on this build | no discrete counter, but solid engagement+power denominator |
| 5 | IOReportCopyChannelsInGroup named-group probing | user | PMP0 `AGX-DCS-BW F7/F8`, `AGX Energy` floors = 90–96% **at idle** (display pins VMAX) | saturated; no idle/load separation |

## Root-specific finding (stage 4, `powermetrics_gpu_tensorops.txt`, 1067 samples)

- `GPU Power` and `GPU HW active residency` are the only per-GPU channels; no NA sub-unit
  telemetry. tensorops-load window avg 320 mW / peak 1.5 W (the gemm tail), pre-reload idle
  151 mW; the 09:35 spike to peak 72 W / avg 8.3 W is the **user's oMLX restart**, not the
  load (documented in the merge).
- Enginemon under root (`cal_*_priv.jsonl`) additionally confirms the **ANE is its own
  rail**: `ANE-DCS-BW F≥2` duty 62.3% under the ANE arm, 0.0% under tensorops — GPU and ANE
  cleanly separable at root, the reverse of `GPU Energy` which stays whole-GPU.

## Conclusion for the ledger

GPU-NA has **no discrete positive counter at user or root level** on macOS 27 / M5 Max.
The only defensible attribution number is the **matched-A/B Δ**: same matmul, `tensorops`
(MSL 4.0, lowers to NA at M≥400) vs `msl` (3.2 simdgroup), checksum-gated, and the delta in
`GPU Power` (root) / `GPU Energy` nJ (user) is the pJ/token for the tensor path — exactly the
unpublished number the pJ/token table (knowledge/ane/10) specifies. Cross-checked against the
macmon total (FINDINGS-macmon-xval) and the clean idle/tensorops powermetrics split here.

Dead ends are recorded, not papered over; the ladder is exhausted and closed.
