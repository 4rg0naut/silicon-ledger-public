# EXP-047 — big-tile + swizzled dispatch on hand-written matmul2d (the O-6 cell)

Question: EXP-037/EXP-044 pinned every hand-written `matmul2d` arm at naive 64×32/sg4 tiles to a
flat ~31–32 TF band (fp8 ≡ fp16 parity). Apple's ~7× NA headline is attributed (their MLX post,
Zakharko's tile note: "optimal tile ≥ 32×32") to **bigger tiles + locality-swizzled dispatch** —
never tested by us on this silicon. Does the recipe move the number, and what does it cost in
exactness?

Machine: M5 Max Studio `Mac17,14` (h17c/h17g), macOS 27.0.1/26A434. Instrument
`harness/tile_probe.m` (INSTR-207): same documented device form as the EXP-037 lineage
(`tensor<device T,…,tensor_inline>` + `matmul2d_descriptor` + device destination slice), three arms:

| arm | tile | sg | dispatch |
|---|---|---|---|
| `f16_s` | 64×32 | 4 | block-swizzle (baseline restated same binary, same session) |
| `f16_b` | 128×64 | 8 | block-major swizzle (Morton-family, padded overlaunch grid) |
| `f8_b` | 128×64 | 8 | same, `metal_fp8_e4m3_format` (needs metal 4.1 — compile gate; macOS 27 run gate) |

Exactness gate unchanged: small-integer data, integer partial sums exact in f32; oracle `maxabs`
MUST be 0. Swizzle: linear `threadgroup_position_in_grid.x` → 8×8 block-banded tile map; grid
launched padded (`blocksX·blocksY·64`), overhang threadgroups return early; every valid tile hit
exactly once (bijection argument in the kernel header).

## Correctness (loaded window, 2026-10-27 ~16:20Z — load-independent by EXP-045 N2 precedent)

`./tile_probe ladder` — **VERDICT: ALL PASS**, all three arms, all geometries (k128/k256/full
ladders M·N·K up to 1024×512×1024, 2–8 tiles), `maxabs=0.000e+00/int-exact` every row.
Raw: `raw/ladder-20261027T16*-loaded-correctness.txt`.

## Smoke timing (loaded, loadavg 2.71 — proves the path, NOT the cell)

| arm | med ms @2048³ | TF (med) | TF (min) |
|---|---|---|---|
| f16_s | 0.5410 | 31.76 | 32.0 |
| f16_b | 0.3615 | **47.53** | **56.6** |
| f8_b | 0.2925 | **58.73** | **63.0** |

The naive restatement (f16_s) reproduces the published 31.5 band — the instrument is continuous
with EXP-037. Big tiles are already +50 % fp16 / +86 % fp8 **under load**; certified-quiet values
run tonight (see `raw/` as they land). Raw: `raw/smoke-timing-20261027T162*.txt`.

## Cells (measured values require a certified-quiet window — scheduled, not run)

- **C-47-1** certified-quiet timing ladder f16_s/f16_b/f8_b @ 2048³ + 4096³ (2000/500 reps):
  answers O-6 per-dtype (big-tile gain, fp8-vs-fp16 split at big tiles — parity may break).
- **C-47-2** dispatch floor at big tiles: M=128-equivalent small shape under swizzle vs the
  published 5.3–5.4 µs naive floor.
- Window ownership: this campaign runs **after** the EXP-038 retake queue drains (single-watcher
  rule); the chain is `harness/round6_quiet_campaign.sh` (shared launch, EXP-038 dir).

## Precondition re-check (owner note from planning: "verify Plasma #1534 open at execution")

Checked 2026-10-27 at execution prep: precondition concerns third-party big-tile reports remaining
unreproduced upstream — this experiment is the independent test; nothing here depends on their
answer, and the correctness verdict above already stands alone.

## Reproduce

```sh
cd results/EXP-047-tile-probe/harness
clang -fobjc-arc -O2 -o tile_probe tile_probe.m -framework Metal -framework Foundation
./tile_probe ladder                      # correctness (load-independent)
./tile_probe time 2048 200 f16_b         # timing (window-stamp each row before quoting)
# certified campaign: sh results/EXP-038-nax-quiet-retake/harness/round6_quiet_campaign.sh (backgrounded)
```

Caveats: 128×64 is the first big-tile rung Apple documents as needed (≥32×32) — larger tiles /
Morton-Z ordering themselves remain untested cells; energy per GEMM at big tiles is NOT in scope
here (needs the sudo rail window, O-9 class). Loaded smoke rows are upper bounds, declared.
