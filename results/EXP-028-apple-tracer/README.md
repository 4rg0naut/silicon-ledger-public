# EXP-028 — APPLE TRACER RAID: Apple's own lanes, wires, and fingerprints

Machine: Mac17,14 (M5 Max, h17c), macOS 27.0.1 (26A434), CLT + Xcode 27
(DEVELOPER_DIR-prefixed; no sudo used in this pack). Unprivileged user-run
throughout; production oMLX never touched. Question: what do **Apple's own
tools and public APIs** already tell us about which lane (ANE / GPU / NAX / CPU)
runs what, and which inter-lane wires are observable without our private kANE_*
plumbing? KB-first discipline: every row below was diffed against MEASURE-040/
043/044/046, EXP-024/025/026/027 and the 10-m5 AN-POS lenses before claiming new.

Status (2026-10-08, post-review rework): E1/E3/E4/E5 delivered — E1 now with
the real-workload matrix (granite 3-lane, ML control, matmul2d) in
`results/e1_workload_matrix.txt`; E2 half — Core AI template records but row
streams need privilege (exact one-shot sudo command in
`results/e2_xctrace_coreai.txt`); E4 direct NAX→espresso producer test declared
GAP with the stride contract spec recorded. **E6 added 2026-10-10** — the arch
strings reconciled across two boxes (M5 Max + M4 mini, same OS build)
(`results/e6_arch_surface_reconcile.txt`, `API-138`).

## Answers measured here (details in the named evidence files)

- **Public-log lane fingerprint** (`results/e1_public_log_findings.txt`):
  in-process `com.apple.metalperformanceshadersgraph` events = GPU delegate;
  absence + `com.apple.coreai/runtime` lifecycle = CPU/BNNS. `Delegate init
  (URL)` prints the unmasked cache plan path — public hook from the log stream
  straight into our SU decoder. optsHash keys on options only (cross-model
  stable), modelHash keys on bundle content.
- **Public API ground truth**: `AIModel.deviceArchitectureName == "h17c"` —
  no private decoder needed for the arch name; plans carry `deviceDescriptor
  [0, 40, "h17c"]` + full compiler descriptor JSON in manifest.plist
  (raw/p28_e1_anec/int8_ne_manifest.plist). deep_fp16/deep_int8 (fp32 I/O)
  place on GPU under every preference: placement grammar + dtype gate reproduce
  through the public path (MEASURE-085/086 mechanism, now without odie).
- **Arch surface reconciled, cross-chip** (`results/e6_arch_surface_reconcile.txt`):
  four surfaces on two boxes (same OS build 26A434). The compiler target
  `AIModel.deviceArchitectureName` — corroborated by `mpsgraphtool` `mps.aneArch`
  and enforced by the AOT gate, which accepts exactly one target per box — is
  **h17c** (M5 Max) vs **h16g** (M4 mini). The private
  `_ANEDeviceInfo.aneArchitectureType` returns the `g` form on **both** (h17g,
  h16g): it coincides with the compiler target on the M4 and diverges on the
  M5 Max. Both parts contradict arXiv 2606.22283 ch34 Table 34.3's resolver rows
  (M4 base→h16 vs h16g; M5 Pro/Max→h17s vs h17c) (`API-138`).
- **xctrace Core AI on 27/M5** (`results/e2_xctrace_coreai.txt`): template +
  ODIEProfile/mps-hw-intervals/metal schemas instantiate unprivileged; row
  streams abort ("Could not set the recording priority") — refines MEASURE-043.
- **Espresso wire live** (`results/e3_e4_wire_findings.txt`): mapIOSurfaces +
  IOSurfaceSharedEvent on h17c at median 0.40–0.43 ms/eval (2 surface
  strategies), rc=139 teardown-only. Enginemon user-mode census during
  espresso-only load moves 28 ANE channels: ANE L0/L1 AF+DCS BW, ANS RD/WR,
  ANE-LNK0/1, ANS-DMA/NAND, SOC-NI6 ANS NAN/RAI/RAO/SL, SOC-NI8 ANE UP,
  SOC-NI9 ANEXL U — ANE NoC lenses attribute cleanly with zero GPU compute,
  while AGX UT-engagement still ticks (surface rendezvous keeps AGX warm:
  the invisible wire is two-way).
- **Real-workload lane matrix, measured not assumed**
  (`results/e1_workload_matrix.txt`, `raw/p28_e1_matrix/`): granite 97M via
  granite-runner on the live M5 bundle, three lanes, plus Core ML control and
  matmul2d/NAX. Zero signpost-type events in all 7 captures → op-lifecycle
  signpost blindness measured for Core AI/CoreML/NAX. New signal: the ANE lane
  emits `com.apple.ane/common` `ANEProgramProcessRequestDirect()` per-request
  tracepoints (4,420 = 13 ANE regions × 340 evals, with model string_id and
  status) — per-eval/per-ANE-region client-side attribution exists via
  ane/common, not signposts. `ane/client` bootstrap leaks "ANE Arch String:
  h17s" on a box whose public plans say h17c (resolved in E6 below: compiler
  target H17c, runtime strings separate). NAX
  blind measured: ~880k MSL dispatches → 0 Metal/tensor subsystem events
  (earlier `\bNAX\b` token hits were false positives from our own
  "EXP-027-nax/" path — retracted). Core ML control = zero in-process
  framework telemetry (asymmetry vs Core AI). cpuOnly granite: zero
  MPSGraph/ane → BNNS-by-absence reconfirmed on real granite.
  Substitutions declared: MLX control → Core ML MiniLM control (MLX python not
  installed); matmul2d coreai-torch arm blocked by F-49 ioSurface fatal while
  oMLX live → MSL harness (`p27_load_msl`, rebuilt from tracked `.m`;
  `mlpower-runner` binary also rebuilt from tracked `.swift`).
- Repro: build the E1 harness first (binary is gitignored):
  `swiftc -O harness/p28_coreai_run/main.swift -o harness/p28_run_bin`, then
  `bash harness/p28_e1_signpost.sh [iters]` (default MODEL is machine-local —
  set `MODEL=` to an .aimodel on other boxes); generic capture
  `harness/p28_capture.sh OUT PRED -- CMD`; es rebuild line inside
  `results/e3_e4_wire_findings.txt` header + EXP-027 harness notes.

## Files

- `harness/p28_coreai_run/main.swift` — public Core AI runner (lane arms).
- `harness/p28_e1_signpost.sh`, `harness/p28_capture.sh` — os-log capture.
- `raw/p28_e1_smoke/`, `raw/p28_e1_anec/` — proc/sys ndjson + decoded plan
  (manifest.plist, specialized_model_0.mpsgraph for int8/NE plan 9e4e68a7…).
- `raw/p28_e1_matrix/` — E1 rework: per-workload proc/sys captures (granite
  3-lane, ML control ×2, matmul2d proc/sys, nax/msl sys), matrix_analysis.json,
  tokens.bin fixture. The four largest captures are gzipped in place (F-37
  pattern; MANIFEST pins the `.gz` names — decompress for raw line inspection;
  analysis totals already live in matrix_analysis.json + e1_workload_matrix.txt).
- `raw/p28_e2/toc.xml` + three exported table XMLs (empty-rows evidence).
- `raw/p28_e3/` — enginemon idle/es/idle census jsonl (es_load.jsonl gzipped,
  F-37), 764-name vocab, diff analysis.
- `raw/p28_e4/` — es_harness stage logs (lin/stack, repeats).
- `raw/research-2026-10-08/` — pinned Apple pages (WWDC26-324, lab 8121, docs trio).
- `results/*.txt` — findings (`e6_arch_surface_reconcile.txt` = the E6 arch
  verdict); `MANIFEST.sha256` — pinned shas.

## Next (cheap)

- User one-shot sudo xctrace (command in e2 file) → ODIEProfile rows on M5.
- `sudo log config --mode private:on --subsystem com.apple.anec` + fresh
  specialization → anec Target Architecture line on disk (E1 gap).
- NAX matmul2d producer filling a 224x224 fp16 RowStride-448 surface →
  espresso map+eval (closes the E4 GAP; contract already measured).
