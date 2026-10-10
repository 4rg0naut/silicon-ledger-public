# EXP-026 — the ANE compiler kitchen: ANECCompile, MilAneflow, and who actually launches the service (M5 Max)

**Status:** IN PROGRESS mapping pass 2026-10-07 (kanban phase-2B `dab9dfe1a23341cd`
lanes K1–K6). Kitchen doors inventoried and three of them characterized (legacy C
door rejected-closed, service launch-model mapped, espresso door OPEN — blocker
now surface geometry, fix recipe recorded); `model.src`
schema capture remains open with a corrected trigger recipe (see Deviations 2).
**Machine:** Mac17,14 (M5 Max) · macOS 27.0.1 (26A434), CLT-only. Provenance:
follows `results/EXP-025-ane-gpu-sync/` phase-2 (`docs/P2-LANE-A.md` §7); tools
vendored at `tools/vendor/coreml_to_ane_hwx` (hub, outside this submodule,
commit `0da81de`, locally patched `P2B_SRCNAME/P2B_ISMIL` env hooks).

## Question

Phase-2 relocated the wall from "no Xcode toolchain" to "espresso door is legacy;
the live producer is ANECompilerService". Open that kitchen: what compiler entry
points exist on 27.0.1/M5, which one does the shipping stack actually use, what
feeds it, and what does it accept?

## Headline findings (all measured this session; evidence `results/p2b_*`)

1. **`ANECCompile()` is alive and callable in-process** — `ANECompiler.framework`
   dlopens and exports 140 `_ANEC*` symbols incl. `ANECCompile`,
   `ANECCompileJIT/Offline/Online/WithFunctionCall`, `ANECConvLayerDescInitialize`
   (netlist-era layer descriptors), `ANECGetMPSDialectSupportedVersion`
   (`p2b_recon_anecompiler_exports.txt`). freedomtan's `mil_to_hwx` +
   `hwx_parsing` build CLT-only on 27/M5 unmodified (`tools/vendor/...`,
   `make` in `mil/` and `hwx_dump/`).
2. **…but the legacy C door rejects current MIL text**: every coremltools-9 /
   coremlc-3600 `model.mil` — MiniLM and 7 synthetic conv chains
   (`p2b_battery_aneccompile.txt`, 7/7) — fails `ErrorList=(InvalidMILProgram)`
   before any arch handling (`h17c/h16g/h13g` identical; `model.src` renaming
   shifts it to `InvalidCompilationParam`). Dialect-level refusal, not model
   complexity.
3. **The modern MIL front-end is `MilAneflow.framework`** — a small C API:
   `make_milaneflow_context`, `milaneflow_try_program_from_string/_from_file`,
   `try_function` (op-support oracle for the routing battery),
   `execute_function`, `opset_name_list`, error-copy pair
   (`p2b_recon_milaneflow_exports.txt`). Not in freedomtan's, geohot's, or the
   Bryngelson map. **ABI not cracked this session** — `make_ctx` works,
   `try_program_from_string` candidate signatures crash/return NULL with
   `err_size=0` on both valid and garbage input (`harness/p2b_mila_abi.m`,
   `p2b_mila_file.m` keep the matrix). Needs a disassembly pass (shared-cache
   extraction) to pin arg order.
4. **The XPC service is not a launchd job**: neither ANECompilerService nor
   ANELargeModelCompilerService Info.plist has `MachServices`;
   `NSXPCConnection(com.apple.ANECompilerService)` → lookup error 3; direct
   exec as root exits rc=1 silently; `launchctl print system/...` → Bad request.
   It is spawned by the in-process stack, not by launchd (`p2b_k3_xpc_attempts.txt`).
5. **E5 identity vs ANE cache, measured**: the public loader keeps
   `~/Library/Caches/<clientproc>/com.apple.e5rt.e5bundlecache/<OSBUILD>/<IDENT>/model.milhash`
   — new `<IDENT>` dirs appear when weight bytes OR MIL text change, yet
   ANECompilerService did not re-fire and loads stayed 0.15–0.35 s: the ANE
   program cache key tolerates those mutations (likely op-graph hash), while E5
   re-keys on bundle bytes. Corollary hazard: **weight-byte edits can be served
   stale ANE programs** (`p2b_k4_e5bundlecache_identity.txt`).
6. **Espresso is a dead package-format, not dead input — the K5 door is open**:
   public `compileModelAtURL:` of a legacy `.mlmodel` (coremltools-4-era
   MobileNetV2) on 27.0.1 still emits a **real** espresso program —
   `model.espresso.net` JSON with 170 layers (53 convolution / 70 activation /
   45 elementwise / 1 pool / 1 softmax), `.shape` with layer_shapes, 23 MB
   `.weights` (not the 1 KB preview stub the `.mlpackage` pipeline emits). The
   EXP-025 pathb harness passes `compileModel:` AND `loadModel:` and dies one
   stage deeper at `mapIOSurfacesWithModel:` 0x1D — surface geometry mismatch:
   the program demands a 1×3×224×224 input
   (`layer_shapes.image = {k:3,h:224,w:224,n:1}` measured from
   `/tmp/mnv2.mlmodelc`) while the harness feeds chain-64 surfaces. Fix
   recipe (measured dims + `modelAttributes.liveInputList` strides per
   KB API-068) in `p2b_k5_espresso_door.txt` addendum; executing it — mapping
   matched surfaces and filling the `event_extra_ms` column — is the next
   slice (`p2b_k5_espresso_door.txt`).
7. **`model.src` decoded at last — it is an MLIR bytecode package, user-readable,
   no sudo needed (SU, 2026-10-08)**: `~/Library/Caches/coreai-cache` (client-side,
   `<user>`-owned) keys compiled plans by `<OSBUILD>/<proc>/<ident>` (or
   `<pyver>/<uuid>`) and stores the whole compiler lineage per plan:
   `original_model_N.mpsgraph` (the model.src — `mps`-dialect MLIR bytecode,
   container magic `ML\xefR`, producer `MLIR22.0.0git`, bytecode v6),
   `specialized_model_N.mpsgraph` (placement: 13 `*_ANE_region_*` + 14
   `*_GPU_region_*` symbols for the granite embedding JIT; ANE dtype whitelist
   string `fp16,f8E4M3,si8,ui8,si16,ui16`), `binary_0.llir.bundle/h17c/*.mlir.bc`
   (ANECompiler 10.26.4 LLIR 0.1b output: `anehlo`/`raster`/`llir` dialects,
   every region a fused `anec.linear` "neconv" kernel, 12/13 with `anec.swish`),
   and `binary_0.hwx` — a real Apple ANE task binary that the vendored
   freedomtan parser decodes clean (magic `0xBEEFFACE`, CPU 0x0080/0x9 "[H17
   (A18 Pro/M5)] Dense HWX", InDim/OutDim W=32 H=1 C=64 float16, ActiveNE=4,
   TileDMA/l2/Coeff tables). Full model op set + python provenance come out of
   the string dictionary via `harness/p2b_mlir_bc_strings.py` (dependency-free).
   The v8 sudo window confirmed zero aned involvement for this route (in-process
   dlopen, finding 4's family) — the sandbox was the wrong hunting ground.
   Inventory + decode: `p2b_model_src_inventory.txt`, `p2b_model_src_granite_ops.txt`,
   `p2b_model_src_region_llir.txt`, `p2b_model_src_diff.txt`, `p2b_model_src_hwx.txt`,
   raw artifacts `raw/p2b_model_src/`.

## Core AI specialization cache format (2026-10-10)

The disk-side answer to Deviation 2 ("where does `model.src` live"): on macOS 27 the
Core AI route persists its **whole compile lineage user-readable** under
`~/Library/Caches/coreai-cache/` — no sudo, no sandbox, no `aned` (the JIT route
compiles in-process, K1). Decoded this session:

- **Tool** `bench/coreai_cache.py` (stdlib only, read-only): decodes one plan or the whole
  cache to JSON — `manifest.plist` → versioned dict + compiler descriptor JSON
  (`Package Version/7.0.63/Optimized Modules[0]`), the mpsgraph MLIR-bytecode string
  dictionary (producer / bytecode version / dialects / `main_*_ANE_region_*` vs
  `main_*_GPU_region_*` placement symbols / `mps.*` attrs / ANE dtype whitelist), and
  `binary_0.llir.bundle` + `binary_0.hwx` presence.
- **Spec** `results/coreai_cache_format.md`.
- **Census** `results/coreai_cache_census.json` — 198 plans, layouts osbuild 33 / pyver 165,
  arch stamp `h17c` on all.
- **Key derivation** `results/coreai_cache_keys.txt` — `optsHash` is a model-independent
  function of the compute-unit options (`6C51FA69…` = neuralEngine, `14371356…` = cpu-only),
  `modelHash` is per-model.
- **Readable IR** (`results/p2b_model_src_ir.txt`): the cached plans print as real MLIR —
  a stub dialect plugin (`harness/p2b_mps_dialect_plugin.cpp`) clears the version/resource
  interfaces and `bench/mlir_bytecode.py rewrite` placeholds the private attribute entries.
  Both plans recover: the **original** as the model source (`mps.module`/`mps.func`/
  `mps.constant` with real `dense<>` constants and SSA values; needs `--pad-attrs`), the
  **specialized** as the placement (`mps.aneArch "h17c"`, `mps.aneRegionsSHA`,
  `mps.deviceGPUCoreCount 40`, every ANE/GPU region function with its signature).
  934 lines, 0 errors — the SSA/structure gap closed (private attribute *values* stubbed).
- **KB records** `FORMAT-106`, `FORMAT-107`, `FORMAT-108`, `API-139`.

## Deviations (declared)

1. **XPC direct-drive not completed**: with no launchd registration, the K3
   "self-issued call produces model.hwx" gate waits on either cracking
   MilAneflow (in-process route) or replicating how CoreML spawns the service.
   Both harnesses are in `harness/`.
2. **`model.src` capture — RESOLVED 2026-10-08 via a better route (finding 7)**:
   sudo windows v1–v7 kept missing (v7: system ktrace busy — ledger F-50); v8
   ran the correct watcher (aned sandboxes, per-poll globs; trigger lanes
   verified live) and captured zero aned activity — proving the JIT route
   compiles in-process. The schema came out user-mode from
   `~/Library/Caches/coreai-cache` instead; no further sudo window is needed.
3. `tools/vendor/coreml_to_ane_hwx` carries the local `P2B_SRCNAME`/`P2B_ISMIL`
   patch (2 lines, described in finding 2's experiment).
4. **`event_extra_ms` NOT filled** (finding 6): blocker is harness surface
   geometry, not the engine — exact fix recorded, execution is the next slice.
   IOKit attempt B untouched (unneeded while door A is open).

## Layout

- `harness/p2b_*.m|.py|.sh` — probes (see Build below); `p2b_sudo_capture_v7.sh`
  = user-run sudo (fs_usage variant, hit F-50), `p2b_sudo_capture_v8.sh` =
  sudo aned-sandbox watcher (proved in-process compilation; superseded by
  finding 7); `p2b_mlir_bc_strings.py` = dependency-free MLIR-bytecode
  string-dictionary extractor (works on the gzipped raw artifacts).
- `results/p2b_model_src_*` + `raw/p2b_model_src/` — SU closure: cache
  inventory/census, decoded string dictionaries (granite model.src, ANE-region
  LLIR, original→specialized diff), the first H17-era Apple hwx parsed **on this
  machine from the CoreAI cache** (freedomtan toolchain — the hwx format itself
  is prior art: mdaiter/eiln drivers, freedomtan parser, arXiv:2606.22283
  on-disk-format section; ours is the decode of an M5-era CoreAI emission), and the
  gzipped source artifacts themselves.
- `results/p2b_recon_*` — inventory dumps; `p2b_battery_aneccompile.txt` — K6a;
  `p2b_k3_*`/`p2b_k4_*` — attempt/observation logs; `p2b_k5_espresso_door.txt`
  — espresso revival + measured geometry + surface-dims fix recipe;
  `p2b_k6b_enginemon_mobilenet.txt` — conv-family GPU routing capture.
  Re-stamped 2026-10-08 (EXP-027 AN-POS lens validation): the counter that would
  have caught ANE activity is PMP0/SOC-NI `SOC-NI9 ANEXL U` (ANE-exclusive,
  validated 0→14,746 on a known-ANE program; companion `SOC-NI8 ANE UP`) — it read
  0 in that window ⇒ conv-family GPU routing is a lens-validated TRUE NEGATIVE
  (KB API-129).
- Vendored toolchain lives hub-side: `tools/vendor/coreml_to_ane_hwx` (gitignored).

## Build / reproduce

```sh
# inventory (unprivileged)
cd results/EXP-026-ane-kitchen/harness
clang -fobjc-arc -o p2b_fw_probe p2b_fw_probe.m -framework Foundation && ./p2b_fw_probe
clang -fobjc-arc -o p2b_compiler_probe p2b_compiler_probe.m -framework Foundation && ./p2b_compiler_probe
dyld_info -exports /System/Library/PrivateFrameworks/ANECompiler.framework/ANECompiler
dyld_info -exports /System/Library/PrivateFrameworks/MilAneflow.framework/MilAneflow
# legacy C door battery
clang -o /tmp/mil_to_hwx -x objective-c++ -std=c++17 -framework Foundation \
  -framework CoreFoundation -F/System/Library/PrivateFrameworks \
  -framework ANECompiler -framework Espresso tools/vendor/coreml_to_ane_hwx/mil/mil_to_hwx.cc
python3 p2b_milgen.py 64 128 1 bat && /tmp/mil_to_hwx bat -a h17c   # -> InvalidMILProgram
# XPC attempts
clang -fobjc-arc -o p2b_xpc_client p2b_xpc_client.m -framework Foundation && ./p2b_xpc_client
# espresso revival (K5) — needs a legacy .mlmodel, e.g. coremltools-4 MobileNetV2
# (source used: /tmp/MobileNetV2.mlmodel, ~24 MB)
clang -fobjc-arc -o /tmp/p2b_compile harness/p2b_compile.m -framework Foundation -framework CoreML
cp /tmp/MobileNetV2.mlmodel /tmp/mnv2.mlmodel
/tmp/p2b_compile /tmp/mnv2.mlmodel      # -> /tmp/mnv2.mlmodelc: model.espresso.{net,shape,weights}
PATHB_DIR=/tmp/mnv2.mlmodelc results/EXP-025-ane-gpu-sync/harness/pkgb_harness pathb
  # (build first if absent: see EXP-025 docs/P2-LANE-A.md "PATHB_DIR=<bundle> ./pkgb_harness pathb")
  # -> compileModel: + loadModel: pass; MAP_FAIL 0x1D at mapIOSurfaces (chain-64 surfaces)
python3 -c "import json; print(json.load(open('/tmp/mnv2.mlmodelc/model.espresso.shape'))['layer_shapes']['image'])"
  # -> {'k': 3, 'w': 224, 'n': 1, 'h': 224} — the geometry the surfaces must match
# SU: decode a cached model.src (no sudo, works on the pack's gzipped copies)
python3 harness/p2b_mlir_bc_strings.py raw/p2b_model_src/granite_original_model_0.mpsgraph.gz
  # -> full string dictionary: mps-dialect op set + python call_stack provenance
  # live cache: ls ~/Library/Caches/coreai-cache/<OSBUILD>/<proc>/<ident>/*/model.aimodelx/...
gunzip -c raw/p2b_model_src/na_tiles_binary_0.hwx.gz > /tmp/h.hwx && \
  ../../../tools/vendor/coreml_to_ane_hwx/hwx_dump/hwx_parsing /tmp/h.hwx
```

## KB cross-refs

`knowledge/ane/02-private-api.md` §3.13 (compiler kitchen) + records API-117…122, API-130
(coreai-cache model.src schema, SU);
API-068 (liveInputList strides — K5 fix recipe anchor);
ledger `FAILURES.md` F-45 (trigger-assertion rule), F-50 (ktrace exclusivity +
in-process-compiler rule); `EXP-025-ane-gpu-sync/docs/P2-LANE-A.md` §7.
