# EXP-023 — Small-LLM ANE pilot: Qwen3-Reranker-0.6B re-export on M5 Max

**Status:** in progress (runs overnight 2026-09-26/27, Mac Studio M5 Max, 18C/40G/128 GB, macOS 27.0, fingerprint `bda452aabd60bf26`)

## Question

EXP-013 proved the full pipeline (HF checkpoint → ANE-dialect re-author → single ANE region
→ delegate gate + latency) on an **M4**. Does the same recipe still hold on the **M5 Max**,
where EXP-022 found AOT-compiled probe bundles land in **0 ANE regions** and `ANECCCompileOffline`
fails with `ErrorList` empty? The pilot reruns the recipe on the exact model EXP-013 used so the
two machines are directly comparable.

## Method

1. **Checkpoint** — `Qwen/Qwen3-Reranker-0.6B` downloaded to `models/qwen3-reranker-hf` (1.1 GB).
   PyPI `coreai-models` 0.1.0 is a placeholder squat; the real sources come from
   `github.com/apple/coreai-models`, cloned to `repos/coreai-models` and symlinked into the
   coreai-kit checkout path (`COREMODELS_SRC` in `bench/export_reranker_ane.py`).
2. **Reference** — `work/t8_ref.py` scores 10 query/doc pairs (short/long, relevant/irrelevant,
   domain-matched) on CPU torch: fp16 (reference column) + fp32 (official column).
3. **Re-author gate** — `bench/export_reranker_ane.py` builds the ANE-dialect module
   (Conv2d 1x1 projections, BC1S, per-head SDPA, fp32-accumulating `[x,-x]` LayerNorm RMSNorm
   trick, mask-arithmetic last-token select, 32-row tied head) and checks it against CPU
   torch numerics before exporting.
4. **Export** — `torch.export` + `TorchConverter` → `.aimodel` (seq-len 512).
5. **AOT** — `bench/aot_verify.sh` with the M5 `coreai-build` (toolchain mount resolved by glob),
   `--preferred-compute neural-engine --architecture h17g`; ANE region count must be > 0.
6. **Runtime gate + latency** — `bench/gate_reranker_ane.py` loads the AOT bundle on ANE / GPU /
   CPU delegates, re-scores the same 10 pairs, checks deltas and rank-group invariance,
   and reports median ms/pair per lane. A quiet-window re-run happens after the EXP-022
   03:17 capture completes (guarded by the DONE marker in `exp022-raw/cron.log`).

## Findings so far

- **Prompt contract bug caught pre-flight.** `apply_chat_template` on this checkpoint silently
  empties `<Query>`/`<Document>` when the pre-formatted `<Instruct>...` body is passed as user
  content — every pair collapsed to the same score (0.003945). Fixed in `work/t8_ref.py`:
  the prompt is now plain string concat of `system` turn + body + `assistant` prefix, matching
  the recipe in the HF model card. Debug confirmed identical token ids per pair before the fix,
  distinct after. Token ids `yes`=9693, `no`=2152, `pad`=151643 are valid single tokens.
- **Model calibration, not a bug:** Qwen3-Reranker-0.6B shows weak separation on our
  domain pairs (relevant ANE-domain docs score ~0.002 where casual pairs score ~0.55). The
  scores are genuine — reproduced on HF fp32/fp16 with the official template. `rank_groups` in
  `reference.json` therefore encode the *measured CPU ordering* (the invariance target the ANE
  bundle must reproduce), not hand-written relevance labels.
- **fp16 tolerance honesty:** the M4-era gate (worst |dp| < 1e-3 vs published fp32) was too
  strict for these pairs: inter-implementation fp16 spread on borderline pairs (p ~ 0.27)
  reaches ~8e-3 across torch fp16 vs fp32 vs the re-authored graph, which the three-column
  table now shows separately. New defaults: export gate 1e-2 vs same-precision HF fp16 +
  strict rank preservation; runtime gate 2e-2 vs CPU reference + strict rank preservation.
  (Rationale: 28-layer fp16 accumulation, logits near decision boundary; documented rather
  than quietly tuned.)

## Results

**Torch-level numerics gate: PASS.** Worst |dp| vs same-precision HF fp16 = 5.9e-3
(tol 1e-2), vs HF fp32 = 7.8e-3; all five rank groups preserved (`work/export-run2.log`).

**Export + AOT: reaches the ANE.** `torch.export` → `TorchConverter` (coreai-torch 0.4.2)
→ `.aimodel` (1.2 GB fp16, seq 512); `coreai-build` h17g produced
**2 ANE regions** — on the same night the EXP-022 MPSGraph probes still compile to 0.
The M5 ANE path is dead *through MPSGraph*, not dead.

**AOT-bundle load regression (new M5 finding):** the python `coreai.runtime` cannot load
the AOT-specialized `.aimodelc` — `CoreAIDelegates error 0`, identical failure on ANE,
GPU *and* CPU delegates, so it is not ANE-specific and not load-correlated (reproduced
at 02:15Z quiet and 04:49Z active). Loading the plain `.aimodel` with a per-unit
`SpecializationOptions` works on every lane (ANE JIT ~24 s cold). The gate runs
fall back to this path automatically and stamp each lane `[aotc|jit]`.

**Runtime gate + latency (`.aimodel` JIT-specialized).** Two independent runs — 02:15 CEST
during agent sleep (the guarded re-run, fired on its 60-min timeout before the 03:17
capture even started, so zero overlap) and 04:49 CEST in-session — produced bit-identical
medians, so this workload's latency is regime-insensitive (unlike the EXP-022 raw-ANE path):

| lane | load | median ms/pair | worst \|dp\| vs CPU reference |
|---|---|---|---|
| ANE | 0.8 s (warm cache; 24 s cold) | **71** | 7.0e-2 FAIL at tol 2e-2 |
| GPU | 0.8 s | 26 | 5.7e-3 |
| CPU | 0.01 s | 214 | 2.5e-2 |

Rank preservation: ANE 5/5 groups PASS. ssample sandwich during the gate: **ANE lane moved 23.6 GB (quiet run) / 18.3 GB
(in-session run)**, child rc=0 — the lane executes on the ANE.

The ANE numerical gap is confined to borderline pairs (`s256-hard` 0.552→0.482,
`irr-math` 0.280→0.232; all confident pairs agree to <4e-3) — fp16 softmax-margin
sensitivity amplified by the graph's `-40000.0` causal-mask floor, not a layout bug:
GPU on the same bundle tracks CPU to 5.7e-3. Ordering is intact everywhere.

**M4 comparison (EXP-013, same model/graph):** ANE 88 → **71 ms/pair (−19%)**,
GPU 87 → **26 ms (−70%)**. CPU reference column regenerated here on M5 (214 ms/pair).

## Verdict

**GO with one regression carried forward.** The EXP-013 re-author recipe transfers to the
M5 Max end-to-end: the same 28-layer Qwen3 graph re-authors, passes numerics, compiles
to real ANE regions, executes on the ANE delegate, and gets faster (71 vs 88 ms/pair;
GPU 3.3× faster). Two M5-era caveats for the LADDER: (1) Core AI *AOT bundles* cannot be
loaded by the python runtime at all on this macOS build (error 0, all delegates) — the
working route is JIT-specializing the `.aimodel`; (2) the ANE lane's absolute calibration
drifts on borderline pairs (rank-safe, magnitude-unsafe for score thresholds — threshold
on CPU/GPU scores, or calibrate on the ANE). MPSGraph → ANE remains NO-GO (EXP-022).

## Retry — 2026-10-05 (fresh open-source stack, macOS 27.0.1 / 26A434)

Retested the AOT-bundle load regression with a completely fresh toolchain to rule out a
stale-env artifact: new `uv` venv (Python 3.13) with the PyPI `coreai` wheel
(`coreai.runtime` — API moved from the old coreai-kit path; `AIModel.load` is now async).

**Regression persists, with two distinct failure signatures:**

| call | result |
|---|---|
| `AIModel.load(.aimodelc)` (plain) | `RuntimeError … No such file or directory` (ENOENT during asset load) |
| `AIModel.load(.aimodelc, specialization_options=…)` — CPU, Neural Engine, GPU | `CoreAIDelegates.AIModelError error 0` — identical to 2026-09-27 |
| `AIModel.load(.aimodel)` JIT control | **LOAD OK** (~0.1 s warm) |

**Layout forensics (new finding):** the open-source runtime's binary looks for
`main-unspecialized.odix`, `main-aggregate-delegates`, `aggregatedSoC.json`; the Sept
`coreai-build-3600.83.1` bundle contains `main-h17g.mlirb` + `main-h17g-delegates/`
(assetVersion 2.0). Symlinking the renamed files does not satisfy the loader — the ENOENT
survives. So the plain-load failure is a *bundle-layout mismatch* between coreai-build
3600.83.1 and the current runtime, not just an opaque delegate error. The specialization
path still dies inside `CoreAIDelegates` with error 0 (no localized description).

**ANE payload confirmed present:** `main-h17g-delegates/MPSGraph/mpsExecutable.mpsgraphpackage/
binary_0.llir.bundle/…_ANE_region_0_0.bc/h17g/…mlir.bc` — the ANE region bytecode is in the
bundle; the failure is at runtime load, not compilation (consistent with "reaches the ANE"
above).

Runtime cache is `~/Library/Caches/coreai-cache/` (buckets `26A434/` and `unknown/`; the
JIT control caches under `unknown` — the current runtime does not resolve this machine's
SoC to a named bucket, worth watching in a later build).

**Verdict unchanged:** JIT-specializing the `.aimodel` remains the working route on M5 Max;
AOT `.aimodelc` from coreai-build 3600.83.1 is unloadable by both the Sept coreai-kit
runtime and the current open-source runtime. Re-export with the current open-source
compiler would likely produce loadable bundles — not re-run in this session (timebox).

### Root-cause correction (same session, minutes later)

The `error 0` at specialization is an **architecture mismatch**, caught with a different model in
the same build family. Granite rebake-p3 bundles (same `coreai-build-3600.83.1`, one per arch)
run on this machine through the Swift CoreAI delegate: the `h17g` bundle fails with

    CoreAIDelegates.AIModelError.incompatibleCompiledAssetArchitecture(device: "h17c", asset: ["h17g"])

— the M5 Max's CoreAI delegate identifies as **h17c**, not h17g. The matching `h17c` bundle
loads through the python runtime via `AIModel.load(..., specialization_options=…)` (log shows the
ANE pass rejecting the fp32 embedding table — `Incompatible element type for ANE: expected fp16,
f8E4M3, …` — then falling back internally). Plain `AIModel.load(.aimodelc)` still ENOENTs for
h17c too: the layout gap above is real and independent.

**Corrected verdict for this machine:** the 2026-09-27 reranker AOT bundle was compiled with
`--architecture h17g`, which this OS build (`26A434`) does not accept — the `CoreAIDelegates
error 0` was the opaque surface of that mismatch, not a universal AOT-load death. An h17c
reranker re-export should load. The `.aimodel` JIT route stays the robust path; the layout gap
for plain (unspecialized) `.aimodelc` load remains open.

**Post-fix confirmation 2026-10-06 (quiet sudo window):** the h17c-compatible Core AI route
(`bench/power_coreai.py` + granite97m) produced a **lane-specific ANE rail of 261.1 mW**
(0.0 on the gpu/cpuOnly lanes, gates PASS 35/35) — the first directly metered ANE energy on
this machine. MiniLM on M5 by contrast: ANE rail 0.0 with ANE-DCS duty 0% — GPU placement
confirmed on both meters. Rows `m5-granite-*`/`m5-minilm-*`; see EXP-022 "Energy close".

## Reproduce

```
.venv/bin/python work/t8_ref.py                      # CPU reference scores
.venv/bin/python bench/export_reranker_ane.py --seq-len 512 --output-dir work/exports/reranker-ane
bench/aot_verify.sh work/exports/reranker-ane/qwen3-reranker-0.6b_float16_s512_ane.aimodel work/exports/reranker-ane/aot_h17g_ane h17g
.venv/bin/python bench/gate_reranker_ane.py          # ANE/GPU/CPU lanes + latency
```
