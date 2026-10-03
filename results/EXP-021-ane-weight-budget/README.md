# RESULT — the ANE weight budget counts FILES, not const() nodes

**Date:** 2026-09-25 · **Machine:** Mac mini M4 (H16G), 16 GB, macOS 27.0
**Method:** hand-authored MIL through the private `AppleNeuralEngine.framework` path
**Code:** `bench/ane-dma-test.m` · `SHAPES="64,64,32,N" SAME_SHAPE=1 [SHARED_BLOB=1] ./bench/ane-dma-test`

---

## What was in dispute

Orion's `docs/ane_constraints.md` #15 states:

> *"The ceiling is 16 across a 2304x range in per-weight size… Every BLOBFILE tensor costs a full
> slot… It is a count budget, not a byte budget."*

Verified in their `experiments/ane_weight_limit_probe.m` with `14 conv → SUCCESS, 17 conv → FAILED`.

A separate build on an M5 Max observed a **d256 fp16 chain compiling fine with 256 `W()` const nodes,
all pointing into one `weight.bin`** — and proposed that the budget is tied to **entries in the weights
dictionary**, not `const()` node count. To avoid resolving this by argument, we measured it.

## The measurement

Two arms, identical in every way except how the weights are addressed. Every conv is `64→64`, seq 32 —
size and shape held constant so only the **count** varies, exactly as Orion's own probe held size
constant. Correctness is checked by construction: all-ones weights, all-ones input, so a 1×1 conv must
produce exactly `in_dim` = **64.0**.

| N convs | separate file each | one shared file, per-tensor blocks |
| ---: | --- | --- |
| 1 | COMPILED, 64.0 ✓ | COMPILED, 64.0 ✓ |
| 8 | COMPILED, 64.0 ✓ | COMPILED, 64.0 ✓ |
| 16 | COMPILED, 64.0 ✓ | COMPILED, 64.0 ✓ |
| **17** | **FAILED** | **COMPILED, 64.0 ✓** |
| 24 | FAILED | COMPILED, 64.0 ✓ |
| 32 | FAILED | COMPILED, 64.0 ✓ |
| 64 | FAILED | COMPILED, 64.0 ✓ |
| **128** | FAILED | **COMPILED, 64.0 ✓** |

**Every arm that compiled was also numerically correct**, so this is not a compile-only artefact — the
weights really are being read from the right offsets.

## Conclusion

**The budget counts entries in the weights dictionary — weight FILES — not `const()` nodes and not
bytes.** Separate files: 16, then failure. One file: 128 references compile and compute correctly, at
8× the believed ceiling.

Orion's observation was accurate and their framing was incomplete. Their own wording shows why: they
described it as *"16 blobs"*, and never varied the file/reference ratio. Their probe could not have
distinguished the two hypotheses, because every arm referenced its own blob.

## Why it matters

**128 layers per program against a believed 16** is not a footnote:

- **Orion needed 72 programs for Stories110M.** At 128 weight tensors per program that count collapses.
- **The ~119 compile-per-process limit is a compile budget** — needing far fewer compiles makes it much
  less binding, and pairs with the hash-keyed program cache our probe found
  (`purgeCompiledModelMatchingHash:`, `compiledModelExistsMatchingHash:`).
- **Every program boundary is an ANE↔host transfer.** Fewer, larger programs is a direct win.

## Incidental findings from the same session

**BLOBFILE reference offset, settled empirically.** A reference at **64** compiles *and computes
correctly*. References at **0**, **128** and **192** all fail to compile. This reproduces Orion #8
exactly, and it resolves a 64-vs-128 discrepancy between two builds: **there is no disagreement.** The
reference is 64; the payload begins at 128; measured from the reference, the header is 64 bytes. Two
descriptions of one layout, now verified on M4.

**A mulit-tensor blob file is a CONCATENATION of per-tensor blocks**, each `[128-byte header][payload]`,
with tensor *i* referenced at `i × block + 64`. A single header for the whole file cannot describe more
than one tensor — our first attempt did exactly that and failed, which is worth recording because the
error is `InvalidMILProgram` with no hint that the *content* of a file is the problem.

**Two failure modes look identical.** An unwritten blob file and a malformed blob both produce
`InvalidMILProgram`. The loader reads the files back from disk even when the weights arrived in memory
(the `.mlpackage`-as-anchor behaviour), so a dictionary entry with no matching file on disk is simply
absent. Our harness originally assumed the `w0..wN` naming and so never wrote the shared-file case at
all — it looked like a compiler rejection and was a missing file.

**Correctness is not implied by compilation.** Offsets 0, 128 and 192 do not fail because the compiler
disapproves of them; they fail because the size field cannot be located. And a wrong-but-compilable
reference would read the wrong bytes and produce plausible garbage with no error at all. The ones-weights
check is what makes any of this meaningful — and it is the correctness arm EXP-020 was missing.

## Provenance and credit

Skeleton from `maderix/ANE` (`inmem_basic.m`, MIT). MIL conventions and the BLOBFILE header from
`mechramc/Orion` (`core/mil_builder.m`, MIT; constraints `docs/ane_constraints.md`, MIT). The
file-vs-node hypothesis came from an independent build on an M5 Max, and this measurement was run to
settle it rather than argue it.

Three of the four harness bugs encountered while getting here were ours, not the ANE's: a deleted
output-declaration block, an assumed filename pattern, and a hardcoded two-element return tuple left
over from when the harness only had 1–2 convs. Recorded because each produced an error message that
pointed somewhere else.