# coreai-cache format — the Core AI specialization cache, decoded (2026-10-10)

Machine: Mac17,14 M5 Max, macOS 27.0.1 / 26A434. User-level, unprivileged, read-only.
Tool: `bench/coreai_cache.py` (stdlib only). Census: `coreai_cache_census.json`;
key table: `coreai_cache_keys.txt`. Record: `API-139` (+ `FORMAT-*`).

Apple documents what Core AI *does* (specialize, cache per device+OS) but not the bytes it
persists. The public route writes them user-readable; this note is the format.

## 1. Location and layout

```
~/Library/Caches/coreai-cache/<key>/
```

`<key>` is the **OS build** (`26A434`, Swift/Core AI route) or the **Python version**
(`3.12.15`, coreai-torch route). Two layouts:

```
osbuild:  26A434/<process>/<modelHash64>/<optsHash64>/{model.aimodelx|X.aimodel}/...
pyver:    3.12.15/<modelHash64>/<X>.aimodel/...
```

- `modelHash64` — lowercase 64-hex. Per **model** (175 distinct across the cache).
- `optsHash64` — UPPERcase 64-hex, osbuild layout only. A pure function of the
  `SpecializationOptions` (see §4); **model-independent**, reused across 8–10 models each.

## 2. Entry anatomy

A plan is a directory containing a `*.mpsgraphpackage`. Inside (osbuild, JIT/ANE route):

```
model.aimodelx/
  main-this.odix                     # ODIE index (opaque; not decoded)
  main-this.dbginfo                  # torch-python call stack (provenance, plain text)
  main-this-delegates/
    MPSGraph/mpsExecutable.mpsgraphpackage/
      manifest.plist                 # versioned dict; holds the compiler descriptor JSON
      original_model_0.mpsgraph      # model source, mps-dialect MLIR bytecode
      specialized_model_1.mpsgraph   # placement-specialized plan
      binary_0.llir.bundle/          # per-ANE-region LLIR bitcode (ANECompiler output)
      binary_0.hwx                   # ANE hardware task (absent on GPU-routed plans)
      resources.bin                  # weights
```

`*.delegates/` may instead hold a `BNNS/bnns.ir*` delegate (different container, no MLIR
string dictionary).

## 3. manifest.plist

Top-level `Package Version → "<7.0.63>" → {…}`. Keys:

| key | meaning |
| --- | --- |
| `Original` | filename of the source (`original_model_0.mpsgraph`) |
| `ANERegionsHash` | `{ "<arch>": "<hash>_<hash>" }` — arch-keyed plan identity |
| `GPU adapter present` | `"NO"` on this route (no GPU-compiler fallback compiled in) |
| `Binary File Resources` | `{"0": {"File Name": "binary_0.llir.bundle", "Type": 2}}` |
| `Optimized Modules` | list of strings; **[0] is the compiler descriptor JSON** |

The descriptor JSON (reached at `Optimized Modules[0]`, repeated under `Used In Cache[0]`)
carries `entryFunctionName`, `deviceDescriptor` `[0, 40, "h17c"]`, `inputShapes`, and the
full `compilationDescriptor`: `useANELLIR`, `allowedComputeDevices`, `preferredDevice`,
`aneCompilerSpatialSplitting`, `enableANEFWToFWSignal`, `enableANECHWRankPromotion`,
`enableMemrefBufferization`, ~30 flags. `deviceDescriptor[2]` is the **compiler arch**
(see EXP-028 E6).

## 4. Key derivation (measured)

| optsHash(8) | models | plans | preferredDevice | allowedComputeDevices | useANELLIR | ANE pkgs |
| --- | ---: | ---: | --- | --- | --- | ---: |
| `14371356…` | 9 | 10 | 1 | 1 | False | 0 |
| `3EED3375…` | 8 | 9 | 1,2 | 1,7 | False,True | 1 |
| `6C51FA69…` | 10 | 14 | 2 | 7 | False,True | 5 |

- `optsHash` is a function of the **compute-unit options** only (`allowedComputeDevices` /
  `preferredDevice` / `useANELLIR`), not of the model — identical hash across distinct
  models, distinct hash per options arm. `6C51FA69…` = the neuralEngine arm, matching the
  live-log capture (API-136) now fully decoded from disk. `14371356…` = cpu-only
  (`allowed` = 1). `3EED3375…` = the mixed/default arm.
- `modelHash` is per-model.
- **Arch stamp: `h17c` on all 198 decoded plans** — the cache is per-device, and every
  plan on this box carries the same compiler arch.

## 5. The mpsgraph MLIR bytecode

| file | producer | dialects | content |
| --- | --- | --- | --- |
| `original_model_0.mpsgraph` | `MLIR22.0.0git`, bytecode v6 | builtin, func, mps | the model source (op set: constant/matmul/softmax/…), one `mps.` attr |
| `specialized_model_1.mpsgraph` | same | + placement, gpu, ane, memref, arith, mpsx | placement: `main_*_ANE_region_N_0` × 13, `main_*_GPU_region_N` × 14, ~32 `mps.*` attrs, `ane_family A18`, dtype whitelist |

- Header magic `4d 4c ef 52` (`ML\xefR`) + varint version + producer string.
- `specialized_model` adds the `placement` dialect (grammar: `placement/gpu/region_call/
  stitched/memref_backed`) and the `mps.*` attribute dictionary (`mps.aneArch`,
  `mps.allowedComputeDevices`, `mps.aneEnableFWToFWSignal`, …).
- The ANE dtype whitelist error text is emitted verbatim:
  `Incompatible element type for ANE: expected fp16, f8E4M3, si8, ui8, si16, or ui16`.
- **Hybrid is normal**: the ANE-routed granite plan is 13 ANE + 14 GPU regions, not
  pure-ANE. `GPU adapter present = NO` means no GPU fallback *compiler* was packaged — it
  does **not** mean the plan is ANE-only.

## 6. Gaps (declared)

- Op **order / operand wiring** (SSA) is not printed: stock `mlir-opt` parses the container
  then fails at the private-dialect instantiation. Needs a DialectPlugin stub.
- Attribute/type binary payloads are read via the **string dictionary** only; typed values
  (strides, affine maps) survive as strings but are not structurally decoded.
- `main-this.odix` is opaque (not decoded); `dbginfo` is a plain-text stack, read as text.

## 7. Reproduce

```sh
python3 bench/coreai_cache.py --plan  <a .mpsgraphpackage dir>     # one plan -> JSON
python3 bench/coreai_cache.py --root ~/Library/Caches/coreai-cache --summary
python3 bench/coreai_cache.py --root ~/Library/Caches/coreai-cache  # full census JSON
```
