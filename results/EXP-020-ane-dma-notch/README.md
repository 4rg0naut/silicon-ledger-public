# RESULT — the ANE kernel-DMA notch exists on the M4, and the split fix works

**Date:** 2026-09-25 · **Machine:** Mac mini M4 (H16G), 16 GB, macOS 27.0
**Method:** hand-authored MIL, compiled and dispatched through the private
`AppleNeuralEngine.framework` path. No downloaded models required.
**Code:** `bench/ane-dma-test.m` · **run:** `./bench/ane-dma-test` (and `ORDER_REVERSE=1`)

---

## The question

Eileen Yoon measured on an **M3** that when one ANE core streams an exact multiple of 1 MiB, a 14-bit
prefetch-ring counter wraps to zero at the finish line, the prefetcher concludes nothing remains to
fetch ahead for, and throughput collapses from ~45–60 GB/s to 17–19 GB/s. Her fix: **do not request
exactly 1 MiB — split the transfer in two.**

M1 and M5 Max are reported unaffected. **M4 was unknown.** That is what we tested.

## Why it was runnable here

The transfer size is set by the layer shape:

```
bytes/core = (Cout / 16) × Cin × 2
```

so a 1×1 convolution with `Cin=2048, Cout=4096` gives `(4096/16) × 2048 × 2 = 8,388,608` bytes over
16 cores = **exactly 1 MiB per core**. Choosing the shape chooses the transfer, which means the whole
experiment needs no pretrained weights — the MIL is authored and the blobs generated.

## The arms

| arm | convs | Cin → Cout | bytes/core | role |
| --- | ---: | --- | ---: | --- |
| `notch_1mib` | 1 | 2048 → 4096 | **exactly 1 MiB** | the suspected notch |
| `control_16k` | 1 | 2048 → 4032 | 1 MiB − 16 KiB | **the control** — same shape family, not a multiple |
| `split_2x` | 2 | 2048 → 2048 each | 0.5 MiB ×2 | **the fix** — same bytes, same maths, split |
| `notch_2mib` | 1 | 4096 → 4096 | exactly 2 MiB | a larger multiple |

## Results — 6 runs per arm, 3 forward and 3 reverse, medians

```
arm             n   median     min     max   spread
notch_1mib      6    23.65   21.71   25.03     3.32
control_16k     6    43.53   42.20   44.81     2.61
split_2x        6    43.55   40.80   44.89     4.09
notch_2mib      6    30.45   29.51   32.78     3.27

notch_1mib -> split_2x : 23.65 -> 43.55 GB/s = 1.84x
notch_1mib -> control  : 23.65 -> 43.53 GB/s = 1.84x
```

### Reading it

**1. The M4 is affected.** 23.65 GB/s at exactly 1 MiB/core against 43.5 GB/s otherwise. The spread
within each arm is ~3 GB/s, so the ~20 GB/s gap is not noise.

**2. The clean comparison is unambiguous.** `notch_1mib` and `split_2x` move *identical* bytes
(16.78 MB) and compute *identical* maths — the same output computed as one 4096-wide conv or two
2048-wide ones. Only the transfer split differs, and it is **1.84× faster split**.

**3. The control behaves as a control should.** A layer off by 16 KiB from the boundary shows no
penalty at all (43.53 GB/s). If the effect were about layer size rather than exact multiples, this
arm would have been throttled too. It was not.

**4. The split matches the control exactly** — 43.55 vs 43.53 GB/s. Splitting recovers *full*
bandwidth, not merely most of it.

## What is not settled

- **`notch_2mib` is only partially throttled** (30.45 GB/s, between the two). The original report
  describes *all* multiples collapsing to the same floor. Ours does not. Either the M4 behaves
  differently at higher multiples, or something else is in play. **Unresolved.**
- **The GB/s figure is effective, not counter-derived.** It is weight bytes ÷ eval time. The original
  work read the ANE's own memory-controller byte counters. We can do the same — `enginemon` reads
  those counters unprivileged — and that would be the stronger measurement.
- **Outputs were not checked for numerical correctness.** The blobs are filled with a constant, so
  the outputs are not independently meaningful. A correctness arm is needed before publishing.
- **One machine, one OS build.** No M1/M3/M5 comparison.
- Absolute rates differ from the original: we see 23.65 throttled / 43.5 nominal on M4 against
  17–19 / 45–60 on M3. Same phenomenon, different silicon — which is the point of testing it.

## Provenance and credit

The skeleton is `maderix/ANE`'s `inmem_basic.m` (MIT) — the minimal Path A example. The MIL
conventions and BLOBFILE header format come from `mechramc/Orion`'s `core/mil_builder.m` (MIT):
weight shape `[OUT,IN,1,1]`, `pad_type "valid"`, BLOBFILE `offset=uint64(64)`, and the 128-byte header
with magic `0xEFBEADDE` at byte 64 — a format both projects implement identically and independently.
Constraints honoured from Orion's `docs/ane_constraints.md`: #4 (≈49 KB minimum surface), #8 (blob
offset 64), #9 (`milText` as `NSData`), #15 (2 weight tensors, well inside the 16-blob budget).

The erratum being reproduced is Eileen Yoon's, *"Getting 50 GB/s Back Out of the ANE"*:
<https://eiln.github.io/posts/ane-dma.html>

**And an incidental confirmation:** the compiler error text is literally
`_ANECompiler : ANECCompile() FAILED` — exactly what our knowledge base concluded `_ANECompiler` was:
a log prefix, not a class.

## To make this publishable

1. read the ANE byte counters with `enginemon` rather than inferring from time
2. add a correctness arm using non-constant weights
3. sweep the boundary finely — 2016 … 2048 … 2080 — to show the shape of the notch rather than two
   points
4. repeat on any second Apple Silicon machine available