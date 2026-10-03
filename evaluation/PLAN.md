# Evaluation plan — choosing the local engine for each job

**The point.** The knowledge/memory layer is the foundation everything else sits on. It is not one
task, it is several, and each wants a different engine. The community has already shipped candidate
tools for most of them. **Our job is to test them against our own data and pick a winner per layer —
before optimising anything for the Neural Engine.** Porting the wrong model to the ANE is wasted work.

---

## The layers

| # | job | input → output |
| --- | --- | --- |
| 1 | **parse** | PDF / paper → clean text |
| 2 | **extract** | text → candidate claims with positions |
| 3 | **label** | claim → kind, confidence, topics |
| 4 | **verify** | claim + source passage → supported / partly / not |
| 5 | **reconcile** | two claims → contradictory or not |
| 6 | **retrieve** | query → the right chunks |

## Candidates, per layer

From the recent sweep. Licence and size matter as much as quality, because we intend to publish.

### 1 · parse
`docling.rs` (2026 Rust port; 4.3× faster, 2.3–2.6× less RAM, native binary) · our existing
**MinerU2.5-Pro** port (1.2B, Apache-2.0) · **LightOnOCR-2-1B** (Apache-2.0, 83.2 OlmOCR-Bench) ·
**Chandra OCR 2** (4B, OpenRAIL-M) · our **OvisOCR2** port (0.8B, best in the zoo at 96.58 OmniDocBench)

### 2 · extract
**GLiNER2.5** (Aug 2026, Apache-2.0, 74M/194M/287M, entities **and** relations with confidence,
MPS-native) · **NuExtract3** (4B, Apache-2.0, JSON template → JSON, official MLX quants) ·
**GLiNER-Relex** (Apache-2.0, emits head-relation-tail triples) · **Outlines** (now has an MLX
backend for schema-constrained decoding)

### 3 · label
**Kev** (Apache-2.0, Qwen3.5 0.8B/4B/9B, official MLX) · **SemIf / OpenJev** (#2 open on JevBench) ·
**our own trained decision model** (ModernBERT-base + pointer head, ANE-ready) · **GLiNER2.5
classifier** mode

### 4 · verify
**LettuceDetect v2** (mmBERT-base, Apache-2.0) · **TinyLettuce** (Ettin 17M/32M/68M, MIT, CPU
realtime) · **ModernCE-large-nli** (MIT, ModernBERT, 8k ctx) · **our Von-1.0** (3-way NLI,
ModernBERT-large, already on the ANE) · **Granite Guardian 4.1-8B** (Apache-2.0)

### 5 · reconcile
**contradictionchecker** (Apache-2.0, with published precision numbers)

### 6 · retrieve
**Granite-Embedding-97M** (ours, in production on the ANE) · **Qwen3-Embedding-0.6B** (cached here) ·
**ColModernVBERT** · **Nemotron-3-Embed-1B** · rerankers: Qwen3-Reranker-0.6B, nemotron-rerank-1b-v2

---

## The gates — checked before quality

A candidate that fails a gate is not measured, it is rejected. Cheap decisions first.

1. **Does it run here?** Apple Silicon, macOS 27, 16 GB today.
2. **Is the output the right SHAPE?** For extraction and labelling this is the whole game: a model
   that returns prose or chat cannot be used, however clever it is. It must return a schema.
3. **Licence.** If we publish the corpus and the tooling, the licence has to permit it.
4. **Fits.** Download size and peak memory, against a 16 GB machine.

## The metrics

- **Quality against our gold**, per metric appropriate to the layer (see below)
- **Speed**: p50 / p95, on a fixed protocol — 10 warm-up calls discarded, then 100 measured
- **Peak memory**
- **Power and energy** — recorded, but only *after* selection; this is the ANE case, not the gate

**Never pooled.** We learned this the hard way: our decision model showed a pooled calibration
error of 0.0497 while being over-confident by **+0.246 on the hardest stratum** and under-confident
on the easiest. Those cancelled. **Every quality number is reported per stratum, never averaged.**

---

## The test data — what we have, what we must build

| layer | test set | status |
| --- | --- | --- |
| **verify** | 554 (claim, source) pairs, of which 57 are held out | **exists** — needs gold verdicts |
| **label** | claims with correct kind/confidence | partial — agent labels are *provisional*, not gold |
| **reconcile** | claim pairs, contradictory or not | 17 known-contested cases |
| **retrieve** | queries → relevant chunks | exists — EXP-007/008 MTEB work |
| **parse** | PDF → gold text | **must build** |
| **extract** | passage → gold claim list | **must build** |

## The anchor problem

Every quality metric compares a tool against **gold**. For most layers we do not have gold — we have
model output, or agent output, which is the same model checking itself.

**The only way out is human labelling of a small set.** A hundred items, read carefully, becoming the
anchor. Everything else is models comparing to models; that handful is the only place ground truth
exists. This cannot be automated and should not be faked.

## Where we start, and why

**Layer 4, verify.** Because:

- the test data **already exists** — 554 claims with their sources, 57 of them held out and
  uncontaminated
- there are **four candidates**, one of them already running on our ANE
- it is the layer currently **blocking** the knowledge base — the labels cannot be trusted until
  something can check claims against sources
- and the failure mode is known: general-purpose checkers score **near chance on code and technical
  content**, so this is exactly where a domain test is worth running

---

## Environment facts (measured today)

```
python        torch 2.13.0 · transformers 5.16.1 · coremltools 9.0 · onnxruntime 1.30
installed     gliner 0.2.29  ← GLiNER already present
available     mlx via uv tool at ~/.local/share/uv/tools/mlx-lm
missing       docling · outlines · ollama · llama.cpp
HF cache      4.6 GB, holds our typed-decisions set, MTEB sets, Qwen3-Embedding/Reranker-0.6B
disk          /Volumes/data has only 25 GB free → download models to M4-Partage (664 GB free)
```

**Set `HF_HOME` to a roomy volume before downloading anything.** `/Volumes/data` is where the live
work sits and 25 GB will not survive an afternoon of model pulls.