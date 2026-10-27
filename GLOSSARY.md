# Glossary — house vocabulary

Plain-language key for the recurring terms in this mirror, so no page needs a preamble.
Where a term is an Apple API name, that is stated; where it is ours, it is ours.

## Surfaces and lanes
- **surface** — one concrete execution path a model can take (e.g. `coreai` coreAI compile→eval,
  `mpsgraph` MPSGraph, `exec` private ANE bundle path, `cpu`, `gpu`). Numbers never transfer
  between surfaces without saying so.
- **lane** — a hardware execution unit class measured per surface (ANE, GPU tensor units "NAX",
  CPU, IO accelerator). The consolidated table lives in
  [`knowledge/ane/16-neural-accelerators.md`](knowledge/ane/16-neural-accelerators.md).
- **door** / **side door** — the private IOKit kernel interface into the ANE (service
  `ANEDriverRoot`, direct-path client classes); see `results/EXP-033-door-map/README.md`
  and [`knowledge/ane/14-door-map.md`](knowledge/ane/14-door-map.md).

## Core AI compiler
- **arch token** (`h17c`, `h16g`, `h15g`) — the per-chip target the Core AI compiler and the
  private ANE runtime each name; the two systems can disagree (the `g`/`c` split is finding
  round-2 `#1`). The mapping rule belongs to Apple — our evidence and the naming ladder are in
  [`knowledge/ane/11-platform-naming.md`](knowledge/ane/11-platform-naming.md).
- **`verifyBundleAtPath`** — Apple's Core AI compiler call that validates an ANE compile bundle
  on disk (found in `Espresso`); its `Code=10` refusal is the weight-budget wall of
  `results/EXP-043-m5max-weight-budget/README.md`.
- **`ANECCompile Code=N`** — the compiler's numeric failure code (10 = bundle validation
  refusal, 1 = tensor-count refusal); internal Apple API, version-unstable.
- **shared-blob private path** — the ANE compile path that takes one big concatenated weight
  blob with per-tensor offsets (vs Core ML's one-file-per-weight path); the byte-wall subject of
  `results/EXP-043-m5max-weight-budget/README.md`.

## Bench protocol
- **window** — one continuous measurement session with a stated machine, thermal state, and
  metric convention; cells from different windows never mix. A **contaminated** window had
  external load; its sets are quarantined, not deleted.
- **certified** — a result whose every cell carries window·metric-convention·instrument·capture-link
  and passes the KB gates.
- **QUIET-KEY** — our own protocol marker for a measurement window re-run with machine-state
  evidence captured before/after; the key certifies the window, not the number.
- **DECLINED** — no number shipped: the measurement was attempted or planned but refused by
  policy (unfinished window, contaminated machine, unsupported surface). A DECLINED cell is a
  measurement record, not an estimate.
- **INVARIANT** — cross-run consistency check (machine ID, arch token, schema version); its
  failure blocks the machine lane of publishing.
- **RETRACTED** — a number once published, now withdrawn; the row stays, struck, with the
  reason and the replacement linked.
- **p50** — median of samples, our default latency stat; `warm` = after load, `cold` = first.

## Claim and status vocabulary
- **verified / human / unverified** — who confirmed a claim; the counts per state are in
  [`PUBLIC-OPENCLAIMS.md`](PUBLIC-OPENCLAIMS.md) and the per-record status JSONLs.
- **NEW / EXT / KNOWN** — status key on WHATSNEW: we could not find it published / we extend
  published work / already public.
- **oracle** — the exact reference an output is checked against (exact-integer arithmetic,
  fp64 CPU, or cross-surface bit comparison).
- **bit-exact** — outputs compared at bit level, not within a tolerance.
