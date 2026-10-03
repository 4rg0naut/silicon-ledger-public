# EXP-001 — ANE operation map for this M4

**Question:** which MIL operations can the Neural Engine execute on *this*
machine/OS/toolchain combination?

**Method:** `ane-probe` builds a minimal single-op Core ML model per MIL op and
queries `MLComputePlan` for device placement.

```bash
cd repos/ane-probe
../../.venv/bin/python -m ane_probe scan
../../.venv/bin/python ../../bench/analyze_ane_scan.py <csv>   # summary
```

**Run:** 2026-09-20 · macOS 27.0 · coremltools 9.0 · ane-probe `c8e4600`

## Results

| Metric | Value |
| --- | --- |
| Ops scanned | 168 |
| `ok` (built + queried) | 130 |
| skipped (probe could not build) | 38 |
| **ANE-supported** | **100 / 130 = 76.9%** |

**Every dense-transformer op is ANE-capable:**
`matmul · linear · conv · add · mul · sub · softmax · gelu · relu · layer_norm ·
gather · transpose · reshape · reduce_mean · exp · erf · rsqrt · pow`

**Not ANE-supported (30):**
- transcendentals: `acos asin atanh cosh sinh tan`
- index / control flow: `argsort non_zero one_hot shape cumsum reduce_argmax reduce_argmin reduce_prod`
- scatter family: `scatter scatter_nd scatter_along_axis slice_update`
- RNN family: `gru lstm rnn`
- misc: `random_bernoulli random_categorical random_normal random_uniform non_maximum_suppression band_part reverse_sequence sliding_windows mod`

**Interpretation:** the ANE accelerates *dense compute* and punts on
*dynamic/stateful/control-flow* work — exactly the split that suits a
transformer encoder and explains EXP-003's result.

## Caveats
- `preferred=CPU` appears on every row and is **meaningless**: single-op models
  pay ANE transfer overhead, so the compiler prefers CPU. Only the `supported`
  column is informative.
- The 38 skipped ops are a probe limitation, **not** evidence about the ANE.
- Static compiler analysis; actual runtime behaviour can differ.

## Correction worth remembering
An ad-hoc single-op check I ran earlier (`ane_probe check conv`) reported
`conv → ANE: NO`. The full scan reports **`conv → ANE: YES`**. The hand-picked
parameters were the artifact. **Lesson: use the full scan, not single-op spot checks.**

## Artifacts
- `ane_support_results.csv` — the raw scan (168 rows)
- `ane_scan_M4.log` — full scan log

**Upstream value:** ane-probe's `results/` had only `M3_Max/macOS_26.2`; this is
the **first M4 / macOS 27 row**. Worth contributing back.

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
|---|---|---|---|---|---|---|---|---|---|---|
| ane-ops-scanned | single-op Core ML model | — | — | — | Ops scanned | 168 | ops | — | — | ours |
| ane-ops-ok | single-op Core ML model | — | — | — | ok (built + queried) | 130 | ops | — | — | ours |
| ane-ops-skipped | single-op Core ML model | — | — | — | skipped (probe could not build) | 38 | ops | — | — | ours |
| ane-supported-ops | single-op Core ML model | ANE | — | — | ANE-supported | 100 | ops | — | — | ours |
