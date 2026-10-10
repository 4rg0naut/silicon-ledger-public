# WX-2 — Paper cross-validation report (arXiv:2606.22283 vs our M5 Max ledger)

Web-check 2026-10-08 (SearXNG via mini VM :8888 + direct arXiv fetch). Pin:
`raw/research-2026-10-08/arxiv_2606.22283v1.pdf`
sha256 `aae783440baf7630ba6b716647cebd0fc9e7590b85180a16378b525ef3398292` (302 pp,
measured on M1 + M5-base/H17s). Every xval row below carries its verdict:
CONSISTENT / CONFLICT-DECLARED / GAP-DECLARED. Nothing is adjudicated silently.

## Core-count question — CLOSED, triple-sourced (CONSISTENT)

Paper table 34.1 (28 compiler targets): suffix→NE-core ladder `base=4, g=8,
s=16, c=32, d=64`, decoded from the core-count field at HAL offset **0x238**;
`H17c → 32` (column labels it "A17 Max-class"), `H17s → 16` ("A17 Pro-class,
the M5" — the base M5). Our two device-side observations:

1. EXP-026 SU: coreai-cache ANE-region LLIR paths on this M5 Max resolve the
   **h17c** target directory names.
2. 2026-10-08 (`p27_mpsgraphtool_write_side.txt`): `/usr/bin/mpsgraphtool
   -specializeForDevice` on this machine emits the string **h17c** as the device
   ANE arch — a public tool independently resolving the same target.

⇒ **M5 Max = h17c = 32 compiler-visible cores** holds across three independent
sources (paper table + cache artifacts + public tool run here). The paper's
class-column omission of M-series parts on H17c/H17d is corrected by our
device evidence. Marketing "16" = H17s tier.

## Table 9.1 roofline diff vs our S1/S2 batteries

| Row id | Paper (M5/H17s) | Our anchor (M5 Max) | Verdict |
|---|---|---|---|
| xval-m5-gpu-compute-roof-fp16 | 30862 GFLOP/s | `m5max-s2-gemm8192-fp16-mps` 60750 GFLOP/s (18-core) | CONSISTENT: per-core 3086 vs 3375 GF/s (+9.3%), within clock/thermal slack between base-M5 and Max |
| xval-m5-gpu-bandwidth-roof | 229.7 GB/s | `m5max-s1-gpu-read` 561.6 / triad 555.1 GB/s | CONFLICT-DECLARED: streaming-roof vs steady-state read, and base-die bus vs Max bus — regimes incomparable, not adjudicated |
| xval-m5-cpu-bandwidth-roof | 130.4 GB/s | `m5max-s1-cpu-read` 273.5 GB/s | CONFLICT-DECLARED: same regime/die caveat |
| xval-m5-ane-matmul-roof | 10191 GFLOP/s matmul (18771 conv; ridge 424 FLOP/B) | no direct ANE TFLOPs row (our tile work rides GPU tensor units) | GAP-DECLARED: ANE saturation battery is the follow-on measurement; kept as the anchor it must clear |
| xval-m5-ane-dispatch-floor | 0.23 ms/dispatch (§9.3) | NX-C coreai matmul2d eval median 0.2398 ms | KEPT-APART: numerically adjacent, different stacks (ANE dispatch vs GPU tensor-op eval); conflation forbidden |
| xval-h17c-num-nes | 32 (table 34.1) | this machine resolves h17c (cache dirs + mpsgraphtool) | CONSISTENT ×3 sources |

## Corroborations harvested (outside the ledger)

- The ANE dtype whitelist we extracted from coreai-cache placement
  (`fp16, f8E4M3, si8, ui8, si16, ui16`) appears **byte-equal** in
  mpsgraphtool's public validation string — see `p27_mpsgraphtool_write_side.txt`.
- mpsgraphtool emits `original_model_N` / `specialized_model_N` naming identical
  to the coreai-cache scheme — same pipeline class confirmed from the public side.
- Attribution honesty (whole-corpus): the compiler chain (MIL→anec.*→hwx→aned),
  the MPS-MLIR dialect RFC (Apple, 2024-02), the hwx format lineage
  (mdaiter/eiln/freedomtan), and "ANE is far more energy-efficient than the GPU"
  are PUBLISHED prior art (paper 2606.22283 §9/§34, LLVM RFC, Apple docs). Our
  zero-hit territory remains: coreai-cache contents on macOS 27, `ane_family`,
  IOReport GPU counter semantics (`Perf_State`), per-tile matmul2d joules.
