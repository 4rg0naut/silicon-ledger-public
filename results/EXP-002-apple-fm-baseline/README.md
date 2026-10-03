# EXP-002 — Apple Foundation Models baseline (`fm`)

**Question:** what does Apple's on-device model actually cost per call, what is
inside it, and does it use the Neural Engine?

**Method:** `xctrace` with the **Foundation Models** template (launched process),
then the **Core AI** template (attached to a resident `fm serve`) for ANE
activity. Cold vs warm vs resident-server latency measured separately.

```bash
# cold, traced
xcrun xctrace record --template 'Foundation Models' --no-prompt --time-limit 15s \
  --output fm2.trace --launch -- /usr/bin/fm respond 'Reply with exactly one word: pong'
# warm, attached to the resident server
xcrun xctrace record --attach <pid> --template 'Foundation Models' --no-prompt \
  --time-limit 25s --output fm_warm.trace
```

**Run:** 2026-09-20 · macOS 27.0 · Xcode 27.0

## What the model actually is (from `ModelLoadingTable`)
```
com.apple.fm.language.instruct_3b.base?variant=generic_sparse      <- the LLM (3B)
com.apple.fm.language.instruct_3b.fm_api_generic_3b?variant=...    <- API adapter
com.apple.fm.language.instruct_3b.fm_api_generic.draft
com.apple.fm.language.instruct_300m.safety                         <- input guardrail
com.apple.fm.language.instruct_300m.mm_guard                       <- multimodal guard
com.apple.fm.language.instruct_300m.image_tokenizer
com.apple.gm.safety_deny.input/output.foundation_models_framework.api
com.apple.safety.output.configuration
```
A 3B model wrapped in a **safety stack** (input, multimodal, output) plus a
separate 300M image tokenizer.

## Numbers

**Cold turn** (`fm respond`, first call in a cold window) — end-to-end **1.08 s**
| Stage | Duration |
| --- | --- |
| Actual inference (`ModelInferenceTable`) | **130.16 ms** |
| Load `instruct_3b.fm_api_generic_3b` | 372.80 ms |
| Input safety load | 154.19 ms |
| `mm_guard` load | 127.57 ms |
| Image tokenizer + output safety loads | 43.86 + 12.60 ms |
| Tokens | 62 in → **3 generated** |

**Latency by invocation style**
| Style | Latency |
| --- | --- |
| Cold one-shot `fm respond` | 1.29 s |
| Warm one-shot `fm respond` (new process) | **0.24 s** |
| Resident `fm serve` (HTTP) | 0.26–0.33 s |
| Warm traced per-request inference | 133–190 ms; asset loads collapse 320 ms → **21 ms** |

**ANE activity** (cold turn, `ane-hw-intervals`): **20 intervals, ≈184 ms**,
several labelled *Neural Engine Prediction*.

## Conclusions
1. **The Neural Engine is used** by Apple's on-device model — measured, not assumed.
2. **The load "tax" is cold-start only.** The OS caches model assets across
   processes, so a resident server is *no faster* than repeated one-shot calls
   (0.26–0.33 s vs 0.24 s). My earlier "2.4× tax" framing was a cold-window artifact.
3. The remaining per-request cost (~150 ms) is the model's own inference plus the
   guardrail passes.

## Unknowns
- The **guardrails' share of the warm ~150 ms is not isolated** — the instrument
  does not attribute per asset cleanly. Would need a warm trace with per-asset
  timing, or comparison against a non-Foundation-Models runtime.

## Artifacts
- `fm2.trace` — cold, launched process (Foundation Models template)
- `fm_warm.trace` — attached to resident `fm serve`, 3 warm requests
- `fm_warm.log` — record log for the attached run

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
|---|---|---|---|---|---|---|---|---|---|---|
| cold-turn-e2e | com.apple.fm.language.instruct_3b.base (fm respond) | — | — | — | end-to-end latency | 1.08 | s (cold turn, end-to-end) | — | per cold fm respond call (end-to-end, incl. cold asset loads) | ours |
| cold-inference | com.apple.fm.language.instruct_3b.base | — | — | — | inference duration (ModelInferenceTable) | 130.16 | ms | 130.16 | per inference (one generation pass, cold process, ModelInferenceTable) | ours |
| load-fm-api-generic-3b | com.apple.fm.language.instruct_3b.fm_api_generic_3b | — | — | — | asset load duration | 372.8 | ms | 372.8 | per cold load (one asset load) | ours |
| load-input-safety | input safety (com.apple.fm.language.instruct_300m.safety) | — | — | — | asset load duration | 154.19 | ms | 154.19 | per cold load (one asset load) | ours |
| load-mm-guard | mm_guard (com.apple.fm.language.instruct_300m.mm_guard) | — | — | — | asset load duration | 127.57 | ms | 127.57 | per cold load (one asset load) | ours |
| load-image-tokenizer | image tokenizer (com.apple.fm.language.instruct_300m.image_tokenizer) | — | — | — | asset load duration | 43.86 | ms | 43.86 | per cold load (one asset load) | ours |
| load-output-safety | output safety (com.apple.safety.output.configuration) | — | — | — | asset load duration | 12.6 | ms | 12.6 | per cold load (one asset load) | ours |
| tokens-input | com.apple.fm.language.instruct_3b.base | — | — | — | input tokens | 62 | tokens (input) | — | — | ours |
| tokens-generated | com.apple.fm.language.instruct_3b.base | — | — | — | generated tokens | 3 | tokens (generated) | — | — | ours |
| style-cold-oneshot | com.apple.fm.language.instruct_3b.base (fm respond) | — | — | — | latency by invocation style | 1.29 | s (cold one-shot fm respond) | — | per fm respond call (cold one-shot) | ours |
| style-warm-traced-inference | com.apple.fm.language.instruct_3b.base | — | — | — | warm traced per-request inference | 133 | ms (stated range 133-190 ms) | 133 | per warm traced request inference | ours |
| warm-asset-loads-cold | fm asset loads (warm trace baseline) | — | — | — | asset load duration | 320 | ms (asset loads, cold baseline of collapse) | 320 | per asset load (cold baseline) | ours |
| warm-asset-loads-warm | fm asset loads (warm trace) | — | — | — | asset load duration | 21 | ms (asset loads after collapse 320 ms -> 21 ms) | 21 | per asset load (warm, after collapse) | ours |
| ane-intervals | com.apple.fm.language.instruct_3b.base (cold turn) | ANE | — | — | ANE hardware intervals | 20 | intervals (ane-hw-intervals) | — | — | ours |
| ane-duration | com.apple.fm.language.instruct_3b.base (cold turn) | ANE | — | — | ANE activity duration | 184 | ms (approx, ane-hw-intervals) | 184 | per cold turn (total ANE hardware activity) | ours |
