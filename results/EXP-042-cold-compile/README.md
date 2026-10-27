# EXP-042 — ANE compile-time ladder (cold vs warm), private in-memory path

## Question
How does ANECCompile wall-time scale with graph size on h16g/h17g at 27.0.1, and does the
compiler cache (keyed by MIL-text hash — the mechanism EXP-041 exposed with its Code=10 aliasing)
save anything on repeat compiles, in-process or across process launches? This is the input a
serving stack needs for precompile-vs-compile-at-boot decisions.

## Method
`harness/compile_ladder.m`: N-conv chains (N in 1..32, C=1024, shared blob per EXP-043 form),
weight filename carries a nonce so MIL text is (a) unique per cold compile or (b) byte-identical
across repeats/runs (argv nonce) for the warm probe. `compileWithQoS` timed with
CLOCK_MONOTONIC_RAW; compile stage only (no eval loops). Captures: raw/ladder-studio-*.txt,
raw/xproc-studio-*.txt, raw/ladder-mini-*.txt.
Window: Studio LOADED (oMLX production up — QUIET-KEY stamped in each capture; timing on this path
is compiler-side and load-tolerant for our purposes, outliers declared below); mini loadavg ~1.3
(no oMLX on mini, not idle).

## Results
Cold compile wall-time, median of 3:

| nconv | h17g Studio | h16g mini |
|---|---|---|
| 1 | 14.8 ms | 29.9 ms (first-launch 44 ms) |
| 4 | 18.4 ms | 24.3 ms |
| 8 | 24.4 ms | 31.3 ms |
| 16 | 37.5 ms | 45.6 ms |
| 32 | 66.9 ms | 78.6 ms |

1. Scaling is ~linear in conv count above N≈4: ~1.6 ms/conv Studio, ~1.8 ms/conv mini, plus a
   ~13–15 ms fixed path. A 32-conv program cold-compiles in under 80 ms on both chips.
2. **No observable compile cache on this path.** Warm (same MIL text, same process) ratios are
   1.0x (noise both ways); cross-process warm (identical nonce across launches, run2) shows no
   speedup either: Studio run2 medians ≈ run1 (65.8 → 74.7 ms at N=32). ANECCompile recompiles on
   the in-memory descriptor path every time. The MIL-hash keying visible in EXP-041 governs
   bundle/blob VALIDATION caching, not a compile-result reuse that helps here.
3. mini only: sporadic 600 ms–1.3 s compile outliers (both cold and warm) under a loaded mini
   (loadavg 1.3–1.5) — daemon-side scheduling jitter, not graph-size-related. Serving stacks on
   shared Macs need compile timeouts, not just fast-path tuning.
4. Cross-check against EXP-043: a graph that will be REFUSED can still burn ~2.5 s (Studio,
   >4 GiB blob) to ~23 s (mini) before the rejection surfaces — failure validation is on the
   expensive path.
5. The 300 s plan-limit question (the number floating around the Qwen3-Embedding-0.6B discussion,
   EXP-015): our graphs are NOT Qwen3 — they are synthetic conv chains, ~2 orders smaller than a
   0.6B transformer graph. Verdict we can honestly state per machine: on the in-memory private
   path, both machines cold-compile everything we threw at them (≤32 conv, ≤3.8 GiB weights) in
   under 80 ms, and the only multi-second compile observed was a refusal-validation path (23 s,
   mini). Nothing we measured contradicts a 300 s budget; we cannot confirm Qwen3-scale timings
   from this — that needs the real model exported through the same path.

## Scope caveat
Private `_ANEInMemoryModel` path only, single-threaded, QoS 0x19, no aneserver CoreML-pipeline
caching (that layer has its own bundle cache; not measured here). Conclusions apply to
in-memory descriptor compiles, which is what harnesses like this one and the maderix-style
builders use.
