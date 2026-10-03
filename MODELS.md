# MODELS — every model this corpus touched: checkpoint, surgery, script, artifact, proof

Registry spine for the port lineage (the "how the models were tweaked" ledger).
One block per ported family; measurement-only comparators are tabled at the
bottom. Artifact hashes point at manifests (`shasum -a 256 -c` verifies whole
trees); nothing here stores bytes — the repo ships recipes, the volumes hold
downloads. Locations: `models/` and `work/` in the repo are symlinks to
`/Volumes/HUB/models/silicon-ledger-studio/` (relocated 2026-10-03); the mini's
originals live at `/Volumes/M4-Partage/local_ai_stack/` (pinned:
`/Volumes/HUB/archive/manifests/local-ai-stack-MANIFEST.sha256`, 2,742 files).

## Laya-English — ModernBERT-large 421M decision model

- source: `convaiinnovations/laya` (HF); weights at `models/laya-english/`
  (`model.safetensors` sha256 `891102d372688fc2a094dac56a384bc537b87c63f21f9f3dac0be2b7cbc8d86c`,
  mini manifest line) — author's repo cloned pre-EXP at `work/laya-repo/`
- surgery + why: fp16 everywhere (ANE cannot execute fp32 ops, `05-gotchas`
  F-25); 1×1-conv form for linears; RoPE cos/sin as precomputed buffers, not
  gathered in-graph (F-34 compiler segfault); final-pool padded ≥32 fp16 wide
  (alignment rule) — same template as Von below
- scripts: `bench/laya_ane_bench.py`, `bench/jevbench_ane.py` (verify),
  `bench/export_laya_ane.py` header covers the multilingual sibling
- artifact(s): Core AI `.aimodel` builds under `work/` (M4 era archive;
  re-bake: `python bench/laya_ane_bench.py --seq-len 256 --variant v1`)
- proof: EXP-016/EXP-018; JevBench v1.3.0 fidelity 230/231 vs author's
  reference; ranked comparison vs aac6fef published port (1.12× faster)
- ledger rows: `laya-en-*`, `laya-ane-*`, `laya-multi-*` (139 rows total incl.
  CPU/Core ML comparators)

## Laya-multilingual — mmBERT-base + typed decision head

- source: `convaiinnovations/laya-multilingual`; weights `models/laya-multilingual/`
- surgery: `torch.gather` marker-select → selection **matmul** against a
  host-built one-hot (ANE rejects data-dependent gather_nd, rank-3 rule);
  everything else reproduced faithfully from `NayaKishorM/laya`
  `DecisionModel.forward` (see `SOURCES.md`)
- scripts: `bench/export_laya_ane.py` (export), `bench/laya_ane_bench.py`
- artifact(s): s256 Core AI graph, 2 ANE regions verified (EXP-017)
- proof: EXP-017 residency + latency vs `aac6fef/laya-multilingual-coreml-ane`
- ledger rows: `laya-multilingual-*`, `laya-ane-*`

## Von-1.0 — ModernBERT-large 3-way NLI decision model

- source: `wfzyx/von`; author repo cloned at `work/von-repo/` (mini archive)
- surgery: re-author of the whole backbone for static trace — precomputed
  RoPE buffers (F-34), masked **mean** pooling, padded 32-wide head output;
  sliding/full attention alternation preserved (EXP-016)
- scripts: `bench/export_von_ane.py`, `bench/von_authored144.py`
- artifact(s): EXP-016 builds (M4-era); `aot_verify.sh` re-checks region counts
- proof: EXP-016 ANE residency; EXP-018 JevBench rows; oracle-gated per
  `09-origins` §3
- ledger rows: `von-*` (80)

## Granite-Embedding-97M — multilingual embedder (most-measured model here)

- source: `ibm-granite/granite-embedding-97m-multilingual-r2`; zoo bundle
  `granite97m_fp32_s128_bound.aimodel` (mini `models/`, plus `work/granite-embedding-97m/`)
- surgery ladder (EXP-005 — the fp16 series): v0 as-is fp32 → **0 ANE
  regions (silent GPU fallback)**; v1 +fp16 softmax; v2 +fp16 scale;
  v3 +fp16 pooling → **1 region, 4.00 ms, 83 mW GPU** vs 10,390 mW fp32-GPU;
  quantization series w8/w6/w4 +fp16; "ours" = own build of the multilingual r2
- scripts: `bench/export_granite_fp16_placement.py`,
  `bench/export_granite_w8_fp16.py`, `bench/granite_ane_variants.py`,
  `bench/build_fork_granite.py` (mini-era), `bench/interference_coreai.py`
- artifact(s): zoo bundle + v0–v3/w-series `.aimodel`s (mini archive, pinned);
  region counting via `bench/probe_ane_regions.py` (glob-double-count fixed, F-27)
- proof: EXP-005 (regions + power), EXP-021; every number in
  `results/EXP-005-ane-residency/README.md`
- ledger rows: `granite-*` (~280 across variants)

## MiniLM — all-MiniLM-L6-v2 (the Core ML baseline lineage)

- source: `sentence-transformers/all-MiniLM-L6-v2`
- surgery: Core ML conversion only (this predates the Core AI program); the
  famous surgery here was to the TOOLCHAIN, not the model — NumPy ≥2.4
  `int()` regression (F-01) fixed the silent conversion failure
- scripts: `bench/convert_encoder_coreml.py` (`models/minilm128.mlpackage`),
  `bench/bench_encoder.py`, `bench/power_ab.py`
- artifact(s): `minilm128.mlpackage` (mini `models/`, pinned in manifest)
- proof: EXP-003 (Core ML vs ANE power band)
- ledger rows: `minilm-*` (47)

## Qwen3-Reranker-0.6B — cross-encoder re-author (EXP-013)

- source: `Qwen/Qwen3-Reranker-0.6B`; weights `models/qwen3-reranker-hf/`
  (Studio/HUB home now; download: `hf download Qwen/Qwen3-Reranker-0.6B --local-dir models/qwen3-reranker-hf`)
- surgery: full re-author to a static ANE graph (the 0.500-score incident and
  the two-way-softmax-over-dead-logits diagnosis, F-32; RoPE fix via F-34
  bisection; every execution path gated across fresh processes)
- scripts: `bench/export_reranker_ane.py` (bake), `bench/gate_reranker_ane.py`
  (fidelity gate), `bench/correctness_head.py`
- artifact(s): `work/exports/reranker-ane/qwen3-reranker-0.6b_float16_s512_ane.aimodel`
  (`main.mlirb` sha256 `3bd166b6a4fcff89226787950e746c9a400c82d47aaf57ca0ed976005d29f422`;
  tree pinned: `work/MANIFEST.sha256`) + AOT bundles `aot_h17g_ane/`, `aot_recheck/`
- proof: EXP-013 — ANE residency (h17g, 1 region), GPU 4422 mW arm history,
  gate pass across repeated fresh processes; reranker 3× faster / 4–5× less
  power than the GPU baseline it replaced
- ledger rows: `reranker-*` / `m5max-*` comparators (~80)

## EmbeddingGemma-300m — small-embedder pilot (M5 era)

- source: `google/embeddinggemma-300m`
- surgery: fp16 export trial; driver lived harness-side (`ane-gemma-*` runs
  logged in mini archive `work/gemma_ane.log`) — in-tree port script is a GAP-2
  item (`results/FLEET.md` appendix)
- proof: `ane-gemma-*` rows (12) + EXP-001 lineage op coverage
- ledger rows: `ane-gemma-*`

## Apple Foundation Models — measured as shipped (no surgery)

- `com.apple.fm.language.instruct_3b.base` + safety/guard/tokenizer submodels;
  EXP-002 baseline, cold-vs-warm discipline (F-13), `bench/` probes drive `fm`
  API; nothing re-authored, so nothing to bake
- ledger rows: `apple-fm-*` / `fm-*` (15)

## Measurement-only comparators (never ported, never touched)

`aac6fef/laya-multilingual-coreml-ane` (published Core ML port, EXP-017
reference) · `llm-semantic-router/mmbert-embed-32k-2d-matryoshka` ·
`Qwen/Qwen3-Embedding-0.6B` · `nvidia/Nemotron-3-Embed-1B-BF16` ·
`intfloat/multilingual-e5-small` · bge-small/base · mpnet-base ·
Jev / OpenJev / OpenDecision (published scores) · the Apple M4/M5 ANE roofline
rows (instrument metadata, not models). Each appears in the ledger with its
`provenance` field naming the third party; none contributed ANE artifacts.

---
Regenerate discipline: add a block when a new family is ported; update `proof`
lines only by appending dated notes. `bench/import_bench_reports.py` remains
the intake path for machine rows. (P3 will pin per-artifact re-bake hashes for
Laya and Granite here; until then the manifests above are the authority.)
