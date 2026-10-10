# Tooling inventory — what already exists, and what should be reused (2026-10-10)

Owner's prompt: *"I've had quite a lot of previous results, dig in the old stuff… probes, harnesses,
we might already have QUITE a lot of them."* Correct. This maps it, and — honestly — records where
the work in EXP-029 **duplicated** existing instruments.

Tooling lives in **five** places:

| where | what it is | examples |
|---|---|---|
| `silicon-ledger/results/EXP-*/harness/` | per-experiment probes (versioned sources; binaries gitignored) | EXP-025 (57 files), EXP-027 (23), EXP-026 (17), EXP-029 (15) |
| `silicon-ledger/bench/` | **cross-experiment** measurement + ledger tooling (~40 scripts) | `latency_protocol.py`, `power_ab.py`, `_power.py`, `na_tiles.py`, `build_measurements.py`, `results_table.py` |
| `silicon-ledger/tools/` | long-lived instruments/services | `enginemon` (ours), `granite-runner`, `embed-server`, `rerank-server`, `memory-stack`, `archive`, `publish` |
| `silicon-ledger-bench/tools/` (separate repo) | model generators + stability | `gen_models.py`, `gen_coreml.py`, `stability_run.sh`, `spread.py` |
| `work/`, `exp022-raw/` | **unversioned scratch** (raw captures, older probes) | `work/Mference`, `exp022-raw/*` |

## The canonical instruments (use these; do not reinvent)

| need | canonical tool | convention it fixes |
|---|---|---|
| **latency** | `bench/latency_protocol.py` | warm-up **10 discarded**, measured **100** back-to-back, report **p50/p95/min** + `ms/token`, **work unit stated on every row** |
| **energy (joules)** | `bench/power_ab.py` + `_power.py` (the shared powermetrics rail parser) | powermetrics rails; **sudo window**; the only route to a real **ANE rail** |
| **lane activity (unprivileged)** | `tools/enginemon` | IOReport; `ANEXL U` = ANE-exclusive, `PS13` = generic GPU; documents its own two traps |
| **ledger rows** | `bench/build_measurements.py`, `results_table.py`, `verify_extraction.py`, `audit_measurements.py`, `identity.py` | one source of truth; every value must literally appear in its source report |
| **placement / routing** | EXP-025 `coreml_plan.py`, `coreml_route_sweep.py`, `plan_devicesupport.m`, `coreml_findcallers.m` | read Core ML's plan, don't guess |
| **matmul2d tiles** | `bench/na_tiles.py` + `na_tiles.metal` (original), EXP-027 `p27_r8.m` / `p27_na_r8.py` (ladder + CPU oracle), `p27_m2d_xcode_probe.metal` | tile-validity ladder, checksum-gated |
| **interference / contention** | `bench/interference_coreai.py`, `calibration_axis.py`, `eval_dev_calibration.py` | relevant to the quiet-window problem |
| **ANE model benches** | `bench/bench_ane_variants.py`, `granite_ane_variants.py`, `laya_ane_bench.py`, `jevbench_ane.py`, `bench_encoder.py`, `eval_ane_embedder.py` | model-level ANE benchmarking patterns |

## Duplication map — EXP-029 vs what already existed

| EXP-029 artifact | verdict | existing ancestor |
|---|---|---|
| `harness/nax_ladder.m`, `mm_inline.metal` | **duplicate** | `bench/na_tiles.metal` + EXP-027 `p27_r8.m` (same idea, better form: threadgroup staging + cooperative destination) |
| `harness/nax_gemm/` (Swift GEMM probe) | **new** (dtype/lane control MetalHLO lacked) — but its **timing convention should adopt `latency_protocol.py`** | MetalHLO's own runner (no f16, always MLX); timing conventions from `latency_protocol.py` |
| `harness/nax_gemm_matrix.sh`, `nax_lane_matrix.sh` | partially duplicate | MetalHLO runner's `--filter` already does this; ours adds the MLX-free/dtype angle |
| `harness/ane_gemm_probe.py`, `make_gemm_models.py` | **new content** (no GEMM-matrix ANE probe existed) — but model-build/plan/predict pattern repeats `bench_ane_variants.py` / EXP-025 `coreml_plan.py` | reuse their conventions |
| `harness/nax_gemm_energy.sh`, `ane_gemm_energy.sh` (enginemon) | **complementary, not a replacement** | `bench/power_ab.py` is the canonical **joule** path (and the ANE rail needs sudo); enginemon gives unprivileged **attribution** |
| `harness/quiet_probe.sh`, `canary.c`, `power_correlate.sh` | **new** (contention gate) — overlaps the *theme* of `bench/interference_coreai.py` | check that script before extending ours |
| EXP-029 docs / records | keep | — |

## Actions that follow

1. **Adopt `latency_protocol.py`'s convention** (10 warm-up / 100 measured / p50+p95+min / work unit)
   in the new GEMM probes — otherwise we add incomparable numbers to a corpus that already fought
   this battle ("142 latency figures under four conventions").
2. **Use `power_ab.py` (sudo window) for any joule claim**, especially the ANE rail; keep enginemon
   for unprivileged lane attribution (`ANEXL U` vs `GPU Energy`).
3. **Stop hand-rolling matmul2d kernels**: MetalHLO (working MPP path) + EXP-027's ladder as the
   correctness reference is enough.
4. **Read `bench/interference_coreai.py` + `calibration_axis.py`** before growing the quiet-probe.
5. Ledger rows for anything we cite must go through `build_measurements.py`/`verify_extraction.py`,
   not into prose only.
