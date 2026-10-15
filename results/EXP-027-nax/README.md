# EXP-027 — THE SECOND LANE: NAX tensor units + ANE routing close-out

Machine: Mac17,14 (M5 Max, h17c), macOS 27.0.1 (26A434), CLT-only.
Unprivileged user-run throughout; sudo = user one-shot only; production oMLX
never touched (F-49). Question: characterise the M5's GPU Neural Accelerators
("NAX") — existence, submission path, energy, observability — and re-validate
every ANE-zero routing claim against a proven lens.

**Status addendum (2026-10-15) — the quiet-window rerun was attempted and is blocked by a venv drift,
not by the machine.** With oMLX down and screen sharing closed (`harness/quiet_probe.sh`: omlx=down,
loadavg <1) the NX-D capture ran: idle floor **148 / 188 mW** (idle1/idle2, n=11 samples each) —
*lower* than the 426 / 394 mW recorded on 2026-10-08, so the window itself is good.

The matmul2d load arm dies deterministically before producing load samples:
`p27_load_coreai.py` prints `compiled; load loop start`, then
`CoreAIRuntime/NDArray+Pool.swift:77: Fatal error: Failed to allocate storage for NDArray with
byteCount: 4096, sk: ioSurface, st: float16` (rc = SIGTRAP, reproduced twice, 30 s and 5 s runs).
The instrument's own warning names the likely cause: *"coreai-torch has only been validated with
torch<=2.13.0; found torch 2.14.1"*. `.venv-conv` was upgraded after this experiment was closed
(see `evaluation/PLAN.md` env block, corrected 2026-10-15). The 4 KB IOSurface-backed float16
allocation is the NDArray pool's per-iteration buffer, not the operands — so it is the pool path
that regressed, not the GEMM.

To unblock: pin `torch<=2.13.0` in `.venv-conv` and rerun `harness/p27_nxd_capture.sh`, or drive the
load from a torch-free sonde (the compiled MSL control `p27_load_msl.m` / `bench/na_tiles.metal`
still build). No energy row is recorded from this attempt.

Status (2026-10-08): CLOSED except two declared GAPs —
NX-A/B/C/D, MX, ES, AN-POS, AN-STALE, AN-ROUTE, HS delivered; energy-window
rerun under a matmul2d sonde awaits a user quiet window (oMLX unload).

## Answers measured here (details in the named evidence files)

- **What exists** (`results/p27_nax_static.txt`): Apple9 family, MTLTensor API
  surface, AGXMetalG17P driver carrying `tensor.metallib` runtime builtins.
- **How you submit** (`NAX-SUBMIT.md`): no dedicated call — MTLBuffer bytes +
  `matmul2d` instruction claim the NA units; eval median 239.8 us single tile.
- **Multi-tile wall** (`results/p27_r8_ladder.txt`): R8 NO-GO — exactly one
  tilegroup completes at every grid size via the coreai compiler route;
  system GPUCompiler has no matmul2d headers (MSL 4.0/4.1 rejected).
- **Public multi-tile recipe** (2026-10-08, `NAX-SUBMIT.md` "Multi-tile
  recipe" + `results/p27_metalhlo_build.txt`): MetalHLO @44b3a04 (cloned
  hub-side `tools/vendor/MetalHLO`, Xcode-27 build PASS / CLT fails at
  `metal` CLI) bundles MLX's `gemm_nax` (MPP `matmul2d<desc,
  execution_simdgroups<8>>`, 128×128 tile / 8 simdgroups / 256 threads,
  64-tile variant at 4 simdgroups for low-occupancy shapes; `dextents` and
  `.slice()` are **(cols, rows)** — inner-stride dim FIRST; MSL 4.0 + Apple9;
  buffers only, no MTLTensor host API) — line-indexed in NAX-SUBMIT.md;
  matmul2d compiles on this box via Xcode 27 SDK headers (NX-B wall is
  CLT-specific); R8 rerun = next slice, correctness-gated.
- **What it costs** (`results/p27_counters.txt` + EXP-024 C7): matmul2d vs
  matched SIMT arm −13.3% per tile (561,612 vs 647,457 mJ/Mtile, signal 1210×
  the 0.1 mW idle floor); dispatch-bound at single-tile size.
- **What observes it** (`results/p27_nxd_nax_lenses.txt`): zero TENSOR-named
  IOReport channels exist; PS13 = generic top-perf-state engagement (NOT
  matmul2d-exclusive); ANEXL/ANE-UP SOC-NI channels are the ANE lenses
  (AN-POS validated: `results/p27_anpos_counters.txt`; **promoted to a
  calibrated metric 2026-10-10**: `results/p27_anpos_promote.txt` — SOC-NI9
  `ANEXL U` reads 0 in every idle/GPU/CPU window and ~19.6k in both ANE
  windows of a matched matrix, so it is lane-exclusive and unprivileged).
- **MilAneflow ABI + AneFlow opset gates** (`results/p27_mila_abi2_findings.txt`),
  **espresso Path-B eval stage** (`results/p27_es_findings.txt`),
  **stale-program hazard REFUTED on public path** (`results/p27_stale_test.txt`).

## WX cross-validation (2026-10-08, arXiv:2606.22283 + public tooling)

Full analysis: `results/p27_paper_xval.md`, `results/p27_mpsgraphtool_write_side.txt`.
Ledger rows (ids verbatim, values as recorded in `results/measurements.json`):

| row id | value | unit | verdict vs our anchors |
|---|---|---|---|
| xval-m5-gpu-compute-roof-fp16 | 30862 | GFLOP/s | SUPERSEDED 2026-10-10 → CONFLICT-DECLARED: the "18-core" tag was a CPU count leaking into a GPU label; anchor box (Mac17,14, 128 GB) is the **40-core** M5 Max SKU (probe.txt `gpu 40 cores`); per-core 60750/40=1519 vs paper 30862/10=3086 (−51%), not +9.3% — see CORRECTION in `results/p27_paper_xval.md` |
| xval-m5-gpu-bandwidth-roof | 229.7 | GB/s | CONFLICT-DECLARED (streaming-roof/base-die vs our steady-state 561.6 read) |
| xval-m5-cpu-bandwidth-roof | 130.4 | GB/s | CONFLICT-DECLARED (same caveat; our read 273.5) |
| xval-m5-ane-matmul-roof | 10191 | GFLOP/s | GAP-DECLARED (no local ANE TFLOPs battery yet) |
| xval-m5-ane-dispatch-floor | 0.23 | ms | KEPT-APART from our 0.2398 ms matmul2d eval — different stacks, no conflation |
| xval-h17c-num-nes | 32 | cores | TRIPLE-SOURCED: paper table 34.1 + EXP-026 coreai-cache h17c dirs + mpsgraphtool emitting h17c here. Observation KEPT; decode SUPERSEDED 2026-10-10: 32 matches neither this die's 16-core ANE (Apple per-SKU fact) nor its 40-core GPU; matches sibling 32-core Max GPU SKU class — `num_nes` semantics OPEN, do not divide by it (`knowledge/ane/05-gotchas.md` GOTCHAS-087) |

Public-tool corroboration harvested: `/usr/bin/mpsgraphtool convert
-specializeForDevice` emits the same `specialized_model_N.mpsgraph` naming as
the coreai cache, the byte-equal ANE dtype whitelist string, `mps.aneArch
h17c`, `mps.deviceGPUCoreCount`, and the `mps.aneEnableFWToFWSignal` attribute
(kANEF knob, dialect-addressable). Attribution sweep: MIL→anec.*→hwx→aned
chain, MPS-MLIR RFC (Apple 2024-02), hwx lineage (mdaiter/eiln/freedomtan),
ANE-efficiency headline — published prior art, credited; coreai-cache
contents, `ane_family`, `Perf_State` semantics, per-tile matmul2d joules —
zero-hit territory, still ours.

## Layout & build

- `NAX-SUBMIT.md` — submission recipe (read first). `docs/` — enginemon
  proposals for the owner session. `harness/p27_*.{m,py,sh}` — probes
  (binaries gitignored, rebuild via headers: `clang -framework Metal
  -framework Foundation p27_<probe>.m -o p27_<probe>`). `results/` — evidence.
  `raw/` — enginemon windows (+`raw/research-2026-10-08/` pins incl. the
  2606.22283 PDF). `raw/MANIFEST.sha256` verifies captured files.
- WX spike commands + outputs: `results/p27_mpsgraphtool_write_side.txt`.

## Deviations (declared)

- Matmul2d energy window rerun under the ANEXL/PS13 sondes awaits a user-run
  quiet window (standing rule: agents run no GPU energy work while oMLX lives).
- Full SSA decode of mpsgraphtool packages still needs the DialectPlugin stub
  (shared blocker with EXP-026 SU deviation).
- Paper numbers are external-measured (M5-base/H17s); conflicts vs our rows are
  declared in the xval table, never adjudicated silently.
