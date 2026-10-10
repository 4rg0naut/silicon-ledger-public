# SOURCES — what this corpus owes, and to whom

Mandated by `00-DESIGN.md` ("SOURCES.md — projects, posts, papers, licenses, access dates").

**The rule this corpus plays by:** everything above this line and in `bench/`,
`evaluation/`, `tools/` and `results/` is our own original work, MIT-licensed
(repo root `LICENSE`). Upstream material is **cited, never vendored, never
copied** — including the two projects whose licenses forbid redistribution
text. Access dates are the dates we actually read the sources.

## Prior-art projects (the landscape table in `01-landscape.md`)

All license statuses verified directly on 2026-09-23 (GitHub API `license`
field + raw `LICENSE` path), as recorded in LANDSCAPE-037 and neighbors.

| Project | License | How we use it |
|---|---|---|
| [maderix/ANE](https://github.com/maderix/ANE) | MIT | Cited extensively (QoS levels, private-API pipeline); the working example in `bench/ane-compile-test.m` follows its documented invocation. No source copied. |
| [johnmai-dev/ANE-LM](https://github.com/johnmai-dev/ANE-LM) | MIT | Cited |
| [AmiraniLabs/libane](https://github.com/AmiraniLabs/libane) | Apache-2.0 | Cited |
| [thebasedcapital/ane-infer](https://github.com/thebasedcapital/ane-infer) | **no license** | Cite-not-quote only; unlicensed text is not redistributed. Verified 2026-09-23 (raw LICENSE → 404). |
| [anemll/anemll](https://github.com/anemll/anemll) | **no license** | Cite-not-quote only; same verification. |
| [skyfallsin/ane.cpp](https://github.com/skyfallsin/ane.cpp) | MIT | Cited |
| [royisme/qwen-ane-llm](https://github.com/royisme/qwen-ane-llm) | MIT | Cited |
| [shershah1024/lfm2.5-vl-ane](https://github.com/shershah1024/lfm2.5-vl-ane) | MIT code + LFM Open License v1.0 model | Cited |
| [AtomGradient/hybird-batch-prefill-on-ane](https://github.com/AtomGradient/hybird-batch-prefill-on-ane) | MIT | Cited |
| [tinygrad `extra/accel/ane`](https://github.com/tinygrad/tinygrad) | MIT (tinygrad) | Cited (the `ANESpecialization` / ANECompiler reverse-engineering corpus) |

## Documentation and header sources

| Source | License | Use |
|---|---|---|
| [hollance/neural-engine](https://github.com/hollance/neural-engine) | MIT (docs) | Cited throughout `01-landscape.md`, `06-measurement.md` |
| [nst/iOS-Runtime-Headers](https://github.com/nst/iOS-Runtime-Headers) | BSD-2 | Cited for `_ANEClient` & friends class shapes |
| [mdaiter/ane](https://github.com/mdaiter/ane) | unverified | Consulted prior art — the entitlement findings behind the private-API route (cited at the end of `01-landscape.md`'s survey; not in §3's table). No text redistributed. |
| [Eileen Yoon — "ANE DMA" post](https://eiln.github.io/posts/ane-dma.html) | author retains rights | The measurement our `bench/ane-dma-test.m` was written to reproduce (its header names the post); method cited in `03-program-format-and-compile.md` and `05-gotchas.md`. Register-level M3 findings cited, not copied. |
| maderix.substack.com ANE series (Parts 1–5) | author retains rights | Cited (QoS ladder, MIL pipeline) |
| arXiv:2606.22283 (AppleNeuralEngine direct-drive reference paper) | arXiv license | Cited with arXiv id inline wherever its findings appear |
| [mechramc/Orion](https://github.com/mechramc/Orion) | MIT | `bench/ane-dma-test.m` follows its `core/mil_builder.m` generator **conventions** and `docs/ane_constraints.md` constraints — conventions, not code |

## M5 GPU-NA attribution sources (added 2026-10-05; feed `10-m5-attribution-signals.md`)

Access date 2026-10-05 for every row; licenses not re-verified today are marked
`unverified` rather than assumed (the honesty rule above).

| Source | License | Use |
|---|---|---|
| [arXiv:2606.12765 — Rigel](https://arxiv.org/abs/2606.12765) (M4 Max Metal 4.1 tensor path) | CC-BY-4.0 (arXiv page) | Checksum-gated harness method (adopted into EXP-024 protocol); M4 pre-NAX baseline facts (matmul2d on shader pipes, fp8 emulated) |
| [arXiv:2607.00501 — BaseRT](https://arxiv.org/abs/2607.00501) | arXiv license | Native-Metal runtime context; decode/prefill baselines |
| [arXiv:2607.19438 — BaseRT on M5 Neural Accelerators](https://arxiv.org/abs/2607.19438) | arXiv license | Independent confirmation NA routing moves prefill 3.9–6.4× (pJ/token delta expectation); "every core carries a dedicated Neural Accelerator" |
| [Apple ML Research — "Exploring LLMs with MLX and the Neural Accelerators in the M5 GPU"](https://machinelearning.apple.com/research/exploring-llms-mlx-m5) | © Apple | Primary: TensorOps+MPP drive the NA; TTFT 3.3–4.1× vs M4; decode stays bandwidth-bound; macOS 26.2 floor for MLX NAX |
| [Tungsten — "Metal 4 matmul2d on M5 Max"](https://tungsten-lang.org/articles/metal4-matmul2d-on-m5-max) | author retains rights | Root causes + fixes for the multi-tile silent-zeros we hit (MTL4Compiler pipeline, innermost-first extents, residency set, TG-memory length); M≥400 crossover envelope for true-NA load arms |
| [aditvenk/mpp-bad-examples](https://github.com/aditvenk/mpp-bad-examples) | unverified | Listed matmul2d bug reproducers (found via search; not yet opened — cited as pointer only) |
| [metalworking — Neural Accelerators / MTLTensor pages](https://metalworking.vercel.app/machine/neural-accelerators/) | unverified | NAX vocabulary; MLX `steel/gemm/nax.h` 16×16 fragments; MPP-via-library claim — cited, not copied |
| [antirez/ds4 issue #14](https://github.com/antirez/ds4/issues/14) | issue text © author | Points at Apple's MPP Programming Guide (2026-03-16): M5 GEMM prefers hardware-managed caching over TG staging |
| [metaspartan/mactop PR #75](https://github.com/metaspartan/mactop/pull/75) | unverified (repo) | Primary RE for macOS 27/M5 privilege behavior: AMC kernel-blocked (`32d86fd`), PMP0 naming + gated CPU counters (`53e5f90`), H11ANEIn binary fallback (`3ffd18e`), exclave ANE binary duty semantics (`b0fdcabe`), bin-label + lowest-floor decode (`pmp_names.h`), M6 F2 floor (#99) |
| [lablup/all-smi issue #415](https://github.com/lablup/all-smi/issues/415) | unverified (repo) | M5 Max 364-channel Energy Model fixture (Mac17,7/26A428): rails incl. ANE0/AFR0 exist; GPU Energy live at user level; element-timestamp mechanics |
| [Mference](https://github.com/tunecassio/mference) (local: `work/Mference`) | MIT (README badge) | MSL A/B selection rule context: decode on GEMV, prefill `matmul2d` with bounded dequant tiles (`docs/SYSTEM_DESIGN.md`) |
| [Anemll/ds4-ssd](https://github.com/Anemll/ds4-ssd) | MIT | Production NAX usage: "NAX, the Apple neural-accelerator backed `matmul2d` path used by Metal on M5-class hardware"; `ds4_profile.json` picks ANE only for chunk shapes measured faster than GPU/NAX; `--no-int8`/`--quality` disables NAX/ANE paths — a ready-made engine A/B switch for EXP-024 arms (`docs/PROFILES.md`, `docs/ANE_KERNELS.md`) |

## H17-truth research pass (added 2026-10-06; feeds `10-m5-attribution-signals.md` Q8/§33.3, `16-neural-accelerators.md`, C6–C8)

Access dates 2026-10-06. Raw fetch pins: `results/EXP-024-engine-attribution/raw/research-2026-10-06/`
(in-repo subset + `MANIFEST.sha256`); full captures on the Studio at
`/Volumes/data/OpenFox/dev_m5max_re/exp024-raw/research-2026-10-06/` (ane_paper.html
sha256 `441c63cf…`). Note: `*.github.io` is blocked from this network; Zakharko's report
was recovered through the GitHub contents API `?ref=gh-pages` — pin file `tza.html`.

| ID | Source | Claim scope | Privilege class of what it gives us | Matrix row it upgrades |
|---|---|---|---|---|
| PAPER-ANE-RE+ | [arXiv:2606.22283](https://arxiv.org/abs/2606.22283) §Ch1.3/Ch24/Ch33/Ch34.4 — full-text pass (prior row was abstract-scope) | Per-die NE-core sequence base=4 g=8 s=16 c=32 d=64 → **M5 Max h17c = 32 compiler-visible cores**; runtime string is coarse (`h1N`/`h1Ng`), fine letters are compiler-target ids; §33.3 whole-engine unentitled channel catalog (table in file 10); 24 named per-task `kANE_*` counters behind a stats-descriptor gate (`ANEProgramCreateArgs+0x6c`, create→1/load→0 on public compiles); M1 sustained 0.5 pJ/FLOP fp16 (0.37 optimized); dispatch floor ~0.9 W; 1 firmware command in flight | Paper documents what an *entitled* sampler reads; catalog itself is unentitled | Q8 core-count corrections; §33.3 probe list (B4); kANE gate recon (B5); C8 ceilings |
| TZAKHARKO-NA | [tzakharko/apple-neural-accelerators-benchmark](https://github.com/tzakharko/apple-neural-accelerators-benchmark) (report `index.html` @gh-pages = pin `tza.html`; kernels `Sources/…/tensor.swift`+`matmul.swift` = pins) | A19 measured: Matrix FP16 1024 FLOPS/core/cycle (~4× SIMD FP16 iso-clock), INT8 ~2048 OPS/core/c, optimal tile ≥32×32; NA "not directly exposed to developers" — timing-derived; runs on Xcode 26.1/26.x **unprivileged** | Confirms tensor-op path needs no entitlement, and our R8 no-op is a 27.0-beta GPUCompiler regression, not platform policy | C6 valid-tile harness design; C8 NA ceiling (with HAL-32 conservative denominator) |
| ANE-FORGE | [arXiv:2606.17090](https://arxiv.org/abs/2606.17090) + artifact repo `comp-physics/ANEForge` — **404 as of 2026-10-06 (watch)** | Tooling that walks the kANE_* counter path end-to-end (per PAPER-ANE-RE §33 references) | would give per-task dispatch telemetry at process granularity | FLEET watch thread D9a; B5 unblocks if repo lands |
| APPLE-MLX-M5 | Apple research post "Exploring LLMs with MLX and the Neural Accelerators in the M5 GPU" (re-fetched 2026-10-06, pin `apple_mlx.html`) | TTFT A/B methodology only (3.3–4.1× prefill deltas); no counters, no energy channels — checked for placement-dump telemetry: **nothing** | none new | Confirms GAP stands for Core AI placement dump (D9c) |

## Private-ANE-stack sources (added 2026-10-08; feeds K2/EXP-026 kitchen walls, ES/MX, and the API-121 ↔ Orion cross-link)

Access dates 2026-10-08 (fetched from this Studio; network OK direct). Raw fetch pins:
`results/EXP-027-nax/raw/research-2026-10-08/` (this slice re-pins `apple_mlx.html`,
`matmul.swift`, `tensor.swift` from `EXP-024 .../research-2026-10-06/` for self-containment;
manifest rides the EXP-027 pack manifest).

| ID | Source | Claim scope | Privilege class of what it gives us | Matrix row it upgrades |
|---|---|---|---|---|
| ESPRESSO-DIRECT | [<user>topherkarani/Espresso](https://github.com/<user>topherkarani/Espresso) (MIT; pin `espresso_README.md`, 173★/392 commits @2026-10-08) | Production direct-ANE serving: MIL text → `_ANEClient`/`_ANEInMemoryModel` dlopen bridge (same class as our K1 kitchen), fused multi-layer kernels, IOSurface zero-copy I/O, 519 tok/s 6-layer artifact on M3 Max (their `latest.json`, 3.41× vs CoreML `.cpuAndNeuralEngine` 152 tok/s), Qwen2.5-1.5B hybrid (Q/K/V+SwiGLU on ANE, RoPE/attn/LM-head CPU), per-SoC table claims "M4 38-core ANE"; **their "Espresso" is repo naming — they emit MIL text, NOT the `model.espresso.net` package format our API-122 killed — no contradiction with our dead-package finding** | user-mode dlopen of private APIs; App Store-incompatible (their disclaimer) — matches our unprivileged lane | Corroborates `_ANEClient` + IOSurface Path-B viability we measure in EXP-025/026; counter check: they publish no IOReport lens either |
| HOLLANCE-44 | [hollance/neural-engine issue #44](https://github.com/hollance/neural-engine/issues/44) (open 2026-03-16, filed by karani; pin `hollance44.json`) | Contributor-reported raw-MIL gotchas: `softmax` on non-power-of-2 dims → `InvalidMILProgram`; `slice_by_index` on function inputs + RMSNorm+convs → `InvalidMILProgram`; `reduce_mean` absent from raw MIL text (use `reduce_sum`+`mul`); lane-packed attention (spatial=32) needed for stable eval M1–M4; ANE eval unstable on some hosts even for identity kernels | community-reported (unreproduced here) — directly relevant to K2: our 7/7 `InvalidMILProgram` battery could be hitting gotcha #1/#3 rather than dialect-closure; differential re-run with softmax/reduce_mean-free chains is the cheap discriminator | EXP-026 K2 rejection taxonomy; B4/B5 op-support matrix caveats |
| ORION-PATCH-RELOAD | [arXiv:2603.06728 — Orion](https://arxiv.org/abs/2603.06728) (Kumaresan, 2026-03-06, CC-BY-4.0; pin `orion_arxiv_2603.06728.html`) | Weight-compile bypass by **unload → patch weight files → reload**: 4,200→494 ms/step (8.5×), 3.8× training speedup; 20-constraint ANE catalog (14 previously undocumented); IOSurface zero-copy tensor I/O; LoRA adapter-as-input hot-swap; GPT-2 124M 170+ tok/s (M4 Max); bypasses CoreML via `_ANEClient`/`_ANECompiler` | paper-reported on their private-API path; our side-evidence on this Studio (EXP-027 AN-STALE, measured): public CoreML reload after in-place weight-byte edit serves FRESH outputs (vector-equal to cold recompile, re-plan ~140 ms) — **API-121 stale-program hazard downgraded to bookkeeping-only on the public path; the private-ANE leg remains the authors' claim, our refutation does not extend to it — tension resolved, residual documented** | API-121 amendment (KB 02 §5); patch-reload viability for TOOL-10 weight-swap arms |
| MLX-2693 | [ml-explore/mlx issue #2693](https://github.com/ml-explore/mlx/issues/2693) (closed 2025-10-22; pins `mlx2693.json`, `mlx2693_comments.json`) | Maintainer (awni) on M5 Neural Accelerators in MLX: "work in progress", Metal 4 features evaluated case-by-case, and the vocabulary correction **"AMX != Neural Accelerators"** — the AMX talk linked in the OP is not the NAX path | official maintainer statement (no code claim) | Vocabulary guard for NAX attribution rows (file 16); FLEET D9 timeline context |

## Web-check batch 2026-10-08b (SearXNG via mini VM :8888 + direct fetches; feeds WX-1..WX-4, EXP-027 README xval section)

| ID | Source | Claim scope | Privilege class of what it gives us | Matrix row it upgrades |
|---|---|---|---|---|
| PAPER-ANE-RE+ EXT | arXiv:2606.22283 §9/§9.3/§34.1 full-text re-pass (pin `arxiv_2606.22283v1.pdf`, sha256 `aae78344…98292`, 302pp) | Table 9.1 M5/H17s rooflines: engine 10191 GF matmul / 18771 conv, ridge 424 FLOP/B; GPU 30862 GF / 229.7 GB/s / ridge 134; CPU 1898 / 130.4; §9.3 dispatch floor 0.23 ms; conv-stack efficiency 13× GPU on M5 (2289 vs 175 GF/W), 14.5× on M1; table 34.1 28 compiler targets, H17c=32 (labelled "A17 Max-class"; **our device evidence extends it to M5 Max**, EXP-027 xval-h17c-num-nes) | external-measured on M1+M5-base/H17s (not this Max) — cross-val only, conflicts declared in xval rows | xval-m5-* ledger rows; C8 ceiling comparison; kANE/`Perf_State` disambiguation |
| LLVM-MPS-RFC | [llvm discourse RFC: MPS dialect in MLIR](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102) (2024-02-20, Apple Compute Frameworks team; pin `llvm_mps_dialect_rfc_2024.md`) | Apple's own admission, pre-27: MPSGraph is an in-house MLIR dialect (222 ops, versioned, bytecode-serialised); `mpsgraphtool` ships macOS 14+ and converts coremlpackage→mpsgraphpackage "which is MLIR bytecode"; MPSGraph hands MLIR to "the neural engine compiler"; community framing "virtual ISA for the accelerator"; RFC NOT accepted upstream (dialect out-of-tree at Apple) | public statement of architecture we decode privately — attribution anchor for every "private mps dialect" claim (NOT first-public; ours = on-disk contents + placement metadata on 27) | KB 02 §3.13 attribution note; EXP-026 SU framing correction |
| WWDC26-330+MPP | [WWDC26 session 330 "Optimize custom machine learning operations with Metal tensors"](https://developer.apple.com/videos/play/wwdc2026/330/) (pins `wwdc2026_330_metal_tensors.html`) + [Metal Performance Primitives Programming Guide PDF](https://developer.apple.com/download/files/Metal-Performance-Primitives-Programming-Guide.pdf) (pin `mpp_programming_guide.pdf`, 6.1 MB, sha256 `8e930fa8…c92f`) | Officially documented matmul2d/tensor API surface on M5 (Apple9, MSL 4.0); tile-op semantics as Apple presents them; no energy numbers, no counter semantics, no multi-tile bug notes anywhere in either | public API docs — the lane exists in Apple's story; our measured behavior/energy/observability remains outside what they publish | NX-A/NX-C framing; R8 recipe cross-check vs MPP guide semantics |
| WWDC26-324+LAB8121+DOCS | [WWDC26 session 324 "Meet Core AI"](https://developer.apple.com/videos/play/wwdc2026/324/) (pin `wwdc2026_324_meet_core_ai.html`, transcript incl. Specialization chapter 15:34) + [WWDC26 "Coding Intelligence, Machine Learning & AI Group Lab" 8121](https://developer.apple.com/videos/play/wwdc2026/8121/) (pin `wwdc2026_8121_ciml_lab.html`) + docs trio: [specialization & caching](https://developer.apple.com/documentation/CoreAI/managing-model-specialization-and-caching) (pin `coreai_specialization_caching_docs.html`), [AOT compiling](https://developer.apple.com/documentation/CoreAI/compiling-core-ai-models-ahead-of-time) (pin `coreai_aot_compiling_docs.html`), [ComputeUnitKind](https://developer.apple.com/documentation/CoreAI/computeunitkind) (pin `coreai_computeunitkind_docs.html`) | Apple's own story for lane choice (CPU/GPU/ANE preference), specialization cache semantics, and the Instruments Core AI surface; lab 8121 answers match our measured cache-per-options behavior | marketing-level on lane internals: no cache-path scheme, no placement grammar, no privilege wall disclosure | E1/E2 cross-check — every mechanism we measured here is *absent* from the public docs (gap = our value); date+engine logged in results/EXP-028-apple-tracer/results/e2_xctrace_coreai.txt |
| METALHLO | [pedronahum/MetalHLO](https://github.com/pedronahum/MetalHLO) @commit `44b3a04be0095296f9be95ce060e93045b69c367` (2026-06-06; pins `metalhlo_README.md`, `metalhlo_nax_bundle_header.txt`, `metalhlo_codegenerator_nax_gating.txt`, `metalhlo_codegenerator_mpp_matmul_template.txt`) | Working third-party StableHLO→Metal compiler with THREE backends incl. heterogeneous GPU+ANE+CPU ("profitability-gated: ANE only for vocabulary-scale projections ≥10M output elements, N≥32K; GPT-2 124M logit projection 1.91×"); bundles MLX `gemm_nax` + generates multi-tile `matmul2d<desc, execution_simdgroups<8>>` kernels (128×128/8 simdgroups/256 threads; 64-tile/4-simdgroup variant for low-occupancy shapes; **dextents/slice are (cols,rows) inner-stride-first**; buffers-only, no MTLTensor host API; MSL 4.0 + Apple9); MPP path measured by them at 0.91× MLX on GEMM 4096², ResNet18 8.7× vs JAX-CPU — multi-tile matmul2d WORKS in the wild ⇒ our R8 no-op is harness/compiler-route-specific, not a silicon gate | open-source (Apache-2.0) code + their measurements on M5 Pro/M1 — write-side reference, not our measurement | R8 recipe candidate for the rerun (EXP-027 README); scheduler-heuristic comparison vs our placement-plan finds |
| MPSGRAPHTOOL-SYSTEM | `/usr/bin/mpsgraphtool` (macOS 27.0.1, measured here 2026-10-08) | `convert -coremlpackage … -specializeForDevice` emits `original_model_N.mpsgraph` + `specialized_model_N.mpsgraph` — same naming as the closed coreai-cache scheme — carrying placement dialect (`placement/gpu/region_call/stitched`), device stamps `mps.aneArch h17c` (public tool resolving OUR target), `mps.deviceGPUCoreCount`, and the ANE dtype whitelist string byte-equal to our cache extraction | public system tool, unprivileged — turns our read-only cache decoding into a WRITE-side experimental lane (inject hand-made graphs, watch placement) | p27_mpsgraphtool_write_side.txt; EXP-026 SU corroboration; B-lane placement interrogation |

## Novelty check 2026-10-10 (targeted web search + source reads; feeds API-138, API-140, EXP-026/027)

Prompted by a novelty review of this session's findings. Web/`find` only — no GitHub code
search API here, so absence of a hit is a *strong* negative, not a proof. Access date
2026-10-10. Records: `LANDSCAPE-072..075`.

| ID | Source | What it establishes | Verdict it forces |
|---|---|---|---|
| AI00AI-COREAI | [ai00ai/Apple-coreai-model-zoo-local `knowledge/aot-and-specialization.md`](https://github.com/ai00ai/Apple-coreai-model-zoo-local/blob/main/knowledge/aot-and-specialization.md) | Arch names track the **device identifier**, not marketing: only the matching `.aimodelc` loads (M4 Max = **h16c**, iPhone 17 Pro = **h18p**); `coreai-build compile` exits 0 for **any** arch — only a device load validates | Our AOT-gate result **re-derives a published rule**. Novelty narrows to the observed parts (M5 Max `h17c`, M4 mini `h16g`) + the private-selector divergence — not the rule |
| ANEPERF | [tmc/aneperf](https://github.com/tmc/aneperf) (`classify.go`, `ioreport.go`) | Reads `ANEXL`/`ANE UP`/`ANE0` via a name-substring filter (any channel containing "ANE"); groups `SOC-NI Util BW` as bandwidth; derives `ane_utilization_pct` from the Fast-Die CE histogram | The ANEXL **channel is public**. No exclusivity claim anywhere → our **calibrated exclusivity** is the new part |
| SILICONSCOPE | [kennss/SiliconScope `docs/ioreport-channels.md`](https://github.com/kennss/SiliconScope/blob/main/docs/ioreport-channels.md) | Verified sudoless IOReport map (M1..M5 Max): Energy Model ANE power, PMP0 DCS/AF BW — **never names** `SOC-NI9 ANEXL U`/`SOC-NI8 ANE UP` nor claims ANE lane exclusivity | ANE power monitoring is public; an ANE **activity counter** is not |
| STATS-2897 | [exelban/stats issue #2897](https://github.com/exelban/stats/issues/2897) (2026-01-04 → 2026-09-05) | Community position: macOS exposes **no usable ANE utilization**; mactop's "ANE%" is a watts/8.0 heuristic; Stats' own ANE-utilization attempt did not track ANE correctly | Strengthens the **ANEXL exclusivity** result as a genuinely new capability |
| COREAI-ZOO-PR36 | [john-rocky/coreai-model-zoo PR #36](https://github.com/john-rocky/coreai-model-zoo/pull/36) (our own, **merged** 2026-10-02) | States the M4 mini resolves to **h16g, not h16c (M4 Max)**, and that `coreai-build inspect` prints "This device's architecture" | The **M4 half** of our cross-chip finding is our own prior art — not new (see LANDSCAPE-076) |
| LLVM-MPS-RFC | (already, §Web-check 2026-10-08b) | `mpsgraphtool` produces MLIR bytecode; the `mps` dialect is Apple's, out-of-tree | The **format** is public (LANDSCAPE-077); no parser/dialect published → our MLIR recovery technique is new |
| ANE-GUIDE ch34 | (already, PAPER-ANE-RE+) | Predicted arch table | Our corrections stand (see issue link in `contrib/`) |

Per-claim verdict (this session):

| Claim | Verdict |
|---|---|
| M5 Max compiler target `h17c` / M4 mini `h16g`; private selector divergence | **Extension** — the rule is public (AI00AI-COREAI) and the **M4 half is our own merged PR #36** (LANDSCAPE-076); new: the M5 Max `h17c` target + the private-selector divergence (independently confirmed by a second reviewer, 2026-10-10) |
| Core AI cache layout + `modelHash`/`optsHash` key derivation | **Likely new** — no public decode found |
| Cached `mpsgraph` bytecode printed as readable MLIR | **Extension** — "MPSGraph is MLIR bytecode" is public (LLVM RFC / `mpsgraphtool`, LANDSCAPE-077) and the file names are public (AI00AI-COREAI); **new**: the private `aicode`/`placement` dialects and the stub-plugin + rewrite printing technique |
| `SOC-NI9 ANEXL U` lane-exclusive, calibrated ANE signal | **New as a discriminator** — channel known (ANEPERF); exclusivity/calibration new |
| `ANE-DCS-BW` floor is *not* ANE-specific | **Likely new** (negative result) — monitors lump DCS Floor into ANE-ish sampling |

## Tooling our bench imports (adapted where a row says so — nothing vendored)



> The `bench/…` paths below are the driver names as recorded at capture time. If a
> name is no longer under `bench/`, it is either a mini harness-era driver that was
> never in this repo's history (archive-only: `bench_coreai.py`, `run_bench004.py`,
> `run_bench003_005.py`, `coreai_bench002.py`, `build_fork_granite.py`,
> `llama_real_bench.py`, `ane_real.py`) or a relocated port (`convert_encoder_coreml.py`
> → `ports/`, P3 split) — verify any name with `git log --all -- "*<name>"`.

| Tool | License | Where |
|---|---|---|
| `coremltools` 9 | BSD-3-Clause (Apple) | `bench/bench_coreai.py`, `bench/run_bench004.py` |
| `coreai_torch` TorchConverter | upstream (see tool repo) | `bench/coreai_bench002.py` — header cites it (archive-only driver name, no in-tree copy) |
| `torch`, `transformers` | BSD-3 / Apache-2.0 | `bench/llama_real_bench.py` (via JevBench's tooling) |
| `safetensors` | Apache-2.0 | `bench/run_bench003_005.py` |
| JevBench | upstream (author's harness) | `bench/llama_real_bench.py` — header: "uses JevBench's tooling (imported)" |
| `coreai-model-zoo` (Apple; no public URL pinned in this corpus — referenced via the local checkout as `coreai-model-zoo/knowledge/coreai-overview.md`) | license unverified | Cited in `01-landscape.md` and EXP-005 (Core AI pipeline stages, silent-fallback definition); **code adapted**: `ports/export_von_ane.py` is adapted from the zoo's `conversion/granite_embedding/_granite_model.py` — derivative, not vendored text; verify the zoo's license before redistributing that file |
| [aac6fef/laya-multilingual-coreml-ane](https://github.com/aac6fef/laya-multilingual-coreml-ane) | unverified | EXP-017 reproduction target; the port and its published latencies are cited and attributed, no text redistributed (`results/EXP-017-laya-ane/README.md`, `ports/export_laya_ane.py` header) |
| [NayaKishorM/laya](https://github.com/NayaKishorM/laya) | unverified | `ports/export_laya_ane.py` reproduces `laya/common.py::DecisionModel.forward` **semantics** faithfully (one ANE-legal substitution: `torch.gather` → selection matmul) — graph behaviour, not code text |

## Model weights referenced (measured, never redistributed)

Weights are downloaded from Hugging Face at run time by the probes that need
them; only *our measurements* are in this corpus. Verify each model's own
license before pulling weights.

- IBM `granite-embedding-97m` (Apache-2.0) — most-measured model in the corpus
  (EXP-005/021; in-tree: `ports/export_granite_fp16_placement.py`,
  `ports/export_granite_w8_fp16.py`, `bench/granite_ane_variants.py`;
  `bench/coreai_bench002.py` / `bench/build_fork_granite.py` are mini harness-era
  driver names with no in-tree copy — archive-only references).
- Qwen family: `Qwen3-0.6B` / `1.7B` / `8B`, `Qwen3.5-0.8B/2B/4B`
  (Apache-2.0) — `bench/llama_real_bench.py`, container evals (EXP-023).
- `gpt-oss-20b` (Apache-2.0) — container evals (EXP-023).
- Liquid AI LFM2 / LFM2.5-350M (LFM Open License v1.0) — `bench/ane_real.py`.

## Upstream SDK

- [openclaims-ai/openclaims](https://github.com/openclaims-ai/openclaims) —
  the `openclaims` Python SDK that validates `knowledge/ane/openclaims/`.
  Not vendored; installed from git in a venv. As of 2026-10 the upstream
  repo carries no LICENSE file (noted in the spine doc's fine print).

## Apple frameworks

`AppleNeuralEngine.framework`, `CoreML.framework`, `Metal`, `CoreTime` —
Apple's, closed source, private APIs used at runtime via `dlopen`. No Apple
source or headers redistributed here; our C/ObjC files are original bindings.
