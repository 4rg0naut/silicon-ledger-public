# What's new — 2026-10-10

This mirror is the **distilled** public slice of a private Apple-silicon reverse-engineering
corpus (private paths scrubbed, evidence kept). This page is the one-screen summary: what the
latest round found, and — honestly — **what is new versus already public**. Full priors are in
[`knowledge/ane/SOURCES.md`](knowledge/ane/SOURCES.md) ("Novelty check 2026-10-10").

## Status key
**NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public.

## The findings

| # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | A **cross-chip arch identity**: the Core AI compiler target is `h17c` on an M5 Max and `h16g` on an M4 mini, while the older private `_ANEDeviceInfo` selector returns the `g` form on both (`h17g`/`h16g`) — so it agrees on the M4 and **diverges on the M5 Max**. | **EXT** — the rule is public, and the **M4 half is our own merged PR** ([coreai-model-zoo #36](https://github.com/john-rocky/coreai-model-zoo/pull/36)); new: the M5 Max `h17c` target + the selector divergence | [`results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt`](results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt) |
| 2 | **Core AI's on-disk specialization cache decoded** — the `~/Library/Caches/coreai-cache` layout (`modelHash` per model vs `optsHash` = a pure function of the compute-unit options). Nothing public documents these bytes. | **NEW** | [`results/EXP-026-ane-kitchen/results/coreai_cache_format.md`](results/EXP-026-ane-kitchen/results/coreai_cache_format.md) |
| 3 | **The cached `mpsgraph` bytecode printed as readable MLIR** — a stub dialect plugin + a bytecode rewrite recover the op graph, region functions, shapes and `mps.aneArch`/`aneRegionsSHA`. | **EXT** — "MPSGraph is MLIR bytecode" is public (Apple's LLVM RFC, `mpsgraphtool`); **new**: the private `aicode`/`placement` dialects and the printing technique | [`results/EXP-026-ane-kitchen/results/p2b_model_src_ir.txt`](results/EXP-026-ane-kitchen/results/p2b_model_src_ir.txt) |
| 4 | **`PMP0/SOC-NI9 "ANEXL U"` is a lane-exclusive, calibrated ANE activity counter** — 0 in every idle/GPU/CPU window, ~19.6k under ANE work. The channel is known; its **exclusivity** is not. | **NEW as a discriminator** | [`results/EXP-027-nax/results/p27_anpos_promote.txt`](results/EXP-027-nax/results/p27_anpos_promote.txt) |
| 5 | The `PMP0` **`ANE-DCS-BW` floor-residency channel is *not* ANE-specific** (reads higher at idle than under ANE load). | **NEW** (negative result) | same file as #4 |

A correction note for finding #1 is filed upstream:
<https://github.com/sbryngelson/ane-guide/issues/1>.

## What this mirror is (and is not)
- **Is:** measured numbers, the failure corpus, and the instruments, with every claim carrying its
  command and its caveats. The claim layer is machine-checkable — see
  [`PUBLIC-OPENCLAIMS.md`](PUBLIC-OPENCLAIMS.md) (616 claims, 741 provenance events, 0 invalid).
- **Is not:** vendor claims, or a promise that any of the private/documented Apple interfaces are
  stable. Where a claim is an AI's check rather than a human's, it says so.

Start at [`README.md`](README.md) and [`PUBLIC-INDEX.md`](PUBLIC-INDEX.md).
