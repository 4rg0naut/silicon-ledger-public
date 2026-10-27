# EXP-040 — sidekick "M4 Max fp16 zero-collapse": does the M4 base collapse? No — and cross-chip outputs are bit-identical

## Question
sidekick reports fp16 ANE outputs collapsing toward zero on an M4 Max for their stack. Our fleet's
M4 base (`Mac16,10`, h16g) is the closest part we own. Does the same failure class appear here,
on the surface where we can actually gate numerics (Core AI `.aimodel` + granite-runner, ANE-preferred)?

## Method
One bundle (`granite97m_fp16_s128.aimodel`, EXP-005 fp16 v3 line), one tokenizer dir, one golden
fixture set (35 texts, S=128), copied Studio→mini; the same prebuilt `granite-runner` binary
(macOS 27.0.1/26A434 both boxes); `--compute neuralEngine --dump-embeddings` on both machines.
Raw: raw/studio-run.log, raw/mini-run.log (window QUIET-KEY + uptime + gate lines + sha256),
raw/mini-cpu-gpu-gates.txt (cpu/gpu gate lines; gate re-run 2026-10-27, dumps bit-identical,
warm p50 drift ≤8%), raw/emb-studio.json, raw/emb-mini.json.

## Results
1. **No zero-collapse on M4 base, on any compute surface.** Per-surface table (mini, same bundle/
   fixture; raw emb-{mini,cpu,gpu}.json + gate lines in raw/mini-run.log (neuralEngine) and
   raw/mini-cpu-gpu-gates.txt (cpu/gpu)):

   | surface (runner --compute) | gate | zeros | min abs | max abs | warm p50 |
   |---|---|---|---|---|---|
   | neuralEngine | 35/35 PASS, min cos 0.999957561 | 0/13,440 | 8.43e-06 | 0.7427 | 12.39 ms |
   | cpu | 35/35 PASS, min cos 0.999963701 | 0/13,440 | 4.43e-06 | 0.7414 | 4.96 ms |
   | gpu (runner `--compute gpu` → cpuAndGPU device set) | 35/35 PASS, min cos 0.999993980 | 0/13,440 | 7.73e-07 | 0.7417 | 7.39 ms |

   (Substitutions declared: per-COMPUTE table stands in for per-depth — one real model at three
   enforced placements, not depth-synthesized; the oracle is the repo golden fixture (torch-side,
   S=128) plus the fp64 recompute in 1b below, fp64-oracle gap closed there; verdict class:
   not-reproduced-at-our-shapes.)
1a. **Placement verified on the mini by power-rail counters (EXP-004 method, unprivileged
   variant).** `raw/em-placement.json` (enginemon 200 ms intervals, mini, wrapped cpu-vs-ANE runs):
   idle window GPU 848 mJ / ANE 0; **cpu arm: GPU 1779 mJ, ANE NRT 0 B, ANE DCS 0 B**; **ANE arm:
   ANE NRT AF RD 11.3 GB, ANE DCS RD 8.35 GB** rail reads while GPU energy falls back toward
   idle. The `--compute` requests correspond to real lane placement on Mac16,10.
   Instrument note for the fleet: the mini exposes the ANE rails under `AMC Stats / Perf Counters`
   (`ANE NRT AF RD`, `ANE DCS RD`), NOT the M5 Max `PMP0/SOC Floor ANE-LNK` group — enginemon
   reads whatever the platform publishes; cross-chip lane comparisons must use per-platform
   channel names, not one hardcoded group (registered convention).
   Side observation echoing EXP-005: at S=128 CPU is the fastest surface for this graph (4.96 ms
   vs ANE 12.39 ms on the mini) — ANE residency here is about residency, not latency.
1b. **fp64 oracle (closes the oracle gap).** `harness/fp64_oracle.py` (uv env, zoo torch graph in
   float64; declared deviation: fp64 padding sentinel clamped to -1e30 because
   `torch.finfo(float64).min` overflows when global+local masks stack to -inf — masking-equivalent
   at score scale, fp32 control identical at printed precision). `raw/fp64-oracle.json`:
   min cos vs fp64 — ANE(m5max) **0.999957437**, ANE(m4) **0.999957437** (identical: same dumps,
   sha256-equal), cpu(m4) 0.999963822, gpu(m4) 0.999994012; max abs err 1.46e-03 / 1.46e-03 /
   2.14e-03 / 8.06e-04. All four surfaces sit at fp16-rounding distance from fp64 truth —
   no collapse, no anomalous error on any of them, ANE and CPU error magnitudes on par.
2. **Cross-chip bit-identity (the bigger result).** The full embedding dumps from h17c (Studio) and
   h16g (mini) are **sha256-identical**
   (`1592dd00…120a`, reproduced in two independent run pairs, raw/*-run.log). Same OS build, same
   bundle, ANE-preferred compute: the two ANE generations produce byte-for-byte identical fp16
   results on this graph. Cross-silicon determinism is real here — so any "chip X collapses
   outputs" report is a SOFTWARE/surface story, not silicon nondeterminism.
3. Timing (stamped, not comparable): warm p50 Studio 9.98 ms vs mini 12.39 ms on this run; mini
   load 203 ms vs Studio ~200 ms on this repeated load path.

## Scope discipline (GOTCHAS-024 style)
- This is the Core AI ANE path for one embedding graph. sidekick's report is from a different
  stack (their own dispatch, token-count regime, possibly MPSGraph delegation paths). We can only
  say: the collapse does not reproduce on M4 base at this surface, and the surfaces we share
  (ANE fp16 arithmetic on conv/matmul-shaped work, 27.0.1) are cross-chip deterministic.
- No M4 Max in fleet; nothing here adjudicates the M4 Max report directly (cited, not measured).

## Feeds
sidekick #104 draft: the cross-chip bit-identity row is the strongest single fact we can offer —
it reframes per-chip "output quality" debates as software-surface questions.
