# 01 — Landscape: the two doors into the Apple Neural Engine

This is the orientation document. It explains what the Apple Neural Engine (ANE) is, the two
completely different ways to get work onto it, how far each one lets you see and control, who has
already built what, and where the legal line actually sits. Everything here is cited; the confidence
of each non-obvious claim is marked inline as **(MEASURED)**, **(DOCUMENTED)**, **(INFERRED)** or
**(CLAIMED)**, and the machine-readable form of every claim is in the `## Records` block at the end.

---

## 1. The two doors

The ANE is a fixed-function matrix accelerator that has shipped in A-series chips since the A11
(2017) and in Mac chips since the M1 **(DOCUMENTED**, arXiv:2606.22283 abstract**)**. Apple exposes
it to third-party applications through exactly one public door — the model frameworks — and the
community reaches it through a second, private one.

### Door 1 — Core ML (and now Core AI), where Apple's compiler decides

You hand Apple a converted model. Apple's compiler decides what code becomes an ANE program, what
is split off to the GPU or CPU, and when it runs. You cannot ask which processor ran your model:
`MLModelConfiguration.computeUnits = .all` merely *expresses a preference*, and Core ML provides no
runtime API to query the actual device used **(DOCUMENTED**, hollance/neural-engine
`docs/running-on-ane.md` and `docs/is-model-using-ane.md`**)**.

What this buys you: it is supported, it is shippable, and it is the only route Apple will accept in
an App Store app. What it costs you: placement is a compiler decision, the graph may fall back
silently, and there is no training path at all.

On macOS 27 the official door is **Core AI**, Apple's Core ML successor announced at WWDC 2026. It
keeps the "convert once, run on ANE/GPU/CPU" idea but replaces `.mlpackage` + coremltools with a new
IR, compiler and runtime; the converter and optimization repos are open source while the compiler and
runtime remain closed, shipped as the `coreai-core` wheel and `CoreAI.framework`
**(DOCUMENTED**, `coreai-model-zoo/knowledge/coreai-overview.md`**)**.

Core AI is still a preference, not a control. Our own measurement on this machine: the published
Granite-Embedding-97M fp32 bundle compiles to **0 ANE regions** on the ANE despite
`preferredComputeUnitKind: .neuralEngine` — the zoo's own definition of "silent GPU fallback"
**(MEASURED**, `results/EXP-005-ane-residency/README.md`**)**. Re-exporting at fp16 produced 14
regions; removing three fp32 operations took it to **1 region**, at which point the ANE path was
4.00 ms with **83 mW** of GPU power against 10,390 mW for the fp32 GPU path **(MEASURED**, same
source**)**. Apple's authoring rules for Core AI list the ANE's supported dtypes as **fp16, int8,
int16** — any fp32 op creates a buffer the engine cannot execute **(DOCUMENTED**, quoted in
`EXP-005`**)**.

### Door 2 — `AppleNeuralEngine.framework`, where you write the program

`/System/Library/PrivateFrameworks/AppleNeuralEngine.framework` is the framework Core ML itself uses
to drive the engine. Its classes are not secret in shape — `nst/iOS-Runtime-Headers` publishes
headers for `_ANEClient`, `_ANEModel`, `_ANERequest`, `_ANEIOSurfaceObject`, `_ANEProgramForEvaluation`,
`_ANEDaemonConnection` and others **(DOCUMENTED**, nst/iOS-Runtime-Headers tree**)** — but Apple
documents none of them, and there is no importable SDK.

The community loads this framework at runtime with `dlopen`/`objc_msgSend` and drives the
compile → load → evaluate pipeline itself: build MIL (Machine Learning Intermediate Language)
program text, compile it in memory through `_ANEInMemoryModelDescriptor`, load the program, pass
tensors through IOSurfaces, and evaluate **(DOCUMENTED**, maderix/ANE README and
`maderix.substack.com` Part 1**)**.

We wrote our own Core ML graph into an ANE-resident one at level 1; the private route is what lets
anyone go below that. Its own honest description, from the reference paper: the direct route "is
callable from ordinary user space but remains undocumented, unsupported, and version-fragile; it is
intended for measurement, research, and on-device work, not for shipping software, where Core ML
remains the supported path" **(DOCUMENTED**, arXiv:2606.22283**)**.

Concretely, what the private door gives you that the public one does not:

| | Core ML / Core AI | `AppleNeuralEngine.framework` |
|---|---|---|
| Who picks the ops that run on ANE | Apple's compiler | you |
| Can you ask what ran where | no API | you dispatched it, you know |
| Weights as compile-time constants or runtime inputs | compiler's choice | you choose (baked `const()` vs packed spatial input) |
| Multiple functions in one program | not exposed | yes, addressed by `procedureIndex` |
| Training (backward pass, optimizer) | no API exists | demonstrated |
| Supported for shipping | yes | no |

---

## 2. The ladder of access levels

Four levels, each giving more control and less support. The useful mental model is *who decides what
the hardware executes* and *how much you can see*.

### Level 1 — the framework: Apple decides

Core ML (or Core AI) plus `MLModelConfiguration`. You choose a preference among CPU/GPU/ANE and
nothing else. Placement is the compiler's decision, and a graph that "looks like" it uses the ANE
may be entirely on the GPU **(DOCUMENTED**, hollance `docs/running-on-ane.md`; **MEASURED**, our
`EXP-005`, fp32 bundle at 0 ANE regions**)**.

### Level 2 — inspection: nobody decides differently, but you can finally see

This level does not change what executes; it changes what you can *know*. It matters because it is
where you diagnose level-1 failures, and it needs no private dispatch.

- **`MLComputePlan`** — a public Core ML API that reports, per operation, which compute devices
  support it. `ane-probe` uses it to build minimal one-op Core ML models and produce an op-by-device
  support matrix per chip/OS/coremltools version **(DOCUMENTED**, `repos/ane-probe/README.md`**)**.
- **`anemll-profile`** — combines `MLComputePlan` placement with Espresso `[CostModelFeature]` logs
  captured by forking `/usr/bin/log stream`, parses `Unsupported op` compiler messages for the
  fallback reason, and runs real predictions for measured throughput **(DOCUMENTED**,
  `repos/anemll-profile/README.md`**)**.
- **`enginemon`** (ours) — reads Apple's **IOReport** counters from a fully unprivileged process and
  reports ANE bytes moved and ANE interrupt counts, with no root and no entitlement
  **(DOCUMENTED/DOCUMENTED-our-own**, `tools/enginemon/README.md`**)**.
- **Debugger symbols** — a symbolic breakpoint on `-[_ANEModel program]` tells you Core ML is using
  the ANE; Espresso engine names (`Espresso::ANERuntimeEngine`, `Espresso::MPSEngine`,
  `Espresso::BNNSEngine`) tell you which engine is on the stack **(DOCUMENTED**, hollance
  `docs/is-model-using-ane.md`**)**.

Two traps at this level, both measured by us and both capable of producing a confident wrong answer:

- On M4, IOReport's `Energy Model → ANE` channel is **frozen** at a constant and reads 0 even under
  a workload that provably uses the ANE. Reporting its zero as "the ANE was not used" is a fabricated
  negative. The usable signals are `AMC Stats → ANE DCS RD` (bytes) and the second-level `ane 0`
  interrupt count **(MEASURED**, `tools/enginemon/README.md`**)**.
- `xctrace`'s `ane-hw-intervals` is **blind to Core AI graphs** — 0 intervals recorded for a Core AI
  run while a Core ML control in the same session logged 1310 **(MEASURED**, same source**)**.

### Level 3 — the private framework: you write the program

This is where the community actually lives. You construct MIL text, compile it with
`_ANEInMemoryModelDescriptor` (or `compileModel:` on a model directory), load it onto the engine, and
evaluate it with IOSurface inputs and outputs. The canonical sequence, from maderix's Part 1
**(DOCUMENTED**, `maderix.substack.com` Part 1**)**:

```objc
id client = [_ANEClient sharedConnection];
id model  = [_ANEModel modelAtURL:compiledURL key:@"mykey"];
[client compileModel:model options:@{ @"kANEFModelType": @"kANEFModelMIL",
                                      @"kANEFNetPlistFilenameKey": @"model.mil" }
                 qos:21 error:&err];
[client loadModel:model options:@{} qos:21 error:&err];   // programHandle assigned
id req = [_ANERequest requestWithInputs:@[wA, wB] inputIndices:@[@0,@1]
                                outputs:@[wOut] outputIndices:@[@0]
                          weightsBuffer:nil perfStats:nil procedureIndex:@0];
[client evaluateWithModel:model options:@{} request:req qos:21 error:&err];
```

And the in-memory variant, which is what makes training possible because it avoids a filesystem
round-trip per weight update **(DOCUMENTED**, same source**)**:

```objc
id desc  = [_ANEInMemoryModelDescriptor modelWithMILText:milData   // NSData, not NSString
                                                 weights:weightDict]; // NSDictionary, not NSData
id model = [_ANEInMemoryModel inMemoryModelWithDescriptor:desc];
[model compileWithQoS:21 options:@{} error:&err];
[model loadWithQoS:21 options:@{} error:&err];
[model evaluateWithQoS:21 options:@{} request:req error:&err];
```

Note the two silent failure modes maderix documents: `milText` must be `NSData` holding UTF-8 bytes
(an `NSString` fails silently), and `weights` must be an `NSDictionary` mapping names to blobs, not a
single buffer **(DOCUMENTED**, same source**)**.

A newer discovery sits at the edge of this level: `_ANEClient` also exposes **multi-procedure
programs** (several MIL functions in one compiled program, dispatched by `procedureIndex`, with
`inputIndex`/`outputIndex` equal to the procedure ID), and `do`-prefixed direct methods such as
`doEvaluateDirectWithModel:` that bypass the ANE daemon XPC path — 106 µs against 117 µs for the
daemon path on M5 **(MEASURED**, ane-infer `docs/ane-internals.md`**)**.

### Level 4 — program descriptors and register values

Below MIL there is the compiled artefact and, below that, the registers.

- The compiler emits an **hwx** (or **E5**) program — a Mach-O-like file whose ops begin at offset
  `0x4000` — and `tinygrad` maintains a register map (`aneregs`) of the fields each op uses:
  `Common.InDim.*`, `KernelDMASrc`, `TileDMASrc`, `L2`, `NE`, `TileDMADst`, with all tensor strides
  required to be multiples of `0x40` bytes **(DOCUMENTED**, tinygrad `extra/accel/ane` README at
  commit `d0e7520`**)**.
- Real level-4 work is being done today: the M3 1 MiB DMA erratum was diagnosed by sweeping and
  hex-diffing live register-file values such as `TD+0x004`, `TD+0x078` (core base addresses) and
  `TD+0x134` (`Common.Cin`) across configurations **(DOCUMENTED** in method, **MEASURED** in result:
  the post reports 2.4× Llama 3.2 1B throughput recovery, eiln.github.io**)**.

### Where the frontier is

The frontier is level 3 with frequent excursions into level 4, and occasionally level 2 as the
instrument. Everything that is new in this field — ANE training, batched prefill, program chaining,
multi-procedure dispatch, the DMA erratum — is a level-3 or level-4 result **(INFERRED**, from the
prior-art survey below**)**. Level 1 work is not where the frontier is because the interesting
knobs are not reachable from there.

---

## 3. Prior art

Stars, last-push dates, languages and licenses were read from the GitHub API on **2026-09-23**.
"Last activity" is `pushed_at`, which is the last push to any branch, not the last release.

| Project | What it does | Language | License | Stars | Last activity | Train or infer | How usable, honestly |
|---|---|---|---|---|---|---|---|
| [maderix/ANE](https://github.com/maderix/ANE) | Backpropagation on the ANE via reverse-engineered `_ANEClient`/`_ANECompiler`/`_ANEInMemoryModelDescriptor`; also the standard reference for the private API route | Objective-C | MIT | 7,261 | 2026-03-10 | **Trains** | Research proof of concept that genuinely ran (109M at 91 ms/step, Qwen3-0.6B at 412 ms/step). Author states it is "not a maintained framework or library" and that feature requests will go unaddressed |
| [johnmai-dev/ANE-LM](https://github.com/johnmai-dev/ANE-LM) | LLM inference (Qwen3, Qwen3.5 dense) on ANE via the private framework | C++ | MIT | 143 | 2026-03-04 | Infers | The upstream most other projects fork. Builds with CMake into a working generate/chat CLI. Complete for what it covers; stale since March 2026 |
| [AmiraniLabs/libane](https://github.com/AmiraniLabs/libane) | Low-level ANE runtime with a Graph IR, automatic op fusion, a stable C ABI and Python/Swift bindings | C++ | Apache-2.0 | 7 | 2026-09-22 | Infers (a compute library) | The most active project in the cluster; published on PyPI with CI, tests and 18 worked examples. Explicitly "for research use… not production deployment" |
| [thebasedcapital/ane-infer](https://github.com/thebasedcapital/ane-infer) | Hybrid ANE + Metal GPU + CPU LLM engine (Qwen3.5 DeltaNet), Rust + Obj-C + Metal | Rust | **none declared** | 28 | 2026-03-05 | Infers | Broadest reverse-engineering write-up of `_ANEClient`/chaining internals. README itself says "not production-ready" and "not faster than llama.cpp (yet)" |
| [anemll/anemll](https://github.com/anemll/anemll) | Full pipeline: HuggingFace → Core ML conversion → ANE inference, plus Swift reference CLI and iOS/macOS/visionOS apps and a profiler | Python (+Swift) | **none declared** | 1,677 | 2026-09-18 | Infers | The most complete end-to-end product in the list: v0.3.5 beta, pre-converted models on Hugging Face, a TestFlight app, and published eval numbers. Still a beta; its own note says quantization quality needs work |
| [skyfallsin/ane.cpp](https://github.com/skyfallsin/ane.cpp) | Fork of ANE-LM pushed toward 4B–9B dense Qwen, with fused kernels, W-lane batching and a persistent compile cache | C++ | MIT | 5 | 2026-04-25 | Infers | Real, measured 4B/9B results and an unusually honest companion *field guide* documenting dead ends. Low stars but high information density |
| [royisme/qwen-ane-llm](https://github.com/royisme/qwen-ane-llm) | ANE-LM wrapped in an OpenAI-compatible FastAPI server with streaming and tool calls | C++ + Python | MIT | 1 | 2026-03-04 | Infers | A thin, functional wrapper. Useful as an integration example, not as an ANE reference |
| [shershah1024/lfm2.5-vl-ane](https://github.com/shershah1024/lfm2.5-vl-ane) | LFM2.5-VL-450M vision-language model fully on ANE, as a native macOS app plus REST endpoint | Swift | MIT code + LFM Open License for the model bundle | 2 | 2026-06-16 | Infers | Working app and CLI with measured performance (prefill ~85 ms, decode ~57 tok/s, 1–2 W) and 100%/92% ANE residency. Note it is a **Core ML** project, not a private-API one |
| [AtomGradient/hybird-batch-prefill-on-ane](https://github.com/AtomGradient/hybird-batch-prefill-on-ane) | Batched ANE prefill (32 tokens per dispatch) benchmarked against MLX GPU decode, with a paper | C++ (+Python) | MIT | 2 | 2026-03-18 | Infers | A benchmark and paper rather than a product, but the measurement (11.3× over sequential dispatch, GPU at 0.22 W during ANE prefill) is well documented and reproducible |
| [tinygrad](https://github.com/tinygrad/tinygrad) `extra/accel/ane` | geohot's early ANE reverse engineering: hwx program parsing, the `aneregs` register map, IOKit/entitlement notes | Python + Obj-C | MIT (whole repo) | 33,642 (whole repo) | 2026-09-23 (whole repo) | Neither — a driver/RE effort | **Effectively abandoned.** The `extra/accel/ane` directory is absent from `master`; it exists at commit `d0e7520`, and its README is explicit that "we don't have all the details worked out yet". Historically important, not a runtime |

Two licence observations, both verified directly on 2026-09-23: **`anemll/anemll` has no `LICENSE`
file at its repository root**, and **`thebasedcapital/ane-infer` has no `LICENSE` file either**;
GitHub's API reports no detected licence for both. For a corpus we intend to share, that matters —
unlicensed source can be read and cited, but its text cannot be redistributed
**(DOCUMENTED**, GitHub API `license` field and the raw `LICENSE` path returning 404**)**.

Reading the table as a whole:

- **One project trains; every other project infers.** Training on the ANE is demonstrated, not
  productised.
- **The fork tree is shallow.** ANE-LM is the ancestor of ane.cpp, qwen-ane-llm and (by the
  authors' own attribution) the batch-prefill work. maderix is cited as the origin by nearly
  everyone, including ane-infer, ANE-LM, ane.cpp and the batch-prefill repo.
- **Two flavours of project are mixed here.** The private-API cluster (maderix, ANE-LM, libane,
  ane-infer, ane.cpp, qwen-ane-llm, batch-prefill) drives the engine directly. ANEMLL and
  lfm2.5-vl-ane go through Core ML. Both are legitimate answers to "how do I get on the ANE", and
  comparing them is instructive: ANEMLL gets reliability and shippability, the private cluster gets
  control and visibility.
- **Stars do not track usefulness.** The two most informative private-API documents in the list —
  libane's and ane.cpp's — have 7 and 5 stars respectively; the 33,642-star tinygrad repository
  contains an ANE backend that no longer exists on its main branch.

---

## 4. The legal position

This is the section where people are least careful, so it is stated plainly:

> **Using a private framework is unsupported, not illegal.** No court has ruled that
> reverse-engineering the ANE is unlawful, and the standard authorities point the other way. What you
> definitely lose is Apple's support and any chance of App Store distribution.

### The interoperability argument

**Sega Enterprises Ltd. v. Accolade, Inc., 977 F.2d 1510 (9th Cir. 1992)** held that intermediate
copying of object code during reverse engineering, undertaken to discover the unprotected functional
requirements for interoperability, is **fair use**. The Copyright Office's own summary records the
reasoning: the copying was "legitimate, essentially non-exploitative"; the defendant "did not usurp
plaintiff's market" but produced its own independently creative work; and, critically, "without a
fair use exception for disassembling object code, the owner of the work would have a de facto
monopoly over the functional aspects of the work" **(DOCUMENTED**, copyright.gov Fair Use Index
summary**)**. Applied to the ANE, the analogous argument is: reading `AppleNeuralEngine.framework`
to learn the interface for driving hardware you own is exactly the Accolade situation.

**17 U.S.C. § 1201(f)** is the statutory counterpart. Its reverse-engineering exception permits
circumventing an access control "for the sole purpose of identifying and analyzing those elements of
the program that are necessary to achieve interoperability of an independently created computer
program with other programs", where those elements were not previously readily available — and it
permits developing and sharing the means to do so, to the extent the acts do not themselves infringe
**(DOCUMENTED**, law.cornell.edu, 17 U.S.C. § 1201(f)(1)–(3)**)**. The statutory definition of
"interoperability" is "the ability of computer programs to exchange information, and of such programs
mutually to use the information which has been exchanged" — a definition that reads awkwardly when
applied to a hardware accelerator rather than two programs, which is one reason the analogy is
argued rather than settled **(INFERRED)**.

### The practical App Store restriction

The community's original reference states the practical position bluntly: "There currently is no
public framework for programming the ANE. There are several private, undocumented frameworks but
obviously we cannot use them as Apple rejects apps that use private frameworks"
**(CLAIMED**, hollance/neural-engine `docs/programming-ane.md`; note this is the author's assertion
about App Review behaviour, not an Apple document**)**.

Apple's actual rule is written down: **App Store Review Guideline 2.5.1 — "Apps may only use public
APIs and must run on the currently shipping OS"** **(DOCUMENTED**,
developer.apple.com/app-store/review/guidelines/**)**. A private framework is by definition not a
public API, so an app that links or `dlopen`s `AppleNeuralEngine.framework` is out of policy. Linking
against it is also separately impossible for a shippable app: there is no public SDK stub to link
against, which is why every project in the table resolves symbols at runtime with `dlopen` and
`objc_msgSend`.

So the operating position is:

- **On your own machine, for research and measurement**: the interoperability cases are the
  argument of record, and there is no reported enforcement action against any of these projects.
- **In a distributed app**: dead on arrival, not because a court said so but because of Guideline
  2.5.1 and the absence of a public interface.
- **Redistribution of Apple's code or headers** is a separate question and was not attempted by any
  project surveyed here; they publish their own code, not Apple's.

### Two honesty notes

First, **I could not verify that any of the ten listed projects cites Sega v. Accolade or §1201(f) by
name.** I checked the READMEs and, where reachable, the docs directories of all ten on 2026-09-23 and
found no such citation; the repositories rely on the argument implicitly rather than citing it
**(INFERRED**, from reading those files**)**. The interoperability framing in this section is
therefore the general legal basis for this class of work, not a quotation from the projects.

Second, at least one project's guidance is a different and more aggressive posture than
interoperability reverse engineering: tinygrad's ANE README documents **patching the `amfid` daemon
in memory to disable the entitlement check** so that unsigned binaries can reach the engine, noting
it verified this on macOS 12.4 **(DOCUMENTED**, tinygrad `extra/accel/ane` README**)**. Patching a
system security daemon is not the same act as reading an interface, and the fair-use and §1201(f)
arguments should not be assumed to cover it. Nothing in this knowledge base asks us to do that;
levels 3 and 4 on a normal user account work without it.

---

## 5. Why the private door wins

Four concrete capability differences, each with a source. The honest counterweight is at the end.

### 5.1 You control the program, so you can control what is fused and what is dispatched

Apple's compiler decides fusion at the public door. At the private door you decide, and it is worth
a lot. ane-infer fused an entire FFN — gate projection conv → sigmoid → mul → up-projection conv →
mul → down-projection conv, **8 operations in one dispatch** — and measured **3.6 TFLOPS** against
**1.1 TFLOPS** for the same work dispatched op-by-op **(MEASURED**, ane-infer
`docs/ane-internals.md` / README**)**. maderix's Part 2 found the same shape of result from the other
direction: a single matmul uses only about 30% of the engine's capacity, and deep graphs of 16–64
chained ops are what approach peak **(MEASURED**, `maderix.substack.com` Part 2**)**. At batch scale
the effect is larger still: batching 32 tokens per dispatch instead of one raised ANE prefill
throughput **11.3×** on Qwen3.5-0.8B and **7.3×** on Qwen3.5-2B **(MEASURED**, AtomGradient README
and paper**)**.

### 5.2 The overhead tax disappears, which matters most exactly where the ANE is used

For small operations Core ML adds **2–4× overhead** over direct `_ANEClient` dispatch; the gap closes
only when the compute time dominates **(MEASURED**, `maderix.substack.com` Part 2**)**. LLM token
decode is the regime made of small operations. The private route also exposes a direct evaluation
path that skips the ANE daemon's XPC hop — 106 µs against 117 µs per eval on M5, about 10%
**(MEASURED**, ane-infer `docs/ane-internals.md`**)** — and one independent fit of dispatch cost on
M3 Max is `latency ≈ 119 µs + bytes / 78 GB/s`, which tells you the fixed cost is real and large
relative to a single matvec **(MEASURED**, skyfallsin field guide, quoted in the ane.cpp README**)**.

### 5.3 Training exists, and only here

There is no Core ML training API. Not "an awkward one" — none. Training a transformer on the engine
required reverse-engineering `_ANEClient`/`_ANECompiler` and building a dynamic-weight pipeline where
weights are passed as runtime data rather than baked as `const()` tensors
**(DOCUMENTED**, maderix/ANE README; **MEASURED**, the results: Stories110M 109M params at 91 ms/step,
Qwen3-0.6B 596M at 412 ms/step, loss 9.11 → 1.02 over 50K steps**)**. Whether it is *useful* is a
separate question answered below.

### 5.4 Visibility — you can see the machine, and measure it honestly

At level 1 you cannot ask which processor ran your model **(DOCUMENTED**, hollance
`docs/is-model-using-ane.md`**)**. At levels 2–4 you can: breakpoints on `-[_ANEModel program]` and
the Espresso engine symbols, `MLComputePlan` placement, Espresso cost-model logs, and unprivileged
IOReport counters for ANE bytes and interrupts **(DOCUMENTED**, hollance, `ane-probe`,
`anemll-profile`, `enginemon`, as cited in §2**)**. This is not a nicety. Our own EXP-005 is the
proof: the whole finding — that a "preferred compute unit: Neural Engine" graph was running entirely
on the GPU — depended on having both `MLComputePlan` region counts and IOReport byte counters. A
level-1-only workflow would have shipped the wrong claim **(MEASURED**, our own**)**.

Speed, separately, is *not* automatically a win. Measured outcomes are workload-shaped:

- ANE prefill drew **0.22 W of GPU power**, a **282×** reduction against 62.05 W for GPU prefill, and
  beat the GPU on short prompts for the 0.8B model (148.7 vs 138.2 tok/s) while losing badly on long
  prompts (268.0 vs 736.2) **(MEASURED**, AtomGradient README**)**.
- LFM2.5-VL-450M ran with **100% vision residency** and **~92% of language cost** on the ANE at
  **1–2 W** against 8–15 W on the GPU **(MEASURED**, lfm2.5-vl-ane README**)**.
- ane.cpp reported Qwen3.5-4B int8 at 30.08 tok/s prompt and 11.66 tok/s generate on M3 Max — real,
  but "still modest" in its own words **(MEASURED**, ane.cpp README**)**.
- The reference paper's own verdict on decode is that it is bandwidth- and dispatch-bound, with GPU
  at batch 16 **2.7× faster and 4.6× more energy-efficient** **(MEASURED**, arXiv:2606.22283,
  as distilled in `coreai-model-zoo/knowledge/ane-silicon-reference.md`**)** — while our own
  embedder measurement on M4 found the ANE path slightly *faster* and using ~125× less GPU power
  **(MEASURED**, our own `EXP-005`**)**. These are different workloads and they do not contradict each
  other; see the contested records for both positions.

And the costs, stated without hedging:

- **Private-API code breaks on macOS updates.** maderix: the APIs "may change or break with any macOS
  update"; ane-infer: "Private API usage means it breaks with macOS updates"
  **(CLAIMED**, both READMEs**)**.
- **Compile is a resource leak.** maderix hit a ceiling at roughly **119 ANE compiles per process**
  and worked around it with an `exec()` restart; the reference paper puts the load-time ceiling at
  ~**128 programs per process** with **127 in-flight requests per program** **(MEASURED/
  DOCUMENTED**, maderix README; `ane-silicon-reference.md`**)**.
- **Training is immature.** The author's own numbers: **~5–9% utilization of peak**, many elementwise
  ops falling back to CPU, and "this does not replace GPU training for anything beyond small research
  models today" **(CLAIMED**, maderix README**)**. Apple's sanctioned route for on-device training
  remains MLX, not the ANE **(INFERRED**, from the WWDC26 MLX sessions recorded in our
  `results/RESEARCH-SWEEP.md`**)**.

**The summary a newcomer should leave with:** the ANE is reachable two ways; the public way is the
shippable one and it hides everything; the private way is the one where the field's knowledge is
being produced, and it is used for measurement, research and tooling rather than for products. Every
project in §3 that has produced a genuinely new fact about the hardware did it at level 3 or 4.

---

## Records

```jsonl
{"id":"LANDSCAPE-001","claim":"The Apple Neural Engine is a fixed-function matrix accelerator shipped in A-series chips since the A11 and in Mac chips since the M1.","kind":"fact","confidence":"documented","source":"https://arxiv.org/abs/2606.22283","source_type":"primary","retrieved":"2026-09-23","topic":["hardware","history"],"entities":["ANE","A11","M1"],"contested":false}
{"id":"LANDSCAPE-002","claim":"Apple exposes the ANE to third-party applications only through the Core ML model framework.","kind":"fact","confidence":"documented","source":"https://arxiv.org/abs/2606.22283","source_type":"primary","retrieved":"2026-09-23","topic":["access","framework"],"entities":["ANE","Core ML"],"contested":false}
{"id":"LANDSCAPE-003","claim":"A second private route to the ANE exists through AppleNeuralEngine.framework, which the community loads at runtime with dlopen and objc_msgSend rather than linking against an SDK.","kind":"fact","confidence":"documented","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["access","private-api"],"entities":["AppleNeuralEngine.framework","maderix/ANE"],"contested":false}
{"id":"LANDSCAPE-004","claim":"Setting MLModelConfiguration.computeUnits to .all only expresses a preference and does not guarantee that Core ML runs the model on the ANE.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/running-on-ane.md","source_type":"primary","retrieved":"2026-09-23","topic":["coreml","placement"],"entities":["Core ML","MLModelConfiguration"],"contested":false}
{"id":"LANDSCAPE-005","claim":"Core ML provides no API to ask at runtime which processor executed a model.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"primary","retrieved":"2026-09-23","topic":["coreml","visibility"],"entities":["Core ML"],"contested":false}
{"id":"LANDSCAPE-006","claim":"With the private route the caller supplies the compiled program, so op fusion, dispatch count, weight layout and I/O buffers are all under the caller's control.","kind":"fact","confidence":"inferred","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["access","control"],"entities":["AppleNeuralEngine.framework"],"contested":false}
{"id":"LANDSCAPE-007","claim":"The ANE direct route is callable from ordinary user space but remains undocumented, unsupported and version-fragile, and is intended for measurement and research rather than shipping software.","kind":"fact","confidence":"documented","source":"https://arxiv.org/abs/2606.22283","source_type":"primary","retrieved":"2026-09-23","topic":["access","risk"],"entities":["ANE"],"contested":false}
{"id":"LANDSCAPE-008","claim":"Core AI supports only fp16, int8 and int16 tensor types for ANE execution, and any fp32 op creates a buffer the Neural Engine cannot execute and hence falls back to GPU or CPU.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["core-ai","precision","placement"],"entities":["Core AI","ANE","fp32","fp16"],"split":"holdout","contested":false}
{"id":"LANDSCAPE-009","claim":"The published Granite-Embedding-97M fp32 bundle compiled to zero ANE regions on macOS 27 despite being requested with the Neural Engine compute unit.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["core-ai","placement","silent-fallback"],"entities":["Core AI","Granite-Embedding-97M","M4"],"evidence":"0 ANE regions for the fp32 published bundle","caveat":"one specific published bundle on an M4 under macOS 27.0","contested":false}
{"id":"LANDSCAPE-010","claim":"Re-exporting that same embedding graph at fp16 produced 14 ANE regions, and removing three fp32 operations brought it to a single ANE region.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["core-ai","placement","precision"],"entities":["Core AI","Granite-Embedding-97M","M4"],"evidence":"fp32 0 regions; fp16 14 regions; fp16 v3 1 region","caveat":"region count is a shape metric and was later corrected for a double-counting bug (F-27)","contested":false}
{"id":"LANDSCAPE-011","claim":"Core AI is Apple's Core ML successor announced at WWDC 2026, replacing the mlpackage and coremltools stack with a new IR, compiler and runtime whose compiler and runtime remain closed source.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/coreai-overview.md","source_type":"secondary","retrieved":"2026-09-23","topic":["core-ai","toolchain"],"entities":["Core AI","Core ML","coreai-torch","CoreAI.framework"],"contested":false}
{"id":"LANDSCAPE-012","claim":"Level 1 of ANE access is the framework route, in which only Apple's compiler decides which operations become ANE programs.","kind":"definition","confidence":"inferred","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/running-on-ane.md","source_type":"primary","retrieved":"2026-09-23","topic":["access-levels"],"entities":["Core ML","Core AI","ANE"],"contested":false}
{"id":"LANDSCAPE-013","claim":"Level 2 of ANE access is inspection, meaning public or side-channel measurement of placement without dispatching private programs.","kind":"definition","confidence":"inferred","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["access-levels","visibility"],"entities":["ANE","MLComputePlan"],"contested":false}
{"id":"LANDSCAPE-014","claim":"MLComputePlan is a public Core ML API that reports which compute devices support each operation of a compiled model.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["coreml","visibility"],"entities":["MLComputePlan","Core ML"],"contested":false}
{"id":"LANDSCAPE-015","claim":"ane-probe builds minimal one-operation Core ML models and queries MLComputePlan to produce an ANE operation-support matrix per chip, OS and coremltools version.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["tooling","visibility","op-support"],"entities":["ane-probe","MLComputePlan"],"contested":false}
{"id":"LANDSCAPE-016","claim":"anemll-profile combines MLComputePlan placement with Espresso CostModelFeature logs captured by forking /usr/bin/log stream, plus real predictions, to report ANE graph interruptions and per-op fallback reasons.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/anemll-profile/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["tooling","profiling","visibility"],"entities":["anemll-profile","MLComputePlan","Espresso"],"split":"holdout","contested":false}
{"id":"LANDSCAPE-017","claim":"enginemon reads Apple's private IOReport counters from an unprivileged process and reports ANE memory traffic and ANE interrupt counts without root or an entitlement.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["tooling","measurement","visibility"],"entities":["enginemon","IOReport","M4"],"caveat":"verified on euid 501 under macOS 27.0 on M4","contested":false}
{"id":"LANDSCAPE-018","claim":"On M4 the IOReport Energy Model ANE channel is frozen at a constant value and reports zero even under a workload that provably uses the Neural Engine.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["measurement","gotcha","power"],"entities":["IOReport","M4","ANE"],"evidence":"channel returns the constant 10945781 regardless of load; reads 0 under a Core ML compute_units=ALL workload","caveat":"observed on M4; other SoCs may expose a live channel","contested":false}
{"id":"LANDSCAPE-019","claim":"The usable unprivileged ANE-activity signals on M4 are the AMC Stats ANE DCS RD byte counter and the second-level ane 0 interrupt count.","kind":"procedure","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["measurement","tooling"],"entities":["IOReport","M4","ANE"],"evidence":"idle 0 B and 0 interrupts versus 128-171 GB and 24538-37368 interrupts under a known-ANE Core ML workload","caveat":"channel availability is SoC and OS specific","contested":false}
{"id":"LANDSCAPE-020","claim":"xctrace's ane-hw-intervals tracepoint recorded zero intervals for a Core AI graph while a Core ML control run in the same session logged 1310.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["measurement","gotcha","tooling"],"entities":["xctrace","Core AI","Core ML","ANE"],"caveat":"measured in one session on M4 under macOS 27.0","contested":false}
{"id":"LANDSCAPE-021","claim":"Level 3 of ANE access is the private framework API surface, where the caller assembles MIL program text and drives compile, load and evaluate itself.","kind":"definition","confidence":"inferred","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["access-levels","private-api"],"entities":["_ANEClient","MIL","ANE"],"contested":false}
{"id":"LANDSCAPE-022","claim":"Level 4 of ANE access is raw program descriptors and register values, namely the compiled hwx or E5 program and the per-op register map.","kind":"definition","confidence":"inferred","source":"https://raw.githubusercontent.com/tinygrad/tinygrad/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["access-levels","format"],"entities":["hwx","tinygrad","ANE"],"contested":false}
{"id":"LANDSCAPE-023","claim":"tinygrad maintains an aneregs register map documenting the register fields used by each ANE op, including Header, KernelDMASrc, Common, TileDMASrc, L2, NE and TileDMADst.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/tinygrad/tinygrad/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["format","registers"],"entities":["tinygrad","aneregs","ANE"],"split":"holdout","contested":false}
{"id":"LANDSCAPE-024","claim":"In an hwx ANE program the ops begin at offset 0x4000 of a Mach-O-like file, and all tensor strides must be multiples of 0x40 bytes.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/tinygrad/tinygrad/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["format","register","alignment"],"entities":["hwx","tinygrad"],"caveat":"as of macOS 12.4-era reverse engineering; not re-verified on newer compilers","contested":false}
{"id":"LANDSCAPE-025","claim":"The community's frontier work on the ANE happens at access level 3 and level 4, not at the framework level.","kind":"fact","confidence":"inferred","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["access-levels","field-state"],"entities":["ANE"],"evidence":"training, batched prefill, program chaining, multi-procedure dispatch and the DMA erratum are all level-3 or level-4 results","split":"holdout","contested":false}
{"id":"LANDSCAPE-026","claim":"The M3 ANE DMA bandwidth erratum was diagnosed by sweeping and hex-diffing live ANE register-file fields such as TD+0x004 and TD+0x078 across configurations.","kind":"measurement","confidence":"documented","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["registers","dma","method"],"entities":["ANE","M3"],"evidence":"register diffs shown for D=2044, 2048 and 2052 while only address and size fields changed","contested":false}
{"id":"LANDSCAPE-027","claim":"maderix/ANE trains transformer models on the ANE via reverse-engineered _ANEClient and _ANECompiler APIs, and reached 91 ms per step for a 109M parameter model and 412 ms per step for Qwen3-0.6B on an M4.","kind":"measurement","confidence":"measured","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","training"],"entities":["maderix/ANE","Objective-C","MIT","M4"],"evidence":"7261 stars, last pushed 2026-03-10, MIT licensed, Objective-C","caveat":"the author describes it as a research proof of concept, not a maintained framework","contested":false}
{"id":"LANDSCAPE-028","claim":"johnmai-dev/ANE-LM is the upstream LLM inference project on the ANE that most other private-API projects fork, supports Qwen3 and Qwen3.5 dense models, and has not been pushed since 2026-03-04.","kind":"fact","confidence":"documented","source":"https://github.com/johnmai-dev/ANE-LM","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","inference"],"entities":["ANE-LM","Qwen3","C++","MIT"],"evidence":"143 stars, C++, MIT, last pushed 2026-03-04","contested":false}
{"id":"LANDSCAPE-029","claim":"AmiraniLabs/libane exposes a Graph IR with automatic op fusion and a stable C ABI plus Python and Swift bindings for direct ANE dispatch, and is the most recently active project in the private-API cluster.","kind":"fact","confidence":"documented","source":"https://github.com/AmiraniLabs/libane","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","runtime"],"entities":["libane","C++","Apache-2.0"],"evidence":"7 stars, Apache-2.0, last pushed 2026-09-22, published on PyPI","caveat":"the README states it is for research use and not production deployment","contested":false}
{"id":"LANDSCAPE-030","claim":"thebasedcapital/ane-infer is a hybrid ANE plus Metal GPU plus CPU LLM inference engine written in Rust that documents ANE chaining internals, and it declares no license.","kind":"fact","confidence":"documented","source":"https://github.com/thebasedcapital/ane-infer","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","inference","licensing"],"entities":["ane-infer","Rust","Qwen3.5","Metal"],"evidence":"28 stars, last pushed 2026-03-05, no LICENSE file at the repository root on 2026-09-23","caveat":"the README itself states it is not production-ready and not yet faster than llama.cpp","contested":false}
{"id":"LANDSCAPE-031","claim":"anemll/anemll provides the most complete end-to-end ANE pipeline in the field, covering HuggingFace to Core ML conversion, inference, a Swift reference CLI and published sample applications, and it declares no license.","kind":"fact","confidence":"documented","source":"https://github.com/anemll/anemll","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","inference","licensing"],"entities":["ANEMLL","Core ML","Python","Swift"],"evidence":"1677 stars, last pushed 2026-09-18, version 0.3.5 beta, no LICENSE file at the repository root on 2026-09-23","split":"holdout","caveat":"it is a Core ML project rather than a private-API one","contested":false}
{"id":"LANDSCAPE-032","claim":"skyfallsin/ane.cpp is a fork of ANE-LM that runs dense Qwen models up to about 4B parameters on the ANE and reports 30.08 tokens per second prompt throughput and 11.66 tokens per second generation for Qwen3.5-4B in int8 on M3 Max.","kind":"measurement","confidence":"measured","source":"https://github.com/skyfallsin/ane.cpp","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","inference","performance"],"entities":["ane.cpp","Qwen3.5-4B","M3 Max","C++","MIT"],"evidence":"5 stars, MIT, last pushed 2026-04-25; warmed 5-run medians at 500 generated tokens","caveat":"hardware- and setup-specific per the project's own statement","contested":false}
{"id":"LANDSCAPE-033","claim":"royisme/qwen-ane-llm wraps the ANE-LM runtime in an OpenAI-compatible REST server with streaming and tool calls, and has one star and no push since 2026-03-04.","kind":"fact","confidence":"documented","source":"https://github.com/royisme/qwen-ane-llm","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","inference","integration"],"entities":["qwen-ane-llm","C++","Python","MIT"],"evidence":"1 star, MIT, last pushed 2026-03-04","contested":false}
{"id":"LANDSCAPE-034","claim":"shershah1024/lfm2.5-vl-ane runs the LFM2.5-VL-450M vision-language model entirely on the ANE at 100 percent vision residency and about 92 percent of language cost, with prefill around 85 ms, decode around 57 tokens per second and 1-2 W against 8-15 W on the GPU.","kind":"measurement","confidence":"measured","source":"https://github.com/shershah1024/lfm2.5-vl-ane","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","inference","power"],"entities":["LFM2.5-VL-450M","Swift","Core ML","ANE"],"evidence":"2 stars, last pushed 2026-06-16; code MIT, model bundle under the LFM Open License v1.0","caveat":"it is a Core ML port, and RMSNorm reductions are deliberately kept in fp32","contested":false}
{"id":"LANDSCAPE-035","claim":"AtomGradient/hybird-batch-prefill-on-ane measured 11.3x prefill speedup from batching 32 tokens per ANE dispatch instead of one on Qwen3.5-0.8B, and 7.3x on Qwen3.5-2B.","kind":"measurement","confidence":"measured","source":"https://github.com/AtomGradient/hybird-batch-prefill-on-ane","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","inference","batching"],"entities":["AtomGradient","Qwen3.5-0.8B","Qwen3.5-2B","M2 Ultra","MIT"],"evidence":"2 stars, MIT, last pushed 2026-03-18; sequential 23.7 tok/s versus batch 268.0 tok/s for 0.8B at a 74-token prompt","caveat":"M2 Ultra 192 GB under macOS 26, averaged over 10 runs","contested":false}
{"id":"LANDSCAPE-036","claim":"tinygrad's extra/accel/ane backend was early register-level ANE reverse engineering that no longer exists on the master branch and survives only at commit d0e7520.","kind":"fact","confidence":"documented","source":"https://github.com/tinygrad/tinygrad/tree/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane","source_type":"primary","retrieved":"2026-09-23","topic":["prior-art","history","registers"],"entities":["tinygrad","Python","MIT","hwx"],"evidence":"the extra/accel/ane tree is absent from master; the repository as a whole has 33642 stars and was pushed 2026-09-23","caveat":"the directory is not on the default branch, so a naive checkout will not find it","contested":false}
{"id":"LANDSCAPE-037","claim":"Neither anemll/anemll nor thebasedcapital/ane-infer had a LICENSE file at the repository root on 2026-09-23, and the GitHub API reports no detected license for either.","kind":"fact","confidence":"documented","source":"https://api.github.com/repos/anemll/anemll","source_type":"primary","retrieved":"2026-09-23","topic":["licensing","prior-art"],"entities":["ANEMLL","ane-infer","GitHub"],"evidence":"raw.githubusercontent.com/anemll/anemll/main/LICENSE and thebasedcapital/ane-infer/main/LICENSE both returned HTTP 404; API license field null for both","contested":false}
{"id":"LANDSCAPE-038","claim":"Sega Enterprises Ltd. v. Accolade, Inc., 977 F.2d 1510 (9th Cir. 1992) held that intermediate copying of object code during reverse engineering to discover the unprotected functional requirements for interoperability is fair use.","kind":"fact","confidence":"documented","source":"https://www.copyright.gov/fair-use/summaries/segaenters-accolade-9thcir1992.pdf","source_type":"primary","retrieved":"2026-09-23","topic":["legal","fair-use","interoperability"],"entities":["Sega","Accolade","fair use"],"evidence":"the court stressed that without a fair use exception for disassembling object code the owner would have a de facto monopoly over the functional aspects of the work","contested":false}
{"id":"LANDSCAPE-039","claim":"17 U.S.C. 1201(f)(1) exempts circumventing an access control for the sole purpose of identifying and analyzing elements necessary to achieve interoperability of an independently created computer program, to the extent those acts do not themselves infringe.","kind":"fact","confidence":"documented","source":"https://www.law.cornell.edu/uscode/text/17/1201","source_type":"primary","retrieved":"2026-09-23","topic":["legal","dmca","interoperability"],"entities":["DMCA","17 USC 1201"],"evidence":"1201(f) also permits developing and sharing the means to do so, and defines interoperability as the ability of computer programs to exchange information and mutually use it","caveat":"the statutory definition of interoperability is framed around two programs, which fits a hardware accelerator argument imperfectly","contested":false}
{"id":"LANDSCAPE-040","claim":"App Store Review Guideline 2.5.1 states that apps may only use public APIs and must run on the currently shipping OS.","kind":"fact","confidence":"documented","source":"https://developer.apple.com/app-store/review/guidelines/","source_type":"primary","retrieved":"2026-09-23","topic":["legal","app-store","policy"],"entities":["Apple","App Review Guidelines","private frameworks"],"contested":false}
{"id":"LANDSCAPE-041","claim":"Using AppleNeuralEngine.framework is unsupported rather than illegal: it breaches Apple's distribution policy and forfeits support, not a court-established prohibition.","kind":"fact","confidence":"inferred","source":"https://developer.apple.com/app-store/review/guidelines/","source_type":"primary","retrieved":"2026-09-23","topic":["legal","risk"],"entities":["AppleNeuralEngine.framework","App Store"],"caveat":"this is a reading of policy plus the interoperability authorities, not legal advice or a court ruling","split":"holdout","contested":false}
{"id":"LANDSCAPE-042","claim":"The community reference states that private frameworks cannot be used in shipped apps because Apple rejects apps that use private frameworks.","kind":"fact","confidence":"claimed","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/programming-ane.md","source_type":"primary","retrieved":"2026-09-23","topic":["legal","app-store"],"entities":["Apple","private frameworks"],"caveat":"the author's assertion about App Review behaviour, not an Apple statement","contested":false}
{"id":"LANDSCAPE-043","claim":"As of 2026-09-23 none of the ten surveyed projects cites Sega v. Accolade or 17 U.S.C. 1201(f) by name in its README or reachable docs.","kind":"open-question","confidence":"inferred","source":"https://github.com/maderix/ANE","source_type":"our-own","retrieved":"2026-09-23","topic":["legal","field-state"],"entities":["ANE"],"evidence":"README and docs directories of all ten projects were read or grepped and no such citation was found","caveat":"README and docs level check only; a legal note could exist in an issue thread or wiki","contested":false}
{"id":"LANDSCAPE-044","claim":"tinygrad's ANE documentation describes patching the amfid daemon in memory to disable the entitlement check so unsigned binaries can reach the engine.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/tinygrad/tinygrad/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["legal","entitlements"],"entities":["amfid","tinygrad","ANE"],"evidence":"the README gives a specific in-memory patch at +0x8e38 verified on macOS 12.4","caveat":"patching a system security daemon is a different act from interoperability reverse engineering and should not be assumed covered by the same arguments","contested":false}
{"id":"LANDSCAPE-045","claim":"Core ML adds 2x to 4x overhead compared with direct _ANEClient dispatch for small operations, with the gap narrowing only when ANE compute time dominates.","kind":"measurement","confidence":"measured","source":"https://maderix.substack.com/p/inside-the-m4-apple-neural-engine-615","source_type":"primary","retrieved":"2026-09-23","topic":["performance","overhead","coreml"],"entities":["Core ML","_ANEClient","M4"],"caveat":"M4 Mac Mini, macOS 15.x, direct API versus Core ML for the same operations","split":"holdout","contested":false}
{"id":"LANDSCAPE-046","claim":"Direct-API measurement on M4 found a true peak of 19 TFLOPS FP16, which is 100 percent of the theoretical peak implied by 16 cores at roughly 1.2 TFLOPS per core.","kind":"measurement","confidence":"measured","source":"https://maderix.substack.com/p/inside-the-m4-apple-neural-engine-615","source_type":"primary","retrieved":"2026-09-23","topic":["performance","peak"],"entities":["M4","ANE","fp16"],"evidence":"94 percent utilisation at 32 or more layers of graph depth","caveat":"M4 measurement quoted at source; '16 cores' is the published/API count — the compiler per-die field is 4 (base=4 g=8 s=16 c=32 d=64, arXiv 2606.22283 Ch24), see 10-m5-attribution-signals.md Q8","contested":false}
{"id":"LANDSCAPE-047","claim":"Apple's advertised 38 TOPS for the M4 Neural Engine is derived by doubling the measured 19 TFLOPS FP16 figure, and the hardware does not execute INT8 at twice the FP16 rate.","kind":"measurement","confidence":"measured","source":"https://maderix.substack.com/p/inside-the-m4-apple-neural-engine-615","source_type":"primary","retrieved":"2026-09-23","topic":["performance","quantization","marketing"],"entities":["M4","ANE","INT8","TOPS"],"evidence":"identical operations in FP16 and INT8 delivered nearly identical throughput, attributed to dequantization of INT8 weights before compute","caveat":"contradicted by the arXiv 2606.22283 account of a double-int8 compute mode; see the contested records","contested":true}
{"id":"LANDSCAPE-048","claim":"Training on the ANE is demonstrated: maderix reports Stories110M at 109M parameters and 91 ms per step, and Qwen3-0.6B at 596M parameters and 412 ms per step, with loss falling from 9.11 to 1.02 over 50 thousand steps.","kind":"measurement","confidence":"measured","source":"https://maderix.substack.com/p/inside-the-m4-apple-neural-engine-c8b","source_type":"primary","retrieved":"2026-09-23","topic":["training","performance"],"entities":["maderix/ANE","Stories110M","Qwen3-0.6B","M4"],"contested":false}
{"id":"LANDSCAPE-049","claim":"Training on the ANE ran at roughly 5 to 9 percent of peak utilisation with many element-wise operations still falling back to the CPU, and its author states it does not replace GPU training beyond small research models today.","kind":"fact","confidence":"claimed","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["training","limitations"],"entities":["maderix/ANE","ANE"],"caveat":"the author's own summary statement; not an independent measurement","contested":false}
{"id":"LANDSCAPE-050","claim":"No Core ML training API exists, so training on the ANE required reverse-engineering _ANEClient and _ANECompiler.","kind":"fact","confidence":"documented","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["training","access"],"entities":["Core ML","_ANEClient","_ANECompiler"],"contested":false}
{"id":"LANDSCAPE-051","claim":"ane-infer measured a fused FFN of eight operations in a single ANE dispatch at 3.6 TFLOPS against about 1.1 TFLOPS per single-op dispatch.","kind":"measurement","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer","source_type":"primary","retrieved":"2026-09-23","topic":["performance","fusion"],"entities":["ane-infer","ANE"],"evidence":"gate projection, sigmoid, multiply, up projection, multiply and down projection fused into one MIL program","caveat":"the project's own benchmark on its own hardware; not independently reproduced","contested":false}
{"id":"LANDSCAPE-052","claim":"ANE prefill drew 0.22 W of GPU power against 62.05 W for GPU prefill, a 282x reduction, because the ANE path leaves the GPU idle.","kind":"measurement","confidence":"measured","source":"https://github.com/AtomGradient/hybird-batch-prefill-on-ane","source_type":"primary","retrieved":"2026-09-23","topic":["power","prefill"],"entities":["ANE","M2 Ultra","MLX"],"caveat":"M2 Ultra 192 GB, macOS 26, temperature 0, ten-run averages","contested":false}
{"id":"LANDSCAPE-053","claim":"ane.cpp reports 30.08 tokens per second prompt throughput and 11.66 tokens per second generation for Qwen3.5-4B int8 on M3 Max, which the project itself calls modest for single-stream use.","kind":"measurement","confidence":"measured","source":"https://github.com/skyfallsin/ane.cpp","source_type":"primary","retrieved":"2026-09-23","topic":["performance","inference"],"entities":["ane.cpp","Qwen3.5-4B","M3 Max"],"contested":false}
{"id":"LANDSCAPE-054","claim":"A field-guide fit of ANE dispatch cost on M3 Max is latency approximately equal to 119 microseconds plus bytes divided by 78 GB per second.","kind":"measurement","confidence":"measured","source":"https://github.com/skyfallsin/ane.cpp","source_type":"secondary","retrieved":"2026-09-23","topic":["performance","dispatch"],"entities":["ANE","M3 Max"],"evidence":"quoted from the companion apple-neural-engine-field-guide's dispatch scaling benchmark","caveat":"a fit for const-weight matvec dispatches on one machine, not a hardware constant","contested":false}
{"id":"LANDSCAPE-055","claim":"The ANE's per-evaluation dispatch floor is about 0.23 ms on M1, and fusing 32 layers into one program amortizes that to roughly 6.3 microseconds per layer.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-silicon-reference.md","source_type":"secondary","retrieved":"2026-09-23","topic":["performance","dispatch","fusion"],"entities":["ANE","M1"],"evidence":"the note distils arXiv 2606.22283 chapter 19","caveat":"secondary distillation of another group's M1 measurement, not our own run","contested":false}
{"id":"LANDSCAPE-056","claim":"A symbolic breakpoint on the private method -[_ANEModel program] indicates that Core ML is using the Neural Engine for at least part of a model.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"primary","retrieved":"2026-09-23","topic":["visibility","debugging"],"entities":["_ANEModel","Core ML","ANE"],"caveat":"hitting the breakpoint does not prove the whole model ran on the ANE","contested":false}
{"id":"LANDSCAPE-057","claim":"Code that uses the private ANE frameworks is expected to break with macOS updates, as stated by both maderix and ane-infer.","kind":"fact","confidence":"claimed","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["risk","maintenance"],"entities":["maderix/ANE","ane-infer","macOS"],"contested":false}
{"id":"LANDSCAPE-058","claim":"The ANE compiler leaks resources at roughly 119 compiles per process, which maderix worked around by checkpointing and restarting the process with exec().","kind":"measurement","confidence":"measured","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["gotcha","compiler","limits"],"entities":["ANECompiler","maderix/ANE","M4"],"evidence":"compiles start failing after about 119 compile operations in one process","caveat":"the exact leaked resource was not identified by the author","contested":false}
{"id":"LANDSCAPE-059","claim":"The reference paper puts the ANE load-time ceiling at about 128 loaded programs per process with 127 in-flight requests per program.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-silicon-reference.md","source_type":"secondary","retrieved":"2026-09-23","topic":["limits","runtime"],"entities":["ANE","M1","M5"],"evidence":"the note cites arXiv 2606.22283 chapter 4 and chapter 19","caveat":"secondary distillation; the 119-compile figure from maderix is a separate compiler-side limit","contested":false}
{"id":"LANDSCAPE-060","claim":"Apple's sanctioned route for on-device training is MLX, not the Neural Engine.","kind":"fact","confidence":"inferred","source":"/Volumes/data/local_ai_stack/results/RESEARCH-SWEEP.md","source_type":"our-own","retrieved":"2026-09-23","topic":["training","apple-guidance"],"entities":["Apple","MLX","ANE"],"evidence":"WWDC26 session 233 covers distributed inference and training with MLX; no Apple material covers ANE training","caveat":"absence of an Apple ANE training path is inferred from the absence of documentation, not from a statement","contested":false}
{"id":"LANDSCAPE-061","claim":"Core ML and the private API are separate compilation and dispatch pipelines to the same silicon: Core ML's ANE model is held inside opaque Espresso C++ plan and context pointers rather than exposed as an _ANEModel object.","kind":"fact","confidence":"documented","source":"https://github.com/thebasedcapital/ane-infer","source_type":"primary","retrieved":"2026-09-23","topic":["coreml","private-api","architecture"],"entities":["Espresso","MLProgramEngine","_ANEModel","ANE"],"evidence":"deep-walking a loaded MLProgram showed _isANEPathForbidden=NO and _modelIsMIL=YES with the plan held in _plan and _context","split":"holdout","caveat":"observed on M5 under macOS 26.3 for one MLProgram","contested":false}
{"id":"LANDSCAPE-062","claim":"The direct evaluation path doEvaluateDirectWithModel: skips the ANE daemon XPC hop and measured 106 microseconds against 117 microseconds for the standard evaluateWithQoS: path on M5.","kind":"measurement","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer","source_type":"primary","retrieved":"2026-09-23","topic":["performance","dispatch","private-api"],"entities":["_ANEClient","ane-infer","M5"],"caveat":"single-machine measurement by the project; not independently reproduced","contested":false}
{"id":"LANDSCAPE-063","claim":"Sources disagree on whether INT8 confers compute speedup on the ANE: maderix measured no speedup because INT8 weights are dequantized to FP16 before compute, while the arXiv 2606.22283 account reports a double-int8 compute mode running at about 1.4x to 2x the fp16 rate.","kind":"open-question","confidence":"measured","source":"https://maderix.substack.com/p/inside-the-m4-apple-neural-engine-615","source_type":"primary","retrieved":"2026-09-23","topic":["quantization","performance","dispute"],"entities":["ANE","INT8","M4"],"evidence":"maderix: identical throughput for FP16 and INT8 in the same operations; arXiv 2606.22283 via coreai-model-zoo knowledge note: double-int8 compute mode at 1.4-2x fp16","caveat":"the two claims may both be true if weight-only INT8 (W8A16) dequantizes while int8 activations (W8A8) use the double-int8 datapath","contested":true}
{"id":"LANDSCAPE-064","claim":"Sources disagree on whether ANE decode beats the GPU: the reference paper reports the GPU at batch 16 being 2.7x faster and 4.6x more energy-efficient, while our own M4 embedder measurement found the ANE path slightly faster with roughly 125x less GPU power.","kind":"open-question","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["performance","dispute","decode"],"entities":["ANE","GPU","M4","Granite-Embedding-97M"],"evidence":"our v3 fp16 build: 4.00 ms at 83 mW GPU versus 4.33 ms at 10390 mW for the published fp32 GPU path; paper: GPU 2.7x faster at batch 16","caveat":"different workloads and different chips; the paper measures batched decode, we measured a single-encoder embedding forward pass","contested":true}
{"id":"LANDSCAPE-065","claim":"The ANE and the GPU are physically separate processors on the same die, and Metal cannot be used to program the ANE.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/ane-vs-gpu.md","source_type":"primary","retrieved":"2026-09-23","topic":["hardware","architecture"],"entities":["ANE","GPU","Metal"],"evidence":"Core ML uses BNNS on CPU, Metal Performance Shaders on GPU, and private frameworks on the ANE","contested":false}
{"id":"LANDSCAPE-066","claim":"The ANE computes in float16 throughout, so activations well above 1e2 or below 1e-4 lose precision or underflow to zero.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/16-bit.md","source_type":"primary","retrieved":"2026-09-23","topic":["precision","gotcha"],"entities":["ANE","fp16"],"caveat":"written before the Core AI era; the datapath still does not support fp32 computation","contested":false}
{"id":"LANDSCAPE-067","claim":"Device generations differ in ANE configuration: the M4 has a 16-core Neural Engine advertised at 38 TOPS, the M2 Ultra and M3 Ultra have 32-core Neural Engines, and Intel-based Macs have no ANE at all.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/supported-devices.md","source_type":"primary","retrieved":"2026-09-23","topic":["hardware","devices"],"entities":["M4","M2 Ultra","M3 Ultra","A11","Intel Mac"],"evidence":"Apple's advertised TOPS figures are quoted per generation in that document and are not independently verified there","caveat":"the advertised 38 TOPS for M4 is contested by direct measurement of 19 TFLOPS FP16","contested":false}
{"id":"LANDSCAPE-068","claim":"A single ANE matmul operation uses only about 30 percent of the engine's capacity, so throughput comes from chaining many operations into one program rather than from optimizing individual ops.","kind":"measurement","confidence":"measured","source":"https://maderix.substack.com/p/inside-the-m4-apple-neural-engine-615","source_type":"primary","retrieved":"2026-09-23","topic":["performance","fusion"],"entities":["ANE","M4"],"caveat":"M4 direct-API measurement; the reported utilisation figure is approximate","contested":false}
{"id":"LANDSCAPE-069","claim":"ane-infer reports that after seven probe iterations, the ANEProgramChainingPrepare error 15 was caused not by a firmware limit but by using the wrong _ANEIOSurfaceOutputSets factory method.","kind":"measurement","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer","source_type":"primary","retrieved":"2026-09-23","topic":["private-api","chaining","debugging"],"entities":["_ANEChainingRequest","_ANEIOSurfaceOutputSets","ane-infer"],"evidence":"outputSetsWithBuffers: returned error 15 while objectWithstatsSurRef:outputBuffer: succeeded","caveat":"buffersReady remained blocked at the time of writing, so chaining was not fully working","contested":false}
{"id":"LANDSCAPE-070","claim":"libane implements matmul as a 1x1 convolution to gain a throughput advantage over the MIL matmul op.","kind":"fact","confidence":"documented","source":"https://github.com/AmiraniLabs/libane","source_type":"primary","retrieved":"2026-09-23","topic":["implementation","performance"],"entities":["libane","conv1x1","MIL"],"evidence":"the README cites a claimed 3x advantage over MIL matmul, referencing arXiv 2603.06728","caveat":"the 3x figure is the project's claim, not our measurement","contested":false}
{"id":"LANDSCAPE-071","claim":"Core AI graphs can be made ANE-resident by dtype choices alone, but that is not sufficient to make them fast: the fp16 as-is variant was on the ANE yet three times slower than the GPU path.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["core-ai","performance","placement"],"entities":["Core AI","Granite-Embedding-97M","M4"],"evidence":"fp16 v0 13.14 ms versus fp32 GPU 4.33 ms, while v0 was still ANE-resident","caveat":"one graph on an M4; the conclusion that running on the ANE and running well on it are separate claims should generalise but was not tested beyond this graph","contested":false}
{"id":"LANDSCAPE-072","claim":"A Core AI community knowledge page documents that AOT architecture names track the device identifier, not the marketing name: only the matching .aimodelc loads (M4 Max = h16c, iPhone 17 Pro = h18p), and coreai-build compile exits 0 for any requested architecture so only a device load validates the choice — meaning our AOT-gate finding re-derives a published rule, and our novelty is the observed parts (M5 Max h17c, M4 mini h16g) plus the private-selector divergence.","kind":"fact","confidence":"documented","source":"https://github.com/ai00ai/Apple-coreai-model-zoo-local/blob/main/knowledge/aot-and-specialization.md","source_type":"primary","retrieved":"2026-10-10","topic":["prior-art","coreai","architecture","aot"],"entities":["Core AI","h16c","h18p","coreai-build","Mac16"],"evidence":"section 'Architecture names track the DEVICE IDENTIFIER, not the marketing name (device-validated 2026-06-10)' with per-device .aimodelc load results","caveat":"community knowledge page (verbatim WWDC + device runs); does not list M5 Max or M4 mini, so our two parts remain unstated there","contested":false}
{"id":"LANDSCAPE-073","claim":"tmc/aneperf reads the ANEXL and ANE UP IOReport channels through a name-substring filter (any channel containing 'ANE'), groups SOC-NI Util BW under bandwidth, and derives ane_utilization_pct from the Fast-Die CE histogram — so the ANEXL channel is public, but no source claims it is lane-exclusive, leaving our calibrated exclusivity result as the new part.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/aneperf","source_type":"primary","retrieved":"2026-10-10","topic":["prior-art","ane","observability","counters"],"entities":["aneperf","ANEXL","SOC-NI Util BW","Fast-Die CE","ane_utilization_pct"],"evidence":"classify.go ChannelsByCategory + ioreport.go containsANE() (word-boundary 'ANE' match citing ANEXL as an example); README channel-group list","caveat":"aneperf treats all ANE-named channels as one bucket, so it neither proves nor claims exclusivity","contested":false}
{"id":"LANDSCAPE-074","claim":"kennss/SiliconScope publishes a verified sudoless IOReport channel map spanning M1 to M5 Max covering Energy Model ANE power and PMP0 DCS/AF BW, but never names SOC-NI9 ANEXL U or SOC-NI8 ANE UP and makes no ANE lane-exclusivity claim — ANE power monitoring is public, an ANE activity counter is not.","kind":"fact","confidence":"documented","source":"https://github.com/kennss/SiliconScope/blob/main/docs/ioreport-channels.md","source_type":"primary","retrieved":"2026-10-10","topic":["prior-art","ane","observability","counters"],"entities":["SiliconScope","PMP0","Energy Model ANE","ANEXL"],"evidence":"per-chip channel tables (M1 Max, M3 Max, M4 Max, M5 Max) listing Energy Model/PMP groups; no SOC-NI Util BW requestor named","caveat":"community monitor; its M5 notes come from a contributor (@ben0112) who owns no M5","contested":false}
{"id":"LANDSCAPE-075","claim":"exelban/stats issue #2897 (2026-01-04 to 2026-09-05) records the community position that macOS exposes no usable system-wide ANE utilization signal: mactop's ANE percent is a power heuristic (ANE watts divided by a hard-coded 8.0 W), and Stats' own ANE-utilization attempt did not track ANE correctly — strengthening our calibrated ANEXL counter as a genuinely new capability rather than a re-derivation.","kind":"fact","confidence":"documented","source":"https://github.com/exelban/stats/issues/2897","source_type":"primary","retrieved":"2026-10-10","topic":["prior-art","ane","observability","counters"],"entities":["exelban/stats","mactop","ANEXL"],"evidence":"issue thread: maintainer 'no good way to obtain this data'; mactop's internal/app/ioreport.m sums channels whose name starts with ANE into anePower and menubar.go divides by 8.0; user reports Stats' ANE module not tracking","caveat":"a community thread, not a specification; predates any later monitor that may have found a better signal","contested":false}
```

---

## Sources

Every source actually used, with how it was used.

**Local — community reference docs**
- `/Volumes/data/local_ai_stack/repos/neural-engine/README.md` — what the ANE is, table of contents
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/programming-ane.md` — "cannot program the ANE directly"; private-framework rejection claim
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/running-on-ane.md` — `computeUnits = .all` is a preference
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md` — no runtime device query; `-[_ANEModel program]` breakpoint; Espresso engines
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/ane-vs-gpu.md` — ANE and GPU are separate; Metal cannot program the ANE
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/16-bit.md` — fp16 throughout
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/supported-devices.md` — per-generation core counts and advertised TOPS
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/why-care.md` — speed and energy rationale
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/reverse-engineering.md` — pointer to tinygrad's ANE work
- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/internals.md` — nothing outside Apple knows

**Local — tooling**
- `/Volumes/data/local_ai_stack/repos/ane-probe/README.md` — MLComputePlan op-support probing
- `/Volumes/data/local_ai_stack/repos/anemll-profile/README.md` — profiler: MLComputePlan + Espresso cost logs + predictions
- `/Volumes/data/local_ai_stack/tools/enginemon/README.md` — unprivileged IOReport ANE counters; frozen energy channel; xctrace blindness
- `/Volumes/data/local_ai_stack/repos/aneperf/` — Go ANE perf tool (directory listing only; not analysed here)

**Local — our own results and knowledge**
- `/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md` — fp32 → fp16 → 1 region; GPU mW comparisons; region-count correction
- `/Volumes/data/local_ai_stack/results/RESEARCH-SWEEP.md` — project star/date survey, MLX-as-Apple-training-path, prior-art cluster
- `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/coreai-overview.md` — Core AI vs Core ML, `.aimodel`, closed runtime
- `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-silicon-reference.md` — secondary distillation of arXiv:2606.22283 (load limits, dispatch floor, decode verdict)
- `/Volumes/data/local_ai_stack/repos/coreai-kit/docs/GETTING_STARTED.md` — Core AI app-level API and `.neuralEngine` compute unit

**Repositories (fetched 2026-09-23, stars/dates via the GitHub API)**
- https://github.com/maderix/ANE — MIT, 7,261 stars, pushed 2026-03-10
- https://github.com/johnmai-dev/ANE-LM — MIT, 143 stars, pushed 2026-03-04
- https://github.com/AmiraniLabs/libane — Apache-2.0, 7 stars, pushed 2026-09-22
- https://github.com/thebasedcapital/ane-infer — no license file, 28 stars, pushed 2026-03-05; `docs/ane-internals.md`
- https://github.com/anemll/anemll — no license file, 1,677 stars, pushed 2026-09-18
- https://github.com/skyfallsin/ane.cpp — MIT, 5 stars, pushed 2026-04-25
- https://github.com/royisme/qwen-ane-llm — MIT, 1 star, pushed 2026-03-04
- https://github.com/shershah1024/lfm2.5-vl-ane — MIT code + LFM Open License v1.0 model, 2 stars, pushed 2026-06-16
- https://github.com/AtomGradient/hybird-batch-prefill-on-ane — MIT, 2 stars, pushed 2026-03-18
- https://github.com/tinygrad/tinygrad — MIT, 33,642 stars, pushed 2026-09-23; ANE backend read at commit `d0e752003da3fc023fa85094d7f5b65b47dd5091`
- https://github.com/nst/iOS-Runtime-Headers/tree/master/PrivateFrameworks/AppleNeuralEngine.framework — header names
- https://github.com/mdaiter/ane — consulted for the entitlement findings behind the private-API route (not in §3's table; cited here for completeness of the survey)

**Articles, papers, and legal sources**
- https://maderix.substack.com/p/inside-the-m4-apple-neural-engine — Part 1, reverse engineering and the private-API sequence
- https://maderix.substack.com/p/inside-the-m4-apple-neural-engine-615 — Part 2, benchmarks, Core ML overhead, 19 TFLOPS vs 38 TOPS
- https://maderix.substack.com/p/inside-the-m4-apple-neural-engine-c8b — Part 3, training, limitations, 119-compile limit
- https://eiln.github.io/posts/ane-dma.html — 1 MiB DMA erratum, register-level method
- https://arxiv.org/abs/2606.22283 — *Apple Neural Engine: Architecture, Programming, and Performance*
- https://arxiv.org/abs/2608.22110 — *What actually runs: placement and decode speed on the ANE*
- https://arxiv.org/abs/2606.17090 — *ANEForge: Python for direct computation on the Apple Neural Engine*
- https://www.copyright.gov/fair-use/summaries/segaenters-accolade-9thcir1992.pdf — Sega v. Accolade holding
- https://www.law.cornell.edu/uscode/text/17/1201 — 17 U.S.C. § 1201, including the reverse-engineering exception (f)
- https://developer.apple.com/app-store/review/guidelines/ — App Store Review Guideline 2.5.1
- https://api.github.com/repos/… — star counts, `pushed_at`, language and license fields for the ten repositories, read 2026-09-23

**Not reachable / not used**
- `churchofgeohot`-era tinygrad ANE write-ups and the YouTube stream recordings linked from `docs/reverse-engineering.md` were not fetched.
- `https://github.com/anemll/anemll` root `LICENSE` path returned HTTP 404 (recorded above as a finding, not a failure).