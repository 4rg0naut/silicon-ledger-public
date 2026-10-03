# MODELS — every model this corpus touched: checkpoint, surgery, script, artifact, proof

Registry spine for the port lineage (the "how the models were tweaked" ledger).
One block per ported family; measurement-only comparators are tabled at the
bottom. Artifact hashes point at manifests (`shasum -a 256 -c` verifies whole
trees); nothing here stores bytes — the repo ships recipes, the volumes hold
downloads. Locations: `models/` and `work/` in the repo are symlinks to
`/Volumes/HUB/models/silicon-ledger-studio/` (relocated 2026-10-03); the mini's
originals live at `/Volumes/M4-Partage/local_ai_stack/` (pinned:
`/Volumes/HUB/archive/manifests/local-ai-stack-MANIFEST.sha256`, 2,742 files).

Checkpoint fields: `revision:` is the commit sha recorded at download time by the HF
cache (first line of `.cache/huggingface/download/*.metadata`; the second line is the
content sha256 and matches the pinned file hashes). `pin:` gives each cited script's
last-touch commit, verifiable with `git log -1 --format=%h --follow -- <path>`.
`revision: unrecorded` means a pre-ledger download left no cache on any pinned volume.

## Laya-English — ModernBERT-large 421M decision model

- source: `convaiinnovations/laya` (HF); weights at `models/laya-english/`
  (`model.safetensors` sha256 `891102d372688fc2a094dac56a384bc537b87c63f21f9f3dac0be2b7cbc8d86c`,
  mini manifest line) — author's repo cloned pre-EXP at `work/laya-repo/`
- revision: `1c5edc17a7acd8701df6fc341c0d179f1c62c982` (download cache:
  mini `models/laya-english/.cache/huggingface/download/model.safetensors.metadata`,
  inside local-ai-stack manifest)
- download: `hf download convaiinnovations/laya --revision 1c5edc17a7acd8701df6fc341c0d179f1c62c982 --local-dir models/laya-english`
- surgery + why: fp16 everywhere (ANE cannot execute fp32 ops, `05-gotchas`
  F-25); 1×1-conv form for linears; RoPE cos/sin as precomputed buffers, not
  gathered in-graph (F-34 compiler segfault); final-pool padded ≥32 fp16 wide
  (alignment rule) — same template as Von below
- scripts: `bench/laya_ane_bench.py`, `bench/jevbench_ane.py` (verify),
  `ports/export_laya_ane.py` header covers the multilingual sibling
  (pin: `ports/export_laya_ane.py` + `bench/laya_ane_bench.py` @ `9503b24`;
  `bench/jevbench_ane.py` @ `746912f`)
- artifact(s): Core AI `.aimodel` builds under `work/` (M4 era archive;
  re-bake: `python bench/laya_ane_bench.py --seq-len 256 --variant v1`)
- proof: EXP-016/EXP-018; JevBench v1.3.0 fidelity 230/231 vs author's
  reference; ranked comparison vs aac6fef published port (1.12× faster)
- ledger rows: `laya-en-*`, `laya-ane-*`, `laya-multi-*` (139 rows total incl.
  CPU/Core ML comparators)

## Laya-multilingual — mmBERT-base + typed decision head

- source: `convaiinnovations/laya-multilingual`; weights `models/laya-multilingual/`
- revision: `052592a15d198d9ad47da779604259b10b47b7aa` (download cache
  `models/laya-multilingual/.cache/huggingface/download/model.safetensors.metadata` —
  identical on mini and HUB copies; upstream `main` has since advanced to `1720e3e3…`,
  HF API 2026-10-03, so re-download must pin the revision)
- download: `hf download convaiinnovations/laya-multilingual --revision 052592a15d198d9ad47da779604259b10b47b7aa --local-dir models/laya-multilingual`
- surgery: `torch.gather` marker-select → selection **matmul** against a
  host-built one-hot (ANE rejects data-dependent gather_nd, rank-3 rule);
  everything else reproduced faithfully from `NayaKishorM/laya`
  `DecisionModel.forward` (see `SOURCES.md`)
- scripts: `ports/export_laya_ane.py` (export), `bench/laya_ane_bench.py`
  (pin: both @ `9503b24`)
- artifact(s): s256 Core AI graph, 2 ANE regions verified (EXP-017)
- proof: EXP-017 residency + latency vs `aac6fef/laya-multilingual-coreml-ane`
- notes:
  - 2026-10-03 P3 re-bake (Studio M5 Max, `.venv-conv` torch 2.14.1 +
    coreai-torch 0.4.2, clean dir): oracle gate PASS max|Δlogit| = 4.77e-06,
    bit-identical to the original mini run;
    `work/exports/laya-rebake-p3/laya-multilingual_v1_float16_s256_ane.aimodel/main.mlirb`
    sha256 `30cdf9aab27d54dba0c04517c5ded8494c98d42eeb61779ec23238f12b4eb828`
    vs mini original `d65f9aa6b64bad6f050807caf6fb536a80bb2195b2a42036de5341b480c1f6f6`
    (local-ai-stack manifest) — pinned explained delta: numerics identical,
    container bytes machine/torch-build-sensitive. Evidence: `REBAKE.log` beside artifact.
- ledger rows: `laya-multilingual-*`, `laya-ane-*`

## Von-1.0 — ModernBERT-large 3-way NLI decision model

- source: `wfzyx/von`; author repo cloned at `work/von-repo/` (mini archive)
- revision: `aa2fdc9630ecdadef32c56073553b3a69bed38bf` (download cache: mini
  `models/von-1.0/.cache/huggingface/download/model.safetensors.metadata`, inside
  local-ai-stack manifest)
- download: `hf download wfzyx/von --revision aa2fdc9630ecdadef32c56073553b3a69bed38bf --local-dir models/von-1.0`
- surgery: re-author of the whole backbone for static trace — precomputed
  RoPE buffers (F-34), masked **mean** pooling, padded 32-wide head output;
  sliding/full attention alternation preserved (EXP-016)
- scripts: `ports/export_von_ane.py`, `bench/von_authored144.py`
  (pin: `ports/export_von_ane.py` @ `9503b24`; `bench/von_authored144.py` @ `83e2645`;
  `bench/aot_verify.sh` @ `41df40e`)
- artifact(s): EXP-016 builds (M4-era); `aot_verify.sh` re-checks region counts
- proof: EXP-016 ANE residency; EXP-018 JevBench rows; oracle-gated per
  `09-origins` §3
- ledger rows: `von-*` (80)

## Granite-Embedding-97M — multilingual embedder (most-measured model here)

- source: `ibm-granite/granite-embedding-97m-multilingual-r2`; zoo bundle
  `granite97m_fp32_s128_bound.aimodel` (mini `models/`, plus `work/granite-embedding-97m/`)
- revision: `835ad14087e140460703cf0fae09f97d469d65c2` (download cache
  `work/granite-embedding-97m/source/.cache/huggingface/download/model.safetensors.metadata`)
- download: `hf download ibm-granite/granite-embedding-97m-multilingual-r2 --revision 835ad14087e140460703cf0fae09f97d469d65c2 --local-dir work/granite-embedding-97m/source`
- surgery ladder (EXP-005 — the fp16 series): v0 as-is fp32 → **0 ANE
  regions (silent GPU fallback)**; v1 +fp16 softmax; v2 +fp16 scale;
  v3 +fp16 pooling → **1 region, 4.00 ms, 83 mW GPU** vs 10,390 mW fp32-GPU;
  quantization series w8/w6/w4 +fp16; "ours" = own build of the multilingual r2
- scripts: `ports/export_granite_fp16_placement.py`,
  `ports/export_granite_w8_fp16.py`, `bench/granite_ane_variants.py`,
  `bench/build_fork_granite.py` (mini-era, not relocated — it was a harness-side
  driver and left no in-tree successor; the port lineage runs through the ports/
  exports above), `bench/interference_coreai.py`
  (pin: `ports/export_granite_fp16_placement.py` + `ports/export_granite_w8_fp16.py`
  @ `9503b24`; `bench/granite_ane_variants.py` @ `04ce0e8`;
  `bench/interference_coreai.py` @ `f5fc9ac`)
- artifact(s): zoo bundle + v0–v3/w-series `.aimodel`s (mini archive, pinned);
  region counting via `bench/probe_ane_regions.py` (glob-double-count fixed, F-27)
- proof: EXP-005 (regions + power), EXP-021; every number in
  `results/EXP-005-ane-residency/README.md`
- notes:
  - 2026-10-03 P3 re-bake (clean dir, `--out work/exports/granite-rebake-p3`):
    gold gate PASS min_cosine `0.9999907492331014`; export 195,081,877 B/3.9 s;
    AOT via `coreai-build --preferred-compute neural-engine` (resolved at
    runtime, cryptexd mount suffix is per-boot random — F-09) compiled 22
    specializations: h13 → 0 ANE regions, h14+ → 14 regions (MPSGraph
    delegate). `main.mlirb` sha256
    `df276e99b4129c44637426fb56a7743adbb8f5e4132b35063344e4e2faed8e73`;
    same-day pre-fix baseline `689696c15c89146975925f3e7066106f32f7dd6fb4f6e61a38f14810027042d2`
    (14-byte container delta, gate numerics identical). Honest gap: the pre-move
    original of this probe was never manifest-pinned (`work/MANIFEST.sha256`
    covers the reranker tree only); pinned from today forward. Evidence:
    `REBAKE.log` + `probe-record.json` beside artifact.
- ledger rows: `granite-*` (~280 across variants)

## MiniLM — all-MiniLM-L6-v2 (the Core ML baseline lineage)

- source: `sentence-transformers/all-MiniLM-L6-v2`
- revision: unrecorded (pre-ledger Core ML era, before cache pinning discipline;
  the artifact of record is the converted `minilm128.mlpackage`, mini-manifest-pinned)
- download: `hf download sentence-transformers/all-MiniLM-L6-v2 --local-dir models/all-MiniLM-L6-v2`
- surgery: Core ML conversion only (this predates the Core AI program); the
  famous surgery here was to the TOOLCHAIN, not the model — NumPy ≥2.4
  `int()` regression (F-01) fixed the silent conversion failure
- scripts: `ports/convert_encoder_coreml.py` (`models/minilm128.mlpackage`),
  `bench/bench_encoder.py`, `bench/power_ab.py`
  (pin: `ports/convert_encoder_coreml.py` @ `9503b24`; `bench/bench_encoder.py` @
  `c25b8cc`; `bench/power_ab.py` @ `68b8547`)
- artifact(s): `minilm128.mlpackage` (mini `models/`, pinned in manifest)
- proof: EXP-003 (Core ML vs ANE power band)
- ledger rows: `minilm-*` (47)

## Qwen3-Reranker-0.6B — cross-encoder re-author (EXP-013)

- source: `Qwen/Qwen3-Reranker-0.6B`; weights `models/qwen3-reranker-hf/`
  (Studio/HUB home now; download: `hf download Qwen/Qwen3-Reranker-0.6B --revision e61197ed45024b0ed8a2d74b80b4d909f1255473 --local-dir models/qwen3-reranker-hf`)
- revision: `e61197ed45024b0ed8a2d74b80b4d909f1255473` (download cache
  `models/qwen3-reranker-hf/.cache/huggingface/download/model.safetensors.metadata`;
  equals upstream `main` per HF API 2026-10-03)
- surgery: full re-author to a static ANE graph (the 0.500-score incident and
  the two-way-softmax-over-dead-logits diagnosis, F-32; RoPE fix via F-34
  bisection; every execution path gated across fresh processes)
- scripts: `ports/export_reranker_ane.py` (bake), `bench/gate_reranker_ane.py`
  (fidelity gate), `bench/correctness_head.py`
  (pin: `ports/export_reranker_ane.py` @ `9503b24`; `bench/gate_reranker_ane.py` @
  `41df40e`; `bench/correctness_head.py` @ `746912f`)
- artifact(s): `work/exports/reranker-ane/qwen3-reranker-0.6b_float16_s512_ane.aimodel`
  (`main.mlirb` sha256 `3bd166b6a4fcff89226787950e746c9a400c82d47aaf57ca0ed976005d29f422`;
  tree pinned: `work/MANIFEST.sha256`) + AOT bundles `aot_h17g_ane/`, `aot_recheck/`
- proof: EXP-013 — ANE residency (h17g, 1 region), GPU 4422 mW arm history,
  gate pass across repeated fresh processes; reranker 3× faster / 4–5× less
  power than the GPU baseline it replaced
- ledger rows: `reranker-*` / `m5max-*` comparators (~80)

## EmbeddingGemma-300m — small-embedder pilot (M5 era)

- source: `google/embeddinggemma-300m`
- revision: unrecorded (pilot ran harness-side on the mini; no HF cache in any pinned
  volume — the driver log `work/gemma_ane.log` is the artifact of record)
- download: `hf download google/embeddinggemma-300m --local-dir models/embeddinggemma-300m`
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
the intake path for machine rows. Per-artifact re-bake hashes for Laya and
Granite are pinned in the notes above (2026-10-03); the manifests remain the
authority for everything else.
