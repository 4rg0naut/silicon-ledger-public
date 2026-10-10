# FAILURES — do not repeat these

Every failure, wrong assumption and dead end encountered while building this
stack, recorded so it is not rediscovered later. **Read this before debugging
anything similar.** Each entry ends with the rule it produced.

Format: **symptom → what I wrongly assumed → actual cause → fix → rule.**

---

## A. Core ML conversion

### F-01 · coremltools cannot lower `int()` on shape-derived tensors — **trigger is NumPy ≥ 2.4**
- **Symptom:** `TypeError: only 0-dimensional arrays can be converted to Python scalars`;
  coremltools logs `ERROR - converting 'int' op (located at: 'model/embeddings/44')`.
- **Wrongly assumed (twice):** that torch/transformers were "too new" (see F-02, F-03).
- **Actual cause — proven by A/B:** holding **torch 2.7.0, coremltools 9.0 and
  transformers 4.57.6 identical** and changing only NumPy:
  | numpy | result |
  | --- | --- |
  | 2.5.3 | ❌ same `TypeError` |
  | < 2.4 | ✅ **CONVERSION OK, unpatched** |

  coremltools' `_cast` handler materialises a shape-derived value with `dtype(x.val)`
  where `x.val` is a **1-element array with ndim ≥ 1**. NumPy **deprecated** converting
  ndim > 0 arrays to Python scalars and now **raises** — so code that used to work with
  a warning crashes. The `aten::Int` handler's "single value" assumption is *correct by
  the operator's definition*; the break is NumPy tightening its rules under it.
- **Upstream status: already reported.**
  [#2633](https://github.com/apple/coremltools/issues/2633) ("NumPy 2.4.0 breaks CoreML
  export…"), [#2755](https://github.com/apple/coremltools/issues/2755) ("…models using
  `int()` on shape-derived tensors during PyTorch tracing"). Same signature also hits
  [Ultralytics YOLO](https://github.com/ultralytics/ultralytics/issues/25098) and
  [EdgeTAM](https://github.com/facebookresearch/EdgeTAM/issues/14).
- **Fixes available:** (a) pin `numpy < 2.4` in the conversion env — verified working;
  (b) our workaround: replace only `BertEmbeddings.forward` with a trace-friendly
  equivalent that keeps every real weight (`bench/convert_encoder_coreml.py::patch_embeddings`),
  validated at cosine **0.999983**; (c) upstream one-liner: `dtype(numpy.asarray(x.val).item())`
  plus a clear error naming the op and operand shape.
- **Rule:** on a conversion failure, **check the NumPy version first** — and isolate a
  version hypothesis by changing *one* package at a time. `bench/repro_int_op.py` is the
  minimal reproduction.

- **UPSTREAM STATUS (verified 2026-09-20) — no self-compiled patch is needed:**
  - NumPy's change is **intentional and permanent**: numpy/numpy#10404 (2018, "deprecate
    scalar conversions for rank>0 arrays") → numpy/numpy#29835 (Sep 2025, "Raise
    `TypeError` on attempt to convert array with `ndim > 0` to scalar"). **Never patch
    NumPy** — that fights the ecosystem's direction.
  - coremltools fixed it in **PR #2632** (merged), but **the fix never shipped in the
    9.0 PyPI release** — hence everyone on `coremltools==9.0` still hits it.
  - **Verified here:** `coremltools 9.1.dev1` (PyPI pre-release) + `numpy 2.5.3` +
    torch 2.7.0 → **unpatched model CONVERTS OK** (268 ops, no error).
  - Options, all verified: pin `numpy<2.4` · use `coremltools>=9.1.dev1` · keep our
    model-specific monkey-patch · wait for 9.1 stable.

### F-02 · Version-chasing on a conversion failure (torch 2.13 → 2.7)
- **Symptom:** same error after rebuilding an env with torch 2.7.0 ("the version
  coremltools is tested against").
- **Actual cause:** the version was never the problem (see F-01).
- **Rule:** a version *warning* ("only tested with torch ≤ 2.7") is not a diagnosis.
  Reproduce, localise, **then** consider versions.

### F-03 · Same trap again with transformers (5.x → 4.57.6)
- **Symptom:** identical failure after downgrading transformers.
- **Rule:** if two independent version changes produce the *identical* error, the
  cause is almost certainly not a version. Stop and instrument instead.

### F-04 · Dependency warnings silently disabled functionality
- **Symptom:** `scikit-learn version 1.9.1 is not supported … Disabling scikit-learn
  conversion API`; `coreai-torch has only been validated with torch<=2.13.0; found 2.14.0`.
- **Cause:** import-time warnings announcing that a subsystem was switched off.
- **Fix:** pin `torch==2.13.0` (for coreai-torch) and `scikit-learn==1.5.2`
  (for coremltools).
- **Rule:** **read import warnings.** "Disabling X" is a silent capability loss,
  not noise.

### F-05 · `.venv-conv` exists for a reason that turned out to be false
- **Cause:** created to test the torch-2.7 theory (F-02), which was wrong.
- **Decision:** **kept anyway** — coremltools is genuinely untested above torch 2.7,
  so it is a cheap fallback. Its purpose is documented in `results/env.md` so nobody
  mistakes it for a requirement.
- **Rule:** keep the artifact, correct the justification. Never leave a stale
  rationale in place.

---

## B. Xcode / xctrace tooling

### F-06 · `xcrun` could not find any Xcode tool
- **Symptom:** `unable to find utility "xctrace"`, then later
  `You have not agreed to the Xcode license agreements`.
- **Wrongly assumed:** that `xcode-select -s` was **optional** after installing Xcode.
  It is **required** — the active developer dir stayed on CommandLineTools.
- **Fix:** `sudo xcodebuild -license accept` **and**
  `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.
- **Rule:** never describe a required step as optional. After an Xcode install,
  verify `xcrun --find <tool>` before believing anything works.

### F-07 · The real error was hidden by suppressing stderr
- **Symptom:** my loop printed `MISSING` for every tool — because I wrote
  `xcrun --find "$t" 2>/dev/null || echo MISSING`.
- **Cause:** the actual message (a licence error) was thrown away, so a
  permissions/licence problem looked like a missing binary.
- **Rule:** **never suppress stderr while diagnosing.** `2>/dev/null` is for
  scripts that have already been proven correct.

### F-08 · `xctrace` hung forever on the Foundation Models template
- **Symptom:** a 20 s `--time-limit` recording still running minutes later; trace
  file frozen at 40 KB; export failed with "Document Missing Template Error".
- **Cause:** an **interactive privacy prompt** that a headless shell cannot answer.
- **Fix:** add `--no-prompt`.
- **Rule:** any Instruments recording from a script needs `--no-prompt`. If a
  `--time-limit` is ignored, suspect a prompt, not the tool.

### F-09 · `DEVELOPER_DIR` regressed between sessions
- **Symptom:** `xctrace` resolved in one call, then "unable to find utility" in the next.
- **Rule:** do not depend on system toolchain state. Export
  `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` in every command/script.

---

## C. ANE measurement

### F-10 · A single-op probe gave a *wrong* answer (`conv` → ANE: NO)
- **Symptom:** `ane_probe check conv --shape 1,3,224,224` reported `Supported: [CPU,GPU]`, ANE NO.
- **Cause:** hand-picked parameters produced a different op variant. The **full scan**
  reports `conv → ANE: YES`.
- **Rule:** use the **full scan**; never generalise from a single-op spot check.
  (Recorded as a correction in EXP-001 rather than silently fixed.)

### F-11 · `preferred=CPU` misread as a limitation
- **Cause:** single-op models pay ANE transfer overhead, so the compiler prefers CPU.
  It says nothing about the op's capability.
- **Rule:** only the `supported` column is meaningful in an ane-probe row.

### F-12 · Assumed the ANE needs static shapes
- **Symptom:** expected a dynamic-shape (`RangeDim`) conversion to fall back off the ANE.
- **Reality:** the dynamic variant still measured **0.76 ms / 2.20×** — ANE not lost.
- **Rule:** test the assumption instead of designing around it. (Still caveated:
  measured only at length 128.)

### F-13 · Cold-start cost misread as a per-request tax
- **Symptom:** a traced `fm respond` showed 372 ms of asset loads + 295 ms of safety
  model loads against 130 ms of inference → I called it a "2.4× tax".
- **Cause:** that was a **cold window**. Warm one-shot is 0.24 s; a resident server is
  *no faster* (0.26–0.33 s) because the OS caches model assets across processes.
- **Rule:** **measure cold vs warm before attributing a cost.** Load costs amortise;
  per-request costs do not.

---

## D. Containers / zvec-grep (`zg`)

### F-14 · Index build stalled: 437% CPU, 100 GiB block I/O, zero progress
- **Cause (mine, not zg's):** container defaulted to **1 GB RAM** and the index sat on
  a **virtiofs bind mount**; RocksDB + virtiofs thrashed.
- **Fix:** named volume + `--memory 4g` → clean 31 s build.
- **Rule:** for DB-like I/O in Apple containers use **named volumes** (Apple's docs say
  bind mounts are virtiofs and named volumes are faster), and always set `--memory`.

### F-15 · Stale index lock after killing a container
- **Symptom:** `Index unavailable · ZVEC_GREP.ENGINE.LOCK.BUSY`, `ownerHost` = a dead
  container id.
- **Cause:** I copied the repo into the volume **before** deleting the partial index, so
  the dead container's lock travelled with it.
- **Fix:** delete `.zvec-grep` (or its `locks/`) before re-indexing.
- **Rule:** clean partial state **before** copying/moving a workspace, not after.

### F-16 · Read the main-branch docs, ran a 0.2.2 binary
- **Symptom:** `Error: Unknown option: --compact`, `Error: Unknown command: --index`.
- **Cause:** the repository docs describe an unreleased CLI shape; the installed
  release uses subcommands (`zg index`, `zg query`).
- **Rule:** **`<binary> --help` is the source of truth** for the installed version;
  repo docs may describe main.

---

## E. Agent / harness behaviour (mine)

### F-17 · Launching an interactive TUI with `--model` overwrote the global default
- **Symptom:** after a terminal restart, omp came up on `apple-fm/system` (8 192-token
  window) against a 248 007-token session → compaction failed, 400s, session unusable.
- **Cause:** I launched a TUI with `--model apple-fm/system` for a benchmark;
  **interactive model selection persists as `modelRoles.default`** in the global config.
- **Fix:** removed the provider registration; adopted the rule below.
- **Rule:** **never pass `--model` to an interactive TUI on someone's machine.** Use
  project-scoped config (`<project>/.omp/config.yml`) for experiments, and check
  `omp config get modelRoles` afterwards.

### F-18 · `.gitignore` pattern too narrow → 200+ junk files committed
- **Symptom:** trace-bundle internals entered the first commit because the pattern was
  `results/**/raw/*.trace/` and EXP-002's bundles live outside `raw/`.
- **Fix:** `results/**/*.trace/` + `git rm -r --cached` + amend.
- **Rule:** after writing a `.gitignore`, **verify with `git status --short`** before
  committing; make patterns as broad as the real layout.
- **⚠️ RECURRED (2026-09-20, same day):** committing the Swift runner tracked **2090 files**
  because `.build/` (SwiftPM checkouts, object files, embedded git repos) was not ignored.
  The rule existed and was not applied. **Adding an ignore pattern is not the same as
  checking that it works** — run `git ls-files | wc -l` and eyeball the list *before* the
  commit lands, not after. Fixed by ignoring `tools/**/.build/` and `git rm -r --cached`.
- **⚠️ RECURRED AGAIN (2026-09-20, third time): 418 compiled bundles committed.** A probe
  script wrote its `.aimodelc` output into `bench/` instead of `work/`. Worse, the
  pre-commit check **printed `tracked = 466`** and I committed anyway — the check ran but
  its result was not read. The count was ~10× the expected 41.
- **Rule (now enforced by habit, not intent):** a tracked-file count is a **gate**, not
  decoration. Read it, compare it against expectation, and only then commit. Any script
  that writes build output must target `work/` (gitignored) — never a tracked directory.
  This has now cost three amend cycles for one class of mistake; the pattern is that I
  verify *after* acting rather than *before*.

### F-19 · Claimed a dependency relationship that the evidence did not support
- **Symptom:** asserted that omp's `mnemopi` derives from Mnemosyne based on a filename.
- **Rule:** label inference as inference. (`[INFERENCE]` was used, but the claim was
  still weaker than the surrounding text implied.)

### F-20 · Silent backend degradation in `mnemopi`
- **Symptom:** `Mnemopi: llmMode=smol but no tiny/smol model resolved; continuing without LLM.`
  Row counts confirmed it: `facts=0`, `consolidation_log=0`, `episodic_memory=0`.
- **Rule:** when a backend says "continuing without X", check the data store to confirm
  what X was supposed to produce — a degraded backend still looks alive.
- **✅ ROOT-CAUSED (EXP-006):** the LLM is gated by `BeamMemory.localLlmEnabled`, which defaults to
  `false` with **no environment fallback** (`src/core/beam/index.ts:70,87`), and the CLI builds
  `new BeamMemory({ dbPath })` without it. `MNEMOPI_LLM_ENABLED=1` is read
  (`src/core/local-llm.ts:77`) but the config gate wins, so `sleep` silently falls back to the
  heuristic `aaak` path (`llm_used: 0`). **Enabling it is host-side**: whoever constructs the
  engine must pass `config: { localLlmEnabled: true }`. `fm serve` is now verified as the backend
  (`/v1/chat/completions`, model `system`).

### F-21 · A "decisive" differential test whose positive control never fired
- **Symptom:** the accelerator-contention test produced a *clean-looking, appealing* story:
  `granite(.neuralEngine)` slowed **1.27×** under a CPU+GPU hog and **1.16×** under an
  ANE-inclusive hog — i.e. "slowed by a load that cannot use the ANE, therefore it is NOT on
  the ANE." That reading was wrong to make, because the **positive control failed**:
  `granite(.gpu)` slowed only **1.10×** under a GPU hog, so the method cannot detect GPU
  contention at all on this machine. Every row was void.
- **Rule:** a differential/inference test needs a **positive control that must fire**, and the
  harness must **refuse to print a verdict** when it does not. Encode the refusal in the tool
  (this one returns exit 1 with "METHOD FAILED"), not in the operator's judgement.
- **Why it matters:** without the control the numbers were *inside noise* (1.27 vs 1.16) yet
  pointed the opposite way from the truth. A method that cannot fail loudly is not a method.

### F-22 · A distinct latency signature read as a distinct execution unit
- **Symptom:** `.neuralEngine` measured **4.331 ms ±0.015** over 5 runs — non-overlapping with
  `gpu` (4.982 ±0.461), ~30× tighter, 1.885× faster than `cpuOnly`. That looks like a third
  hardware backend, and EXP-004 briefly argued it "favours reading (b): Core AI's ANE path is
  invisible to `ane-hw-intervals`". The power rails then showed the opposite: **ANE 0.0 mW,
  GPU 4421.6 mW** — a different **GPU schedule**, not a different unit.
- **Rule:** latency determinism is a property of the *schedule*, not of the *unit*. Only an
  instrument that observes the hardware (power rails, hardware counters) establishes which unit
  ran. Timing fingerprints generate hypotheses; they are never evidence of placement — and the
  label `[INFERENCE]` on its own does not stop a wrong inference from being written down as a
  lean. Prefer "not yet known" over a direction.

### F-23 · Exported only the table I predicted, out of 36
- **Symptom:** for two sessions I treated `ane-hw-intervals` as *the* ANE answer and never
  enumerated the trace's tables. The `Core AI` template exposes **36**, including
  `metal-gpu-intervals` (which attributed **54,846** GPU intervals to our process — decisive)
  and `ODIEProfile` (Core AI's own profiler). I found them only after an outside suggestion.
- **Rule:** before concluding from an instrument, **list everything it provides**
  (`xctrace export --toc`, `--help`, schema dump) and *then* choose the table. The table you
  reach for first is the one you already believe in; it is not evidence about the ones you
  didn't look at.
- **Corollary:** an absence is only as strong as the instrument's coverage. "0 intervals"
  meant nothing until I knew which tables existed and what each one covers.

### F-24 · A dead counter read as a negative result
- **Symptom:** my first `enginemon` build reported `ANE (exact) = 0.0 mW` and I nearly wrote
  "the ANE drew no power" as evidence. In fact `Energy Model → ANE` is a **frozen** channel: it
  reads a constant (10945781) under idle *and* under a Core ML workload that provably uses the
  ANE (171 GB of ANE memory traffic). The zero was the *counter*, not the engine.
- **Second instance in the same hour:** `SoC Stats → ANE_*_TRIG` advanced by exactly
  `elapsed × 24e6` (5.46 s → 131110395 ticks) regardless of load — a free-running 24 MHz clock
  wearing an ANE name. It looked like strong activity and meant nothing.
- **Rule:** before treating a zero as evidence, **prove the counter moves** — run a positive
  control that *must* move it. A channel whose name mentions your engine is not a channel that
  measures your engine. Both traps are now excluded/labelled in the tool itself, because a
  comment in a README does not stop the next person (or me) from reading the number.

### F-25 · Blamed the build mode when the artifact was the problem
- **Symptom:** with `.neuralEngine` silently ignored, I hypothesised a *packaging* cause — the
  bundle metadata said `"Portable source IR, no AOT"`, so I predicted an AOT compile would
  deliver the ANE. It did not: 0 ANE regions, same GPU execution, and the *same* 0 for iOS/h18p,
  the zoo's known-working recipe. The real cause was **authoring**: the graph is fp32, standard
  `(B,S,D)` layout, `nn.Linear` — while ANE requires **fp16, BC1S, 1×1 Conv2d**.
- **Rule:** when a target silently refuses your work, check whether the **artifact satisfies the
  target's documented requirements** (dtype, layout, op form) *before* blaming the build mode,
  the runtime, or the toolchain. "Try the other build path" is a cheap experiment but a poor
  first hypothesis — and the documented requirements were already in the cloned repo, unread.
- **Tell:** the compile finished in 0.87 s where a real ANE build takes hundreds of seconds.
  Suspiciously fast output is a signal that nothing was actually lowered.

### F-26 · Read ANE region count as a quality metric
- **Symptom:** after removing the fp32 ops the ANE region count fell **13 → 1**, and I nearly
  filed that as a regression (the zoo's ANE bundles report 31/31, so "2" looks broken). Runtime
  said the opposite: GPU power **333 → 83 mW**, warm median **13.14 → 4.00 ms**, while ANE
  bytes moved stayed ~88 GB. Fewer regions meant **fewer ANE↔GPU segment boundaries**, not less
  ANE work.
- **Rule:** region count is a **shape** metric, not a quality metric. It says how finely the
  graph is cut, not how much ran where. Pair it with runtime evidence (work done, power,
  latency) before concluding anything — the zoo's own 49 → 25 observation is the same effect.
- **Corollary:** "it runs on the ANE" and "it runs *well* on the ANE" are different claims.
  fp16 alone moved the graph onto the ANE and made it **3× slower**; only the fp32-op removals
  made it worth having.

### F-27 · Counted directories and files as one thing
- **Symptom:** ANE region counts were reported as 14 / 2 / 2 / 2 across the sweep, and I used
  them as a headline metric. They were **13 / 1 / 1 / 1**: my glob `*ANE_region*` matched both
  the region **directory** (`..._ANE_region_0_0.bc`) *and* the file inside it
  (`.../h16g/..._ANE_region_0_0.mlir.bc`). Every count was inflated by exactly one.
- **The zoo's own docs gave the right glob** — `find <bundle> -name '*ANE_region_*.mlir.bc' |
  wc -l` — and I had read that line before writing mine.
- **Rule:** when a count is used as a gate or a headline, verify the pattern against a case
  whose answer you already know (here: a bundle with 0 regions, which both globs agree on —
  the disagreement only shows up where it matters). A wildcard that matches both a container
  and its contents is a silent double-count.
- **Why it survived so long:** the *ordering* was correct (13 > 1 > 0), so every conclusion
  still held — the error hid behind a correct story. Numbers in a table get re-used; the count
  appeared in four places before it was checked.

### F-28 · Printed a verdict from a one-sample window
- **Symptom:** `power_phase_probe.py` split its power samples at the measured latency transition
  and reported "ANE power is FLAT while throughput halves: a bandwidth ceiling". The run had
  **never entered the slow state** (fast phase 3952/4000), so the "sustained" window contained
  **exactly one sample**. The script compared 1 against 13 and printed a conclusion.
- **Rule:** a comparison with a window below a stated minimum must **refuse to answer**, not
  answer weakly. The script now requires >=3 samples per window and otherwise prints
  "NO VERDICT". Same family as F-21 (a control that never fired) — the fix is always to make the
  tool fail loudly rather than to be careful when reading it.
- **Also:** do not assume a transition will occur. It varies across a session; catch it or say
  you did not.

### F-29 · A parser that silently dropped most samples
- **Symptom:** `power_phase_probe.py` reported ANE power 0–14 mW and CPU up to 6.6 W for a run
  where the IOReport counters showed 173 GB of ANE traffic — which looked like a real instrument
  conflict and led me to write up "the standard ANE instruments are blind to Core AI". The probe
  had parsed **14 of ~51** powermetrics samples: its block-splitting regex dropped the rest, and
  the surviving fields did not match `power_coreai.py`'s readings for the same workload.
- **Rule:** a parser must **count what it parsed and compare against what it expected**; a
  silently-partial parse looks exactly like a real signal. Reuse a validated parser instead of
  writing a second one for the same input, and persist the raw text so a disagreement between two
  tools can be adjudicated.
- **Cost:** a wrong conclusion written into the record (corrected in EXP-005). The counter-example
  that caught it was the *other* tool reading the *same* bundle correctly.

### F-30 · Trusted an env var that the tool does not read
- **Symptom:** set `MNEMOPI_DB_PATH` for a "fresh DB" test; the CLI ignored it and wrote to the
  default `~/.hermes/mnemopi/data/mnemopi.db` — **mixing Granite vectors into a table that already
  held a `bge-small` vector**. The recall output still looked sensible (a plausible ranking), which
  is what made it dangerous: a contaminated run that reports a believable answer.
- **Rule:** before using an env var to *isolate* a test, prove it took effect — the tool's own
  output usually reports the path it chose (`mnemopi stats` prints `DB path:`). `MNEMOPI_DATA_DIR`
  is the knob that works; `MNEMOPI_DB_PATH` is read by the library but not the CLI.
- **Also:** the first run's plausible ordering was *not* evidence. Only the clean re-run
  (3 memories → 3 embeddings, one model) counts.

### F-31 · A long run killed the embedder: IOSurface pool exhaustion
- **Symptom:** an MTEB run over 32,659 samples died mid-flight with
  `CoreAIRuntime/NDArray+Pool.swift:77: Fatal error: Failed to allocate storage for NDArray
  with byteCount: 768, sk: ioSurface, st: float16` — a **768-byte** buffer, i.e. the 384-d fp16
  output. Two smaller runs (~5,500 embeddings each) had completed on the same server minutes
  earlier, which is exactly what made it look like a flake.
- **Root cause:** the Core AI Python runtime exposes **no way to release an NDArray**, and the
  outputs are IOSurface-backed. Under sustained load the pool is exhausted and the process aborts.
- **Fix:** the server re-execs itself every N calls (`--restart-every`, default 4000). The
  specialization is cached, so the reload is a few ms, and an HTTP client retries the dropped
  connection. Verified with 12,000 consecutive embeddings (2× the old failure point): 6 recycles,
  server alive, ~60 embeddings/s.
- **Rule:** a long-running inference server needs a plan for runtime resource pools that have **no
  release API** — recycle the process rather than trusting the GC. And **a short run passing is
  not evidence the long one will**: the first two MTEB tasks completed on this exact server.

---

### F-32 · the ANE returns 0.5 for the reranker, *silently and nondeterministically*

> **RESOLVED (EXP-013).** Root cause: the published bundle is a stock macOS/GPU export with an
> in-graph RoPE gather; it compiles to **0 ANE regions** (silent GPU fallback), so the ANE
> delegate produced a constant. Re-authored into the ANE dialect with cos/sin as inputs, the
> graph compiles to **1 full-ANE region** and gates on the ANE at worst |delta| **6.11e-04**
> with all rank groups correct. The analysis below stands; the outcome is fixed.

**Symptom.** Qwen3-Reranker-0.6B scored `0.500000` on pairs that the GPU scores correctly. Not an
error, not a crash: a plausible-looking "the model is uncertain" number. Averaged over 300 queries
it would have looked like a working-but-mediocre reranker.

**Cause — it was never authored for the ANE.** The bundle is a stock **macOS/GPU** export. Per the
zoo's own [`knowledge/compute-units-and-authoring.md`](repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md),
Apple's two modes are *"iOS/ANE = static-shape, BC1S, Conv2d, per-head, fp16-only; macOS/GPU =
dynamic-shape, standard layout, fused, custom kernels."* The ANE dialect requires all of:

- **1×1 `Conv2d`, not `nn.Linear`** — *"Linear falls back off-ANE"*
- **no fp32 anywhere** — *"a single Python float literal creates an f32 buffer and breaks ANE
  residency"*
- **palettized (LUT) weights** for statically-compiled execution (PORTING.md §6: *"blockwise-linear
  int4 is a GPU-only format there"*)
- BC1S layout, per-head sequential attention

The reranker has none of these; the zoo gated it on the GPU delegate and its own recipe calls
`ComputeUnitKind.gpu()`. PORTING.md's rule: *"If you aren't explicitly targeting ANE, target GPU and
move on."*

**Why it reads as 0.5 and not as garbage.** The graph's output is a **2-way softmax** over
{no, yes}. Any numerical failure that zeroes those logits lands on `softmax([0,0]) = [0.5, 0.5]` —
the *exact* "no information" point. A 152k-way softmax would have looked obviously broken; a 2-way
one looks calibrated. The output shape is what disguised the failure.

**It is NONDETERMINISTIC, which is what I got wrong the first time.** I wrote this entry claiming a
constant `0.5` for every pair. Measured across three separate processes:

| run | first call | later calls |
| --- | --- | --- |
| A | `0.5` | `0.5` |
| B | **correct `0.993652`** | `0.5` |
| C | `0.5` | `0.5` |

Consistent with a **partial ANE partition** — part of the graph on ANE, part falling back — where
the boundary varies with specialization/caching. **Consequence: a single gate run cannot catch
this.** Run B would have *passed* a one-shot gate that only scored one pair.

**Fix.** GPU delegate, and gate against `reference.json` — `gate_reranker.py` checks all six pairs
(worst |Δ| 2.23e-04, all rank groups correct). GPU also loads in ~0.9 s vs the ANE's ~17 s.

**The fix we have NOT done, and the honest framing.** The ANE is not incapable here — *we never
re-authored this graph for it.* We did exactly that work for the embedder: `bench/granite_ane_variants.py`
took Granite-97M from off-ANE to **14 ANE regions** by removing three fp32/GPU-isms one at a time
(v0 as-is → v1 softmax in graph dtype → v2 scale as an f16 buffer → v3 pooling without `.float()`).
The same v0→v3 treatment on the reranker is unexplored, and would be the real fix.

- **Rule:** for a new bundle, gate on **every** delegate before choosing one, and **repeat the gate
  across processes** — a nondeterministic failure passes a single-shot gate. And when a model emits
  a suspiciously round number, that is a broken computation, not a calibrated "I don't know". **The
  narrower the output, the better it disguises failure** — a 2-way softmax lands on a *meaningful*
  0.5 where a wide one would land on obvious noise.

---

### F-33 · my reranker server printed "adopted inherited listening socket" but never adopted it

**Symptom.** A 300-query reranking run died at query 180 with `Connection refused`. The server log
showed the recycle firing, then:
```
OSError: [Errno 48] Address already in use
```

**Cause.** `Engine.maybe_recycle()` re-execs the process to recycle its IOSurface pool, passing the
listening fd via the environment. The embed server *adopts* it. My rerank server's `main()` did:

```python
httpd = ThreadingHTTPServer((args.host, args.port), make_handler(engine))   # binds a NEW socket
inherited = os.environ.pop("RERANK_INHERIT_FD", None)
if inherited:
    print(f"adopted inherited listening socket (fd {inherited})", flush=True)   # ...and lied
```

The `print` was real; the adoption was not. Constructing a fresh `ThreadingHTTPServer` binds a new
socket, which fails because the inherited fd still holds the port — so the re-exec'd process died
and the client lost the server mid-run. **The message made it look handled.**

**Fix.** Adopt the socket for real, the way the embed server already did:
```python
sock = socket.fromfd(int(inherited), socket.AF_INET, socket.SOCK_STREAM)
httpd = ThreadingHTTPServer((args.host, args.port), make_handler(engine), bind_and_activate=False)
httpd.socket.close(); httpd.socket = sock
httpd.server_address = sock.getsockname(); httpd.server_activate()
```

**Verification.** With `--restart-every 12`: 30 requests, 2 forced recycles, **0 failures**. Then in
production: `recycles: 1, adoptions: 1`, and the run crossed the boundary that had killed it and
finished.

- **Rule:** this is the **same shape as F-32 and the EXP-009 sweep collision** — a message claiming
  success while the mechanism was absent. A log line is not a test; force the boundary
  (`--restart-every 12`) and count failures.

---

### F-34 · `coreai-build` SIGSEGVs on the re-authored reranker

> **RESOLVED (EXP-013) — and it was NOT an upstream bug.** The trigger is an **in-graph RoPE
> gather** (`RoPECache.gather_cos_sin`). The zoo's authoring rules already say so:
> `compute-units-and-authoring.md:39` — *"RoPE as input: precompute cos/sin outside the graph
> ... in-graph `gather_nd` makes rank-3 -> ANE rejects"*. Passing cos/sin as graph inputs
> takes the compile from exit 139 to exit 0, and the full 28-layer model then compiles to a
> single ANE region. The bisection below is still the record of how it was localised; the
> 'upstream bug' framing was wrong.

**Symptom.** `coreai-build compile` on the re-authored ANE bundle exits **139 (SIGSEGV)** in ~2 s,
no diagnostic, no `.aimodelc`.

```
EXC_BAD_ACCESS (SIGSEGV) — KERN_INVALID_ADDRESS at 0x18
  MetalPerformanceShadersGraph_host  mlir::mps::CanonicalizeCopyWithConstraints::matchAndRewrite
                                     GreedyPatternRewriteDriver → CommonRuntimeCanonicalizationPass
```

**It is a compiler bug, and the controls prove it.** Not ANE-specific (`gpu` and `cpu` crash too),
not size (1 layer crashes, 0 layers compiles), and the toolchain is healthy:

| bundle | result |
| --- | --- |
| embedder (positive control) | exit 0, 1 ANE region |
| published reranker (stock GPU export) | exit 0, **0 ANE regions** |
| re-authored reranker | **exit 139** |

**Bisection** (`--layers` / `--bisect`): 0 layers ✅ → 1 layer ❌ → attention stubbed ✅ → so the
trigger is in a single block's **attention**, and within it **RoPE**:

| 1-layer variant | compile |
| --- | --- |
| RoPE active | exit 139 ❌ |
| RoPE stubbed | **exit 0** ✅ |
| `rotate_half` as `reshape(d/2,2).flip(-1)` (no cat) | exit 139 ❌ |
| `rotate_half` as `torch.roll` | exit 139 ❌ |

**The first bisection got this wrong, and the reason matters.** Apple's `qwen3.py` does
`from ...rope import apply_rope`, so it holds its own reference; patching `rope.apply_rope` is a
**silent no-op**. Every "no-rope" run was really a "with-rope" run, which produced a confident and
completely wrong conclusion ("not RoPE"). The fix is to patch the name in the *consumer's*
namespace. **When monkey-patching a stub, verify the stub actually took effect** — a no-op stub
looks exactly like a negative result.

It is not the `torch.cat` specifically: any implementation of the half-split rotation moves data
across the width dimension, and that is what trips `CanonicalizeCopyWithConstraints`. That is also
why **8 isolated minimal repros all compiled** — none of them contained RoPE.

**Related upstream:** #55 (SIGSEGV in `anePreCompileBinary`, fixed in 3600.82.1) and the zoo's own
*"coreai-build itself SIGSEGVs ... beta compiler bug, size/shape-correlated"*. **This is distinct**:
a different pass, and it reproduces at 1 layer.

- **Rule:** when a compiler crashes, **bisect with controls before believing it is your graph.** A
  positive control (a bundle that compiles) plus a negative one (a published bundle that compiles
  *to zero ANE regions*) is what turns "it crashes" into "the toolchain is fine and this specific
  graph trips a bug". And when the crash is a **segfault rather than a diagnostic**, the compiler is
  failing to legalize something — that is an upstream bug report, not a modelling problem.

---

### F-35 · the zoo's fp32 EmbeddingGemma bundle crashes MPSGraph under sustained ANE load

**Symptom.** Serving the zoo's `embeddinggemma-300m_float32_static.aimodel` on the ANE through an
HTTP server, the process dies mid-corpus with

```
MPSCommandBufferImageCache.mm:1220: failed assertion
  `Internal error: Released a texture not in current cache frame.'
```

and, on a longer run, a hard crash in `MPSAutoCache::GetTempBuffer` /
`MPSAutoCache::ReleaseTempResource` (crash reports `python3.13-2026-09-21-225744.ips` and `-230435.ips`).

**What it is NOT.** Not the model, not the delegate, not a one-off:

| probe | result |
| --- | --- |
| 400 embeddings, ANE delegate, in-process | **survived** |
| 400 embeddings, GPU delegate, in-process | **survived** |
| ~3,000 embeddings via the HTTP server | **survived** |
| ~6,400 embeddings | dies |
| ~9,000 embeddings (with process recycling at 3,000) | **still dies** |

**The likely cause is the dtype.** This bundle ships **float32**, and Apple's authoring rules are
explicit that *"fp32 falls back to GPU/CPU"* and that the ANE's dtypes are fp16/int8/int16. It still
compiles to **full ANE residency** (1 region, 0 GPU, 0 CPU) — so the compiler accepts it — but at
runtime the fp32 path appears to keep staging temporary MPS buffers that are never released.

**Contrast:** our own **fp16** Granite bundle and our **fp16** re-authored reranker both run for
tens of thousands of calls on the same machine with only the documented F-31 recycle. So this is a
property of this bundle, not of the ANE or of our serving code.

**Worked around, not fixed.** Two of the three tasks were completed before the crash
(NanoSciFact and JaQuAD — both reproducing the zoo's CPU numbers to four decimals), and the third
was taken from the zoo's published value. A production port should re-export this model **fp16**
rather than fp32.

**CORRECTION (2026-09-21, from the model card itself): fp16 is NOT a fix — it is unsupported.**

I first wrote that `--dtype float16` was "one flag away", because the zoo's exporter defaults to
fp16. **That was wrong.** Google's own card states:

> *"**NOTE: EmbeddingGemma activations do not support float16.** Please use float32 or bfloat16 as
> appropriate for your hardware."*

So the zoo's fp32 was not an oversight — **fp16 is unavailable for this model**, which is exactly why
they shipped fp32. The "one flag" claim was a plausible inference from the exporter's default that
the model card contradicts. **Check the model card before proposing a dtype change.**

**Resolution — and the paper had it.** Google's paper (arXiv 2509.20354) states both halves:

> *"We run our evaluations with **half-precision weights (bfloat16)**, using the prompt instructions
> detailed in the model card."*
>
> *"We additionally provide quantized versions... **int8 per-block**, and mixed-precision
> per-channel. We obtain these variants by applying **quantization-aware training**."*

and Table 1 of that paper gives the cost:

| precision | MTEB Multi | MTEB Eng | MTEB Code |
| --- | ---: | ---: | ---: |
| bf16 | 61.15 | 69.67 | 68.76 |
| **int8** | 60.93 | **69.49** | 68.70 |
| int4 | 60.62 | 69.31 | 67.99 |

**int8 costs 0.18 on English.** And **int8 is a native ANE dtype** while fp16 is not — so the
supported path is **int8 with Google's QAT checkpoints**
(`google/embeddinggemma-300m-qat-q8_0-unquantized`), not fp16 (impossible) and not raw fp32
(crashes).

**Measured, meanwhile, what does work.** The full corpus on the **GPU** delegate passes:

| task | zoo CPU | ANE | GPU |
| --- | ---: | ---: | ---: |
| NanoSciFact | 0.8638 | 0.8637 ✓ | — |
| JaQuAD | 0.6208 | 0.6205 ✓ | — |
| MIRACL-ja | 0.8246 | *crashed* | **0.8225 ✓** |

So the model is usable now (embedder on the GPU, reranker on the ANE), and the ANE-native fix is the
int8/QAT export. **Three wrong answers preceded this one — fp16 (unsupported), "the zoo was
careless with fp32" (they weren't), and "it's a fundamental dtype mismatch" (int8 resolves it) —
and every one of them was answerable from documents I had not read.**

**And a FOURTH, caught before building it: int8 would not help.** I proposed an int8/QAT export as
"the ANE-native path". Two independent sources in our own repo say otherwise:

- **Our PR #36 / EXP-005** — int8-affine weights fold to dense fp16 before the data-movement step,
  so *"it saves disk but not bandwidth"*: **4.8× slower** (19.48 vs 4.05 ms).
- **The zoo's own w8 recipe notes** — *"the embedding table and **all compute stay fp32** — hence
  only 22% smaller (305 vs 390 MB) and **not faster on the phone** (6.64 / 23.07 ms vs 5.54 /
  20.99)."*

So int8 would trade a *crash* for a *slowdown*, not for a fix. **The correct answer is the one
already measured: this embedder on the GPU, the reranker on the ANE.**

- **Rule:** before building a "fix", grep the project record for the same idea. **Both** times this
  session that I proposed a dtype-level fix for an ANE problem, the answer was already written down —
  once in a paper I had not read, once in our own PR. The cost of checking is a grep; the cost of not
  checking is a build.

**And the token is still needed**, because any of these paths starts from the PyTorch source
(`SentenceTransformer("google/embeddinggemma-300m")`), which is gated. The zoo's compiled bundle is
MLIR and cannot be re-typed.

- **Rule:** *"it compiles to full ANE residency" is not "it runs on the ANE"*. Compile-time region
  counts and runtime stability are separate claims, and only a sustained load test separates them —
  which is exactly the F-31 lesson, one layer deeper. When a bundle is fp32, expect the runtime to
  be the thing that fails, not the compiler.

### F-36 · A self-started second oMLX server took down the production one (user-reported, recorded 2026-10-06)

A past agent session on the Studio started its own oMLX server beside the production one
(the user's live inference path). The collision was bad enough that the Mac needed a
reboot and manual cleanup. Today the same hazard nearly repeated: exploratory HTTP probes
against `:8000` — harmless in effect, but the wrong instinct (experiment *on* production).

- **Rule:** the Studio oMLX server is production infrastructure — never a measurement
  target, never doubled, never fed experiment models. MLX arms use it *as a service*
  (existing port, user-provided key, own window) or run on mini — but mini is M4, so it
  answers mini questions only, never M5 ones.

### F-37 · `powermetrics -t 15000` ran ~4 h, not 15 s — and a no-op "load" arm nearly became a metric (2026-10-06 sudo capture)

Two bugs in one captured window. (1) I passed `-t 15000` to the parallel `powermetrics`
meaning 15 s; `-t` is **seconds**, so the sampler ran until the user interrupted it —
the raw gpu dumps died mid-flush at 65536 B (7–14 complete samples each). The
driver-parsed summary tables survived and are now the primary record; the truncated
txts are kept but are **not** citable sources. Fixed in `sudo_capture.sh` to bounded
`-n` counts. (2) The step-6 "tensorops load" arm was silently a no-op (R8: multi-tile
matmul2d returns zeros on this beta GPUCompiler — `stage4_load.log` validation_failed
on every size), and the run's tail overlapped the user restarting oMLX — its ~70 W
model-load surge landed in the same file. Had we parsed the tail we would have
attributed an oMLX reload to a dead matmul probe.

- **Rule:** bound samplers with sample counts (`-n`), never durations a human must
  interrupt; keep the parsed table beside every raw dump as the primary record; and
  verify the load arm's VALIDATION line before quoting any power reading — a silent
  no-op reports plausible watts.

## Meta-rule
Three of these (F-01/F-02/F-03, F-10, F-13) share one shape: **I formed a plausible
theory and changed things before localising the failure.** Localise first —
print the offending op, read the stderr, measure cold vs warm, run the full scan.

**And the rule that came out of F-01 specifically, which is now mandatory:**
> When you find a bug, **first check whether it has already been reported upstream** —
> issues *and* PRs — before attempting any small-scope fix. F-01 was already diagnosed
> and fixed (PR #2632, numpy#29835) while I was writing a monkey-patch; the patch was
> still useful as a workaround, but the *investigation* was duplicated work, and the PR
> I proposed would have been noise.
>
> Contribute only what is genuinely new. If someone else's minimal reproduction is
> better than ours, ours is not a contribution.

### F-38 · An untracked results directory evaporated during workspace clone (recorded 2026-10-06)

The morning's energy ledger (`results/EXP-023-m5max-energy/` — measurements.tsv + RUN-PLAN
+ 105 s of raw powermetrics txt) lived in an **untracked** directory of the superproject.
When the harness created a git workspace clone (`workspace switch h17-truth-x7`) the
directory was displaced and could not be relocated afterward; raw captures are gone.
Reconstructed the 10-row ledger verbatim from session output into the content repo
(`silicon-ledger/results/EXP-023-m5max-energy/`), with a RECONSTRUCTED provenance header
and this entry. The rebuilt `bench/_power.py` totals cross-check against the surviving
`results/EXP-004-coreai-ane/raw/*.txt`.

> Rule: measurement artifacts land in the content repo (or a tracked path) the moment they
> are born. Untracked = transient. A file that exists only in an untracked directory has
> the durability of a variable in a REPL.

### F-39 · TorchMetalKernel leaks one IOSurface per predict; 16384 per-client cap killed the C7 load batches (2026-10-06)

`bench/na_tiles.py` sustained runs died with Swift fatalError
`CoreAIRuntime/NDArray+Pool.swift:77: Failed to allocate storage … sk: ioSurface`
(three window attempts). Kernel log was decisive: `Perf: Process Python (pid) has
created 12288 IOSurfaces out of a limit of 16384, possible leak?` →
`create_surface error - exceeded client limit (0x4000)`. The leak is ~1 surface per
predict; batches of 90000 predicts blow the cap ~16 s in. Boundary measured:
15000 predicts PASS, 24000 crashes. Two wrong turns owned first: (1) arm payloads
passed to enginemon as argv — harness never ran (invalid window, GPU pinned 338 MHz);
(2) blamed the sudo session before reading the logs — uid and session-port records were
clean. Mitigation (working design): relauncher loop keeps ≤15000 predicts per process
and relaunches inside the rail window; window energy counted over completed tiles,
duty included. Fix = upstream-side: surface-free predict loop in the harness when we
own it; recorded as a TorchMetalKernel 0.4.2 behavior characteristic.

### F-40 · ANE shared events crash Path A by design, not by misuse (2026-10-07, EXP-025)

**Symptom:** attaching a populated `_ANESharedEvents` to an `_ANERequest` on the
in-memory-MIL path SIGSEGVs at `-[…processRequest:…_block_invoke +1524]`, fault addr
0x10 — deterministic, every run. **Wrongly assumed:** that our wrapper construction or
the attach timing was the bug; libane's crash had been filed as "a good bug report, not
documented behaviour." **Actual cause:** consumption is firmware-gated to the Path-B
`intermediateBufferHandle` flow — shared events require **package-backed models
(`ModelTypePackage`)**; the `tmc/apple` Go bindings guard exactly this
(`ErrSharedEventRequiresPackage`), returning an error where the raw framework
null-derefs. **Fix:** build the `.mlmodelc` path (Lane A) instead of debugging Path A;
the primitive itself is sound — GPU `encodeSignalEvent:` crosses the mach-port bridge to
an `IOSurfaceSharedEvent` wrapper in ~62 µs (porttest T2).

- **Rule:** a crash that is deterministic at identical offset *and identical fault
  address* across independent harnesses is platform contract, not your bug — hunt for
  an upstream guard (Meta-rule, applied: the guard existed, we hadn't looked) before
  debugging our own code. Evidence: `results/EXP-025-ane-gpu-sync/` (VERDICT, F11/F14).

### F-41 · `dtrace -c` cannot probe a dlopen'd private framework (2026-10-07, EXP-025)

**Symptom:** `dtrace -c ./harness` probes against `AppleNeuralEngine`-internal methods
(`-[_ANE* …]`) report zero hits while the framework visibly runs. **Wrongly assumed:**
wrong probe predicates or a stripped image. **Actual cause:** `-c` enables probes at
exec time, *before* `main` — the private framework is `dlopen`'d later, so its probes
never activate; and SIP additionally blocks attaching to the `aned` daemon itself, so
the daemon side stays dark. **Fix:** spawn the process first, then attach with
`dtrace -p <pid>` against **our own** process (unprivileged for pid-provider on own
process); keep the inferior alive with an env stop so it doesn't exit before attach
(`ANE_STOP2=1 ANE_REPS=40`, plus the F-40 crash shortening full-mode runs to ~100 ms).

- **Rule:** dlopen'd frameworks need spawn-then-`-p` attach, and own-process dtrace
  answers dispatch questions that daemon attach cannot reach. Recipe + 151-method
  inventory: `results/EXP-025-ane-gpu-sync/docs/TRACE.md`.

### F-42 · Autoreleased options dict died inside the async ANE completion block (2026-10-07, EXP-025 F14)

**Symptom:** under sustained GPU load the eval loop began crashing in the completion
block a delayed reference to the options `NSDictionary` — passes clean at idle, fails
hot. **Wrongly assumed:** an ANE/firmware flake; latency mode was being blamed on the
shared-events phase (F11). **Actual cause:** the options dict was autoreleased and
nothing retained it across the async hop; under load the autorelease pool drained first.
ARC cannot manage objects crossing hand-rolled `objc_msgSend` seams (compare API-063).
**Fix:** statically CFRetained options dict + per-eval request retain in
`results/EXP-025-ane-gpu-sync/harness/ane_bridge_mrr.m`; latency table re-reproduced 2/2.

- **Rule:** anything captured by an ANE completion block must be explicitly retained
  for the request's full lifetime; a bug that appears only under load is a lifetime bug
  until proven otherwise.

### F-43 · "No Xcode toolchain" was the wrong wall — espresso.net is a legacy door (2026-10-07, EXP-025 phase 2)

**Symptom:** phase 1 recorded Path B as blocked: `ANECCompile …
InvalidNetworkSourceFileName`, `Cannot load model.espresso.net`, "coremltools lacks
`MLModel.compile`, no `coremlcompiler`" (pack F11/F16; GAP in VERDICT caveat 2).
**Wrongly assumed:** the blocker was a missing compiler toolchain, so the fix was
presumed to be installing/emitting the package format. **Actual cause:** the public
`+[MLModel compileModelAtURL:error:]` works CLT-only and emits valid 27-era bundles in
<1 s; those bundles (old cached ones included) contain **no `model.espresso.net`** at
all — the legacy `_ANEClient compileModel:`/`loadModel:` door still demands it, so
feeding it any current-format bundle fails at `_ANEEspressoIRTranslator` regardless of
toolchain (API-110…112). The 27 producer moved into `ANECompilerService.xpc`
(MIL→`model.hwx`→aned), which the legacy door never consults.
**Fix:** stop trying to open the espresso door; re-scoped the E2E slice to driving
`ANECompilerService.xpc` / riding the E5 path (`results/EXP-025-ane-gpu-sync/docs/P2-LANE-A.md` §7).

- **Rule:** before declaring a format GAP, verify which producer still emits that
  format on the current OS — a rejected input can mean the consumer is legacy, not
  that the input is missing. Cross-check with a root file-access census
  (`fs_usage`) during a known-good public path.

### F-44 · Even root gets "Operation not permitted" on the aned cache; fs_usage truncates paths (2026-10-07)

**Symptom:** `sudo find /Library/Caches/com.apple.aned` → *Operation not permitted*
despite root; `fs_usage` census lines showed cut-off paths that couldn't be
`open(2)`-ed back verbatim. **Wrongly assumed:** a permissions bug or a typo in the
path; assumed census lines were directly consumable file paths.
**Actual cause:** the aned cache tree is under platform-binary/SIP-style protection
that even root doesn't traverse with `find`; `fs_usage` truncates long path arguments,
so excerpts are evidence but not addresses.
**Fix:** treat `fs_usage` excerpts as the primary record (saved root-owned in
`/tmp/p2_sudo_capture.txt`), quote them with the truncation visible, and don't attempt
follow-ups that require traversing the protected tree; the `model.src`→`model.hwx`
producer chain was established from the census alone (API-113).

- **Rule:** on locked-down macOS, root ≠ omniscient: platform protections defeat
  `find`/`ls` on some system trees; capture behavior-first (fs_usage/dtrace) and record
  truncated paths as-is rather than reconstructing them.

### F-45 — assert the trigger fires before spending the root window (2026-10-07, EXP-026 K3/K4)

**Symptom:** three user-run sudo capture windows produced no `model.src`: each run's
"compile-miss trigger" (MIL tag / weight-byte mutation) reported `load ok=1` and looked
successful, but the compiler service never ran and the sandboxes stayed empty.
**Wrongly assumed:** a successful load of a mutated bundle implies a recompile, and
sed/perl mutations apply as written. **Actual cause:** three stacked misses — (1) tag
`sed`/`perl` patterns with `[]`/`{{}` escaping silently matched nothing (two windows);
(2) the E5 identity layer re-keys on bundle bytes, but the ANE program cache keys
coarser, so even a real identity change may not re-run the compiler (API-121);
(3) minor tooling traps: `/usr/bin/launchctl` does not exist (it is `/bin/launchctl`),
and `log` is a zsh builtin that shadows `/usr/bin/log` in scripts.
**Fix:** trigger recipes must *assert their effect inside the window before sweeping*:
mutate an OP-BEARING MIL constant, verify a new `~/Library/Caches/<proc>/
com.apple.e5rt.e5bundlecache/<OS>/<IDENT>` appears, poll `pgrep -x ANECompilerServi`
until seen, and only then sweep the service temp paths
(`EXP-026 harness/p2b_sudo_capture_v7.sh` pattern; recipe in
`EXP-026 results/p2b_k4_e5bundlecache_identity.txt` §4).

- **Rule:** privileged capture windows are scarce (human-run); gate every step of the
  trigger on an observable assertion, and prefer unprivileged side-effects
  (per-user cache dirs, `pgrep`) as the assertion source. Escaping-sensitive in-place
  edits need a post-edit `grep -q` assertion, not a hoped-for downstream symptom.

### F-46 · Metal tensor sizeAndAlign segfaults with nil strides; creation then demands nil (2026-10-08, EXP-027 NX-A)

- **Symptom:** `tensorSizeAndAlignWithDescriptor:` on M5 Max / macOS 27.0.1 driver
  AGXMetalG17P 360.34.5 SIGSEGVs immediately for a descriptor with dimensions +
  dataType + usage but `strides == nil`.
- **Wrong assumption:** header says `strides` is nullable, so nil is a valid
  "let the driver compute" input.
- **Cause:** asymmetric validation in the driver — the sizeAndAlign path
  dereferences strides unguarded (crash), while `newTensorWithDescriptor:`
  rejects non-nil strides ("Strides should be nil", MTLTensorDomain Code=2).
  The two entry points want opposite inputs for the same field.
- **Fix:** set explicit row-major strides for sizeAndAlign queries; create a
  fresh (strides-nil) descriptor — or use `newTensorWithDescriptor:attachments:`
  with explicit strides for buffer-backed tensors (that path validated OK).
- **Rule:** with brand-new Apple driver APIs, treat "nullable" in headers as
  untrusted until probed per-entry-point; guard first calls to unshipped API
  paths in a throwaway process, and add unbuffered stdout (`setbuf(stdout,
  NULL)`) before probing — a SIGSEGV silently swallows all printf output.

### F-47 · MilAneflow errors take the errInfo struct, not the ctx — two-register returns (2026-10-08, EXP-027 MX)
- **Symptom:** EXP-026 ABI probes crashed or returned prog=NULL with err_size=0 on every calling-convention variant.
- **Wrong assumption:** `milaneflow_error_message_size/copy_error_message` take the context handle; `try_program_from_string` returns a single pointer; last arg is the string length.
- **Cause:** `try_program_from_string/_from_file` return a 16-byte struct in x0/x1 — {program, errorInfo} — and the error exports take the **errorInfo** (libc++ SSO strings at +0x00/+0x18), while the ctx handle is only 16 bytes: the old probes read +0x17 off a 0x10 allocation. Arg3 is not a length: it is the modelPath used to resolve `@model_path` BLOBFILE references (differentially proven by the error texts it produces).
- **Fix:** `dyld_info -disassemble <shared-cache-path>` disassembles shared-cache images that otool-classic refuses to open ("can't open file: ... No such file"); map dyld_info `-exports` offsets onto labels, read the `free_*` functions for struct layouts (they reveal which offsets must be strings), then confirm every slot with per-process differential probes (valid input vs garbage; expected stage-differentiated errors).
- **Rule:** for shared-cache private C APIs the disassembly gives the ABI for free — which registers survive to `retab` tells you the return-struct width, and paired destructors name the offsets of owned memory. Never model an error channel on the primary handle until the disassembly says so.

### F-48 · Variadic objc_msgSend mangled object args; ANE attrs is a plain dict after load (2026-10-08, EXP-027 ES)
- **Symptom:** `+[_ANEModel modelAtURL:key:]` SIGSEGV'd inside `objc_retain` (or threw `-[NSTaggedPointerString scheme]`) when called through a `static id (*msg_id)(id, SEL, ...)` wrapper; identical call with an explicit `((id(*)(id,SEL,id,id))objc_msgSend)` prototype worked.
- **Wrong assumption:** a single variadic msgSend wrapper is ABI-safe for every selector; `modelAttributes` is a rich object exposing `networkStatusList`.
- **Cause:** on this build the wrapper's object args reached the callee corrupted (garbage/tagged-string receiver); explicit per-call function-pointer prototypes pass cleanly. Separately, `_ANEModel.modelAttributes` on 27.0.1 is `__NSDictionary0` pre-load and an immutable plain dict post-load with Capitalized keys (`NetworkStatusList`/`LiveInputList`/`BatchStride`…), so selector traversal raises unrecognized-selector.
- **Fix:** per-call explicit prototypes for objc_msgSend (the pattern the EXP-025 harness already used); `isKindOfClass:NSDictionary` then `objectForKey:` with Capitalized keys; dims come from `LiveInputList[0].BatchStride` (input 301056 B fp16 for 1x3x224x224) — feeding BatchStride-sized IOSurfaces made `mapIOSurfacesWithModel:` succeed (the EXP-026 0x1D was size mismatch, not format).
- **Rule:** with private-framework bridges, never funnel every call through one variadic msgSend cast — the per-call type is the ABI contract; and treat post-load metadata as dictionaries (probe class with `object_getClassName`), not as documented classes.

### F-49 · enginemon subscription + full Metal surface pool = coreai ioSurface fatal (2026-10-08, EXP-027 NX-D)
- **Symptom:** coreai matmul2d load harness (worked 09:50 same day) began dying at load-loop start: `CoreAIRuntime/NDArray+Pool.swift:77: Fatal error: Failed to allocate storage for NDArray with byteCount: 4096, sk: ioSurface, st: float16` — 3/3 wrapped runs, but 2/2 standalone runs passed (median 241 µs floor).
- **Wrong assumption:** the crash was in the wrapper's fork/exec path or a coreai/venv change (coreai-torch 0.4.2 unchanged since Oct 3; execvp sets no limits).
- **Cause:** co-tenant surface saturation — an oMLX server holding ~18% RAM had consumed the Metal surface pool (`ioreg -c IOMetalResource` → 0 instances system-wide); enginemon's per-channel IOSurface-backed subscriptions (any mode; also when running as an *unrelated* concurrent process) are then the last allocation that fails, and coreai's NDArray pool only allocates 4096 B surfaces through that starved path.
- **Fix:** decouple test (monitor in separate process while harness runs standalone → also fatal) proved it is system-level, not inheritance; switched the calibration window child to the MTLBuffer-only MSL harness (`p27_load_msl.m`), which is immune; surface-pool headroom on the Studio is user-managed (oMLX models are unloaded by the user, never by agents).
- **Rule:** when a GPU-path harness passes standalone but fails under *any* concurrent IOReporter, check pool headroom (`ioreg -c IOMetalResource`) and co-tenants (`ps aux -m`) before suspecting either program — the subscriber is often just the straw; prefer MTLBuffer-only test kernels for calibration windows on shared machines.

### F-50 · system-wide single ktrace consumer kills sudo capture windows (2026-10-08, SU/K4)
- **Symptom:** user-run v7 capture script passed its trigger assertions but `fs_usage` printed `ktrace_start: Resource busy` and captured nothing; earlier v1–v6 sudo windows had also produced no model.src.
- **Wrong assumption:** the failure was another missed trigger (F-45 family) and the fix was a better trigger assertion.
- **Cause:** macOS permits one ktrace/kdebug consumer at a time; another session's live `fs_usage` (not visible in the script's own error checks) owns the kernel trace, so a second `fs_usage` dies immediately — and independently, the CoreAI/MPSGraph JIT route compiles ANE in-process and never spawns aned, so no file ever lands in the aned sandbox to be caught by any watcher.
- **Fix:** dropped fs_usage from v8 (pure directory-watcher with per-poll glob re-evaluation); then abandoned the sandbox hypothesis entirely — the client-side cache `~/Library/Caches/coreai-cache` holds every compiled plan user-readable, making sudo unnecessary for this class of capture (see EXP-026 results/p2b_model_src_inventory.txt).
- **Rule:** on shared machines, any capture plan built on fs_usage/kdebug must pre-check consumer exclusivity (quick `fs_usage -w -f filesys -t 1` smoke test before the real window); and before scheduling another sudo window for compiler-internal artifacts, first prove the artifact type actually crosses a process boundary — in-process compilers keep their artifacts in the client cache.
