# EXP-041 — multi-input ANE battery: how wide is the single-input limitation, per machine?

## Question
maderix/ANE README lists "multi-input ANE requests cause 0x1d error". Issue #56 (2026-10-23)
shows 2 inputs compiling AND evaluating bit-exact on an M4 Air (h16g, 26.3.1), asking whether the
refusal is training-path-only, OS-fixed, or shape-dependent. This is measured here on both fleet
chips at the same OS build (27.0.1 / 26A434), on the public-era private API surface
(`_ANEInMemoryModelDescriptor` + `_ANEInMemoryModel` + `_ANERequest`), compile and eval stages
reported separately so 0x1d is caught wherever it appears.

## Method
`harness/multi_input_probe.m`: 1x1-valid conv per input (all-ones fill s_k) with an add-fan graph,
per-input distinct constants, exact fp16 arithmetic oracles (out[j] = sum_k cin_k·v_k·s_k),
input-index reversal control, equal and UNEQUAL input surface sizes. Identity stamp
(chip/cores/os/host) on every run. Window: loaded Studio (production oMLX up; this probe is
correctness-only, no timing/energy claims — stamped in each raw capture).

## Results — both machines identical
raw/battery-studio-20261026T232314Z.txt (h17g, Studio), raw/battery-mini-20261026T232328Z.txt
(h16g, mini):

| arm | nin | shapes | compile | eval | oracle |
|---|---|---|---|---|---|
| in1 | 1 | 512×64×64 | OK | OK | MATCH |
| in1-w2 | 1 | 512×64×64, fill 2.0 | OK | OK | MATCH |
| in2-add | 2 | 512×64×64 | OK | OK | MATCH |
| in2-w2fill | 2 | 512×64×64, fills 1.0/2.0 | OK | OK | MATCH |
| in2-rev | 2 | index reversal control | OK | OK | MATCH |
| in3-add | 3 | 512×64×64 | OK | OK | MATCH |
| in4-add | 4 | 512×64×64 | OK | OK | MATCH |
| in2-big | 2 | 2048×256×128 | OK | OK | MATCH |
| in2-small | 2 | 64×16×32 | OK | OK | MATCH |
| in2-mixedsize | 2 | 512 and 256 cin (UNEQUAL surfaces) | OK | OK | MATCH |

**Zero 0x1d anywhere, on either chip, at N up to 4, with unequal input surface sizes.** The README
claim does not reproduce on h16g or h17c at 27.0.1/26A434 on the eval-side private path.

## The real trap this run surfaced: ANE compiler cache aliasing (Code=10, not 0x1d)
First battery attempts showed two-input arms failing `Code=10 verifyBundleAtPath: invalid model`
at LOAD while single-input arms passed. Diagnosis: `hexStringIdentifier` (and the tmp bundle dir
under the ANE compiler cache) is derived from MIL TEXT ONLY. Arms sharing MIL text but differing
only in weight BLOB BYTES resolved to the same cache entry; the second load validated the new
weight bytes against the stale cached bundle and was rejected. Baking every arm-varying constant
(nin, index, cin, cout, seq, values, fill, reversal) into the weight FILENAMES gives each arm its
own hash key and the failure disappears. Preserved as evidence: raw/rejected-*.txt captures taken
before the fix. This is a harness artifact of the in-memory descriptor path, not an ANE input-count
limit — but it will masquerade as one in any test suite that varies weights between same-shape
arms (relevant to any future multi-input regression harness; see EXP-021 weight-file-naming note,
same underlying mechanism).

## Answers to upstream (feeds OUTREACH-B, maderix #56)
1. Two-input compile+eval works on h16g AND h17c at 27.0.1/26A434 (matches their M4 Air result).
2. It works up to 4 inputs and with unequal input surface sizes on both chips.
3. 0x1d was never reproduced here in either direction; when multi-input tests fail on this API,
   check the weight-filename/cache-key collision first — it presents as Code=10 at load, but
   suites frequently mislabel it under the generic multi-input limitation.
4. Surface caveat (GOTCHAS-024 discipline): this is eval-path private API, not the training path.
   Training/grad-input behavior remains untested here.
