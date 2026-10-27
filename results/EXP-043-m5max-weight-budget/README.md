# EXP-043 — ANE weight budget bracket on the private path: byte ceiling and count ceiling, separated

## Question
The community frames ANE weight capacity as "1 GiB" (maderix/ANE README; sidekick reports M1 Max
refusing 1.022 GB at runtime). EXP-021 showed a COUNT-shaped refusal on h16g (16 separate weight
files). This experiment brackets both axes on the shared-blob private path (`bench/ane-dma-test.m`,
SHARED_BLOB=1, one file referenced at per-tensor offsets) on both fleet chips at 27.0.1/26A434,
extending EXP-021 (which proved count==weight-FILES for the separate-file path, h16g).

## Method
- Byte axis: nconv=32 fixed, C swept until refusal (payload = 32·C²·2 bytes + 128B/converter hdr).
- Count axis: C=1024 fixed (470 MB blob, far below any byte ceiling), nconv swept.
- Verdict = ANE acceptance + exactness oracle (out[0]=C). Timing rides along but window was LOADED
  (production oMLX up; quiet_probe QUIET-KEY stamped in raw/refine-*.log) — no speed claims here.

## Results
### Byte ceiling (both chips identical)
| C | blob file (exact, 32·(128 + 2·C²) B) | h17g Studio | h16g mini |
|---|---|---|---|
| 2048–5120 | 268 MB – 1.68 GB | OK CORRECT | (spot 7168 below) |
| 7168 | 3,288,338,432 B (3.06 GiB) | OK CORRECT | OK CORRECT |
| 7424 / 7680 / 7808 | 3,527,413,760 / 3,774,877,696 / 3,901,755,392 B | OK CORRECT | — |
| 8064 / 8128 | 4,161,802,240 / 4,228,124,672 B | OK CORRECT | — |
| 8192 | 4,294,971,392 B = 2^32 + 4096 | REJECT Code=10 verifyBundleAtPath | REJECT Code=10 |

The refusal is at **shared-blob file size crossing 2^32 bytes**, on BOTH chips, on the SAME OS.
It is 32-bit size truncation, not a capacity policy: 4,294,967,296 B < file 4,294,971,392 B fails
verifyBundleAtPath while 4,228,124,672 B (C=8128, 66.8 MB below 2^32) passes with exact output —
the accept/refuse bracket is 1.6% wide and 2^32 sits inside it. Disk free (158 GB) and RAM
(128 GB Studio, 16 GB mini) are far from exhaustion at the failure point.

### Count ceiling (both chips identical)
| nconv (C=1024) | 64 | 128 | 160 | 192 | 224 | 232 | 240 | 248 | 256 | 384 |
|---|---|---|---|---|---|---|---|---|---|---|
| h17g Studio | OK | OK | OK | OK | OK | OK | OK | OK | ANECCompile FAILED | FAILED |
| h16g mini | OK | OK | — | OK | OK | — | — | — | ANECCompile FAILED | FAILED |

Count budget: **accepted 248 / refused 256** (bracket 3.2%), ANECCompile Code=1 with empty err
body, identical on h16g/h17g. This extends EXP-021: the 16-file refusal there is about SEPARATE
weight FILES, a different axis; with one shared blob the compiler accepts ≥248 tensor references.
Byte and count ceilings are cleanly separable: the 8192-byte failure occurs at nconv=32 (count
fine), the 256-count failure at 470 MB (bytes fine).

### Placement proof (private path has no MLComputePlan — unprivileged ANE lens instead)
`raw/em-proof.json`: enginemon `--interval 200 --duration 15 --json` wrapped around a 7808 arm
(`Cin 7808 ... CORRECT` in same capture). The ANE-floor channels move exactly as validated in
EXP-037 ("move ONLY under ANE arms"): `ane_floor.dcs_f2_ticks` 19.1 M, `lnk_hi_ticks` 38.3 M
during the window. Lane placement of accepted 3.9 GB blobs: demonstrated; refused (8192) arms
never reach dispatch, so no lane claim applies to them.

## What this says to the upstream framing (feeds outreach sidekick #104)
1. "1 GiB ANE weight limit" is not the ceiling on the private path for h16g or h17g at 27.0.1 —
   3.94 GiB (4,228,124,672 B) loads and computes exactly; the wall is at 4 GiB (2^32 B file size).
2. The M1 Max 1.022 GB refusal is real but arch-specific or surface-specific (h14g-era, or a
   different path — separate weight FILES hit EXP-021's 16-file refusal at far smaller sizes on
   h16g). Do not generalize a single arch's number into a universal constant.
3. Two distinct failure signatures to check: ANECCompile Code=1 (count-shaped, mid-compile) vs
   verifyBundleAtPath Code=10 (file-size >4 GB, at load-verify). Reporting which one you got tells
   the maintainer which budget you hit.

## Harness correction (append-only, 2026-10-26)
`bench/ane-dma-test.m` shared-blob assembly used `int` for capacity and tensor offsets: arms whose
cumulative blob exceeded 2^31 crashed host-side (`absurd capacity` NSException) and would have been
mis-recorded as an ANE refusal at ~2 GB. Fixed capacity/offset arithmetic to size_t/u64 and
re-ran: the 5120-and-below ladder stands; the true ANE failure moved from ~2 GB (harness bug) to
4.29 GB (2^32 file overflow). Raw before/after captures in raw/refine-20261026T232416Z.log
(`Terminating app due to uncaught exception … absurd capacity` for the pre-fix 6144 arm, then the
fixed-binary full brackets and the mini cross-check appended after it).

## Byte-wall refinement (append-only, 2026-10-27)
C=8064 and C=8128 arms run to tighten the accept side of the 2^32 bracket (raw log
`raw/byte-wall-2_32-20261027T002835Z.log`, QUIET-KEY-stamped, loaded window, accept-arms-only):
both OK CORRECT. Max accepted blob refined 7808 → **8128** (4,228,124,672 B); accept/refuse
bracket narrowed from 10.1% to **1.6%**, with 2^32 inside it. Two earlier annotation errors are
corrected here (raw logs left intact, append-only): (a) the refine-20261026T232416Z.log echo
header "== byte probe 7808 (payload 3.83GiB, file 4295006208B < 2^32) ==" had an arithmetically
wrong file size — the true C=7808 file is 3,901,755,392 B, as its own payload line shows
(3810308.0 KB × 1024); (b) the pre-refinement README table listed payload-GB figures mislabeled
as file sizes (e.g. 7168 "3.81 GB" — that was miscalculated payload; true file 3,288,338,432 B).
File-size column above is recomputed exactly from 32·(128 + 2·C²) and cross-checked against every
`shared blob:` payload line in raw/. (c) Count-arm size label: the Method line and count-ceiling
prose say the C=1024 count ladder runs a "470 MB blob" — that figure is the n=224 arm
(224·(128 + 2·1024²) = 469,790,720 B, which PASSED); the refused n=256 blob is 536,903,680 B
(512.0 MiB; raw echo `524320.0 KB`), and n=248 — the largest accepted — is 520,125,440 B.
The size-independence argument is unchanged (both sit far below the 2^32 byte ceiling).

## Window state
ALL runs: LOADED (oMLX production up on Studio; mini idle-ssh). Correctness verdicts are
load-insensitive; the ms/GB/s figures are stamped and non-comparable. Cold-compile data point
incidental: the 8192 refusal took 22.6 s on mini vs 2.5 s on Studio (feeds EXP-042 context only).
Plan-deviation declared: the task cap said artifacts ≤2 GiB; the byte ladder needed 4.29 GiB to
locate the real wall (2 GiB would have stopped at the harness bug, see correction below). Largest
artifact is a transient tmp bundle, not a kept file; kept raws are text/JSON only. Lane claim via
unprivileged enginemon ANE-lens (no MLComputePlan exists for the private path — stated, not faked).

## OS-regression addendum (append-only, 2026-10-27, EXP-044)
The "wall at 2^32" is **OS-version-pinned, not silicon**: on macOS 26.6.2/25G83 the same h16g
generation (Mac16,13 M4 Air) ACCEPTED C=8192 (4,294,971,392 B = 2^32+4096) and every larger size
tested up to C=14336 (13.18 GiB file), exact to the out[0]==C oracle (`../EXP-044-metal-generations/raw/air-wall-26.6.2-20261027T104348Z.log`).
Everything above remains true as measured — on 27.0.1/26A434. Read "the wall is 4 GiB file size"
as "the wall appeared at 4 GiB with macOS 27.0"; filed API-174. This is the "one OS build" caveat
paying rent.
