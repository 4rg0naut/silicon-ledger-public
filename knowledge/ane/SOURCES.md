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

## Tooling our bench imports (adapted where a row says so — nothing vendored)

| Tool | License | Where |
|---|---|---|
| `coremltools` 9 | BSD-3-Clause (Apple) | `bench/bench_coreai.py`, `bench/run_bench004.py` |
| `coreai_torch` TorchConverter | upstream (see tool repo) | `bench/coreai_bench002.py` — header cites it |
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
  (`bench/coreai_bench002.py`, `bench/build_fork_granite.py`, EXP-005/021).
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
