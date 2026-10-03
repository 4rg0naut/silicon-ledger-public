# The three private-API projects — read, compared, and what to take

Pulled and read in full, not summarised from READMEs:
`thebasedcapital/ane-infer`, `mechramc/Orion`, `maderix/ANE`.

```
ane-infer   1.0 MB   52 files   29 Rust · 6 ObjC · 4 Metal
Orion       4.9 MB  161 files   63 ObjC · 53 headers · 19 C · 5 Py · 2 Swift
ANE         1.6 MB   62 files   28 ObjC · 18 headers · 2 Py
```

## Licence is decisive, and it splits the three

| project | licence | what that means for us |
| --- | --- | --- |
| **maderix/ANE** | **MIT** | reuse freely, with attribution |
| **Orion** | **MIT** (Murai Labs) | reuse freely, with attribution |
| **ane-infer** | **no licence file** | **all rights reserved by default** — read it to learn the *technique*, do not copy code |

That is not a formality. `ane-infer` has the most advanced hybrid ANE+Metal decode pipeline of the
three, and we can learn from it — but **nothing may be copied out of it.** Orion and maderix are the
two we can actually build on.

---

## What each one is, honestly

### maderix/ANE — the foundation (MIT)

The project the other two are built on. It is a *research* set, not a framework, and its author says
so plainly. But its minimal example is the clearest thing in the field:

**`inmem_basic.m` is 129 lines and runs a whole ANE program end to end.** And it contains a trick worth
understanding: it **uses Core ML's compiler to *generate* the MIL and weight blob, then bypasses Core
ML entirely at runtime** through the private path.

The full lifecycle, verbatim from that file:

```
dlopen(AppleNeuralEngine)
MLModel compileModelAtURL:            → yields model.mil + weights/weight.bin
modelWithMILText:weights:optionsPlist:   (weights dict, offset @64)
inMemoryModelWithDescriptor:
hexStringIdentifier                   → name the temp dir
pre-create temp dir with model.mil + weights/
compileWithQoS: 21
loadWithQoS: 21
IOSurfaceCreate ×2 + objectWithIOSurface:
requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:
evaluateWithQoS:options:request:error:
  warmup 10, then 100 timed with mach_absolute_time
unloadWithQoS:error:
```

Also ships `sram_probe.m`, `sram_bench.m`, `ane_int8_bench.m`, and a `training/` tree including
`test_weight_reload.m`.

### Orion — the toolkit (MIT)

The only one of the three that is a *runtime* rather than an experiment. "No CoreML. No Metal. No GPU.
No cloud." Its `core/` is the useful part:

| file | lines | why we want it |
| --- | ---: | --- |
| **`mil_builder.m`** | **378** | **generates MIL text programmatically** — see below |
| `lora_adapter.m` | 224 | LoRA hot-swap without recompiling |
| `iosurface_tensor.m` | 166 | surface alloc/read/write |
| `profiler.m` | 99 | timing |
| `checkpoint.m` | | training state |
| `ane_program_cache.m` | | hash-keyed compile cache |
| `runtime.m` | 54 | thin facade |

**`mil_builder` is the find for us.** Its linear helper:

```c
NSString* orion_mil_linear(prefix, input, in_dim, out_dim, seq, weight_path, bias_path);
//  "Uses 1×1 conv (3× faster than matmul on ANE)"
```

`in_dim` and `out_dim` are exactly the parameters that set the per-core transfer size —
`bytes/core = (Cout/16) × Cin × 2`. **That is direct control over the 1 MiB boundary**, and calling it
twice at half size is the split the DMA erratum fix requires. This is the piece we did not have.

It also builds `layernorm`, `rmsnorm`, `gelu`, `silu`, `causal_attention` (explicitly decomposed, not
SDPA), multi-output programs, and the causal-mask BLOBFILE — whose 128-byte header matches what our own
knowledge base recorded independently.

Their measured results, on an M4 Max 64 GB:

```
GPT-2 124M inference:  CPU decode 283 tok/s · ANE full forward 170+ tok/s
                       "CPU decode is fastest per-token due to ANE dispatch overhead"
                       ANE prefill first call 1399 ms (83% compile), cached sub-100 ms
                       accuracy: 100% top-1 argmax, exact 5-token greedy match vs CPU
Stories110M training:  849 ms/step + 494 ms/step recompile = 1345 ms/step · 0.656 TFLOPS
                       exec() restarts needed: 0
```

**That first line matters to us.** For small models at batch 1, **the ANE is slower than the CPU** on
this machine class, because dispatch overhead dominates. Which means the case for our sub-1B
specialists on the ANE is **energy, not speed** — consistent with our own measurements (2463 mW GPU vs
6 mW ANE). We should stop expecting the ANE to be faster and start expecting it to be cheaper.

### ane-infer — the technique reference (no licence)

The most advanced of the three: a full hybrid engine, Qwen3.5 Gated DeltaNet running on the ANE, fused
mega-kernels, Metal shaders for decode. Its Rust bridge exposes something the others don't:

```
pub fn eval_procedure(&self, proc_idx: usize)   // dispatch a specific procedure by index
pub fn transpose_to_channels_first(...)         // the ANE layout conversion
pub fn build_weight_blob(weight_sets: &[&[f32]]) -> Vec<u8>
```

Worth reading for the *approach*. Not usable as code.

---

## A contradiction across all three sources — and our probe reconciles it

Three places disagree about whether ANE weights can be changed after compilation:

| source | claim |
| --- | --- |
| **maderix / Orion #7** | *"Weights are embedded into the compiled program at compile time. There is no way to update weights without recompiling."* |
| **Orion's own RESULTS.md** | *"Each subsequent training step updates weights via `orion_program_reload_weights` — unload the existing program, update the BLOBFILE on disk, reload."* |
| **our probe, this session** | `mapMutableWeightsForModel:andProcedure:mappedWeightsBuffer:size:error:`, `syncMutableWeightsForModel:andProcedure:fromOffset:withSize:error:` — **a full mutable-weights API exists on macOS 27** |
| **libane** (our KB) | patching had *zero* effect |

**These are all describable at once.** The mechanism is the **model cache keyed by hash** — which our
probe also found (`purgeCompiledModelMatchingHash:`, `compiledModelExistsMatchingHash:`). If the MIL
hash is unchanged, a reload serves the *cached compiled program with the old weights baked in*, so
overwriting the BLOBFILE changes nothing. Orion's own flow works because its cache lifecycle accounts
for that.

So the honest position is **not** "patching is impossible" and **not** "patching works". It is:

> Weights are baked at compile time. A reload only picks up new weights if the cache no longer serves
> the old program — either by changing the program's identity or by purging the cache entry. And there
> is additionally a documented **mutable-weights API** that sidesteps the question.

**That reconciles four sources that appeared to contradict each other**, and it is testable with what
we now have.

---

## The seventeen constraints — the single best artefact here

`Orion/docs/ane_constraints.md`, MIT. Each one is stated as symptom → workaround → which experiment
found it → and most are independently reproduced. The ones that will bite us:

| # | constraint | why it matters to us |
| --- | --- | --- |
| **4** | **Minimum IOSurface ~49 KB**; `[768,16]` works, seq=1 fails; ANE uses stride 16 for seq | our small specialist models will hit this immediately |
| **3, 13** | Multi-input **and** multi-output surfaces are ordered **alphabetically by MIL variable name**, not by tuple position — wrong order gives *silently* wrong data | name variables so alphabetical = intended |
| **2, 12** | Multi-input/output surfaces must be the **same allocated size**; pad all to the max | |
| **7** | Weights baked at compile time (see the reconciliation above) | |
| **8** | BLOBFILE reference offset is **`uint64(64)`**, not 0 or 128; wrong offset = silent garbage | matches `inmem_basic.m` exactly |
| **9** | `milText` must be `NSData*`, not `NSString*` | |
| **10** | **`gelu` is not a valid MIL op** — expand to the tanh approximation | |
| **17** | **`rsqrt` is not a valid MIL op** — use `pow(x, -0.5)` | |
| **15** | **Max 16 BLOBFILE weight tensors per program** — a *count* budget, not bytes. A conv **with bias costs two slots** | the binding limit on kernel fusion |
| **16** | Scalar-operand ops (`pow`, `add(scalar)`, `mul(scalar)`) drop the budget to **15**. RMSNorm inherits this via `pow(x,-0.5)`. There is **no** "mixed weight type" rule | explains a widely-misreported gotcha |
| **6** | SDPA ignores causal masks — decompose attention manually | we already had this |
| **5** | ~119 compile limit; 83% of first-call wall time is compile, so a program cache is essential | we already had this |

**Constraint 15 and 16 together are the real design constraint on our ANE work:** a program gets
16 weight slots, minus one if it contains a norm. That is a hard budget on how much you can fuse, and
it is why "just make a bigger kernel" fails.

---

## What to take from each

| from | take | because |
| --- | --- | --- |
| **maderix/ANE** | `inmem_basic.m` as the starting skeleton; the Core-ML-generates-MIL trick; `sram_probe.m` for the SRAM question | MIT, minimal, complete, and the source the others trust |
| **Orion** | **`mil_builder`** (our missing piece); the **17 constraints**; the program cache; LoRA reload | MIT, and it is the only one that generates MIL rather than consuming it |
| **ane-infer** | the *techniques*: per-procedure dispatch, channels-first transposition, blob building — **as reference only** | no licence |

## What this unlocks

**The 1 MiB DMA experiment is now buildable.** We had the hardware question and the measurement
apparatus; what we lacked was **a way to author a program with a chosen transfer size**. `mil_builder`'s
`in_dim`/`out_dim` gives exactly that, and the 17 constraints tell us every way it will fail before we
try it.

The sequence: build a linear layer at exactly 1 MiB per core → measure → build the same maths as two
halves → measure → compare against a size that is *not* a multiple, which is the control that makes the
result mean anything.

## Recommendation

**Build on maderix + Orion; read ane-infer.** Concretely: take `inmem_basic.m` as the harness, take
`mil_builder` for program generation, take `ane_constraints.md` as the rulebook, and attribute both.
Treat `ane-infer` as a paper with working code attached that we are not allowed to copy.

And revise one expectation: **for sub-1B models at batch 1 the ANE is likely slower than the CPU on
this machine.** The reason to use it is the ~400× energy difference we measured, not throughput.