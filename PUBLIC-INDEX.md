# PUBLIC-INDEX — the experiments in plain words

👉 **Latest round: [WHATSNEW.md](WHATSNEW.md)** — the newest findings with an honest
new-vs-already-public verdict on each.

One line each; the full record (commands, numbers, caveats, raw artifacts)
is in the linked folder. Chronological — this is also the story order.

| Experiment | In one line |
|---|---|
| [EXP-001](results/EXP-001-ane-op-map/) | Which operations the Neural Engine accepts, mapped on the M4 by direct probing. |
| [EXP-002](results/EXP-002-apple-fm-baseline/) | Baseline for Apple's built-in chat model: how fast it answers, and where its time actually goes. |
| [EXP-003](results/EXP-003-minilm-coreml-ane/) | A standard text-embedding model through official tooling: latency, energy, and proof of which chip ran it. |
| [EXP-004](results/EXP-004-coreai-ane/) | Asking Apple's new AI runtime to use the Neural Engine — and catching it quietly using the GPU instead. |
| [EXP-005](results/EXP-005-ane-residency/) | The same model re-authored by hand for the ANE: it lands, and it is faster — plus the discovery that the ANE has two throughput states. |
| [EXP-006](results/EXP-006-local-memory-stack/) | Wiring it together into a working local memory system: ANE embeddings plus an on-device chat model. |
| [EXP-007](results/EXP-007-mteb-retrieval-quality/) | Is the fast embedder actually *good*? Standard retrieval benchmarks, honestly scored. |
| [EXP-008](results/EXP-008-multilingual-retrieval/) | The same quality question in French, because English-only is not good enough. |
| [EXP-009](results/EXP-009-grid-sweep/) | Trading quality for cost: sweeping input lengths from 64 to 1024 tokens and finding the knee. |
| [EXP-010](results/EXP-010-chunk-pooling/) | Testing our own advice — splitting long documents and averaging turns out not to pay. |
| [EXP-011](results/EXP-011-chunk-indexed/) | The fix that *does* work: index the chunks separately, measured. |
| [EXP-012](results/EXP-012-reranker/) | Adding a second-pass reranker closes the ranking gap the embedder could not. |
| [EXP-013](results/EXP-013-ane-reauthor/) | Porting that reranker to the ANE: a mysterious constant 0.5, a compiler segfault, and what each really was. |
| [EXP-014](results/EXP-014-competitive-position/) | An honest stock-take: where this work actually stands against published results. |
| [EXP-015](results/EXP-015-candidate-landscape/) | Which models could plausibly run on the ANE next — a survey with receipts. |
| [EXP-016](results/EXP-016-von-ane/) | A decision model (text classifier) ported to the ANE: 144/144 identical to CPU, 2.7× faster. |
| [EXP-017](results/EXP-017-laya-ane/) | Reproducing the closest published ANE port on our stack — and beating its numbers fairly. |
| [EXP-018](results/EXP-018-jevbench-ane/) | Submitting our ports to the community benchmark, so strangers can disagree with us. |
| [EXP-019](results/EXP-019-correctness-head/) | Giving decision models a second output channel that flags when they are wrong. |
| [EXP-020](results/EXP-020-ane-dma-notch/) | Finding (on the M4) the size threshold where ANE data transfers get slower, and the split that fixes it. |
| [EXP-021](results/EXP-021-ane-weight-budget/) | Discovering the ANE's model-size budget counts compiled files, not the operators we expected. |
| [EXP-022](results/EXP-022-m5max-baseline/) | Moving to the Mac Studio: does the whole instrument suite reproduce on the M5 Max? Mostly yes, with a compiler regression documented. |
| [EXP-023](results/EXP-023-small-llm-ane-pilot/) | First probe of a small language model on the M5's ANE: it lands in 2 regions — with one load-time bug carried forward. |
| [EXP-024](results/EXP-024-engine-attribution/) | Which engine really ran it — and the counters that lie: calibrating the ANE/GPU lenses, and retiring the "UT means Neural Accelerator" myth. |
| [EXP-025](results/EXP-025-ane-gpu-sync/) | The wire between the ANE and the GPU, driven end-to-end with data (500/500, ~123 µs) — and how Core ML actually chooses an engine. |
| [EXP-026](results/EXP-026-ane-kitchen/) | Inside Apple's compiler: the Core AI specialization cache decoded from its own bytes, and the cached plan printed as readable MLIR. |
| [EXP-027](results/EXP-027-nax/) | The M5 GPU's tensor units (NAX), first pass: what they are, how work reaches them, and which signals observe them — and which only pretend to. |
| [EXP-028](results/EXP-028-apple-tracer/) | Apple's own tracer, used fairly: public lane fingerprints, and exactly where the privilege wall sits. |
| [EXP-029](results/EXP-029-nax-crosslane/) | NAX vs the other lanes, measured: 2.26× over the shader path at 4096² with ~2× less energy; the GPU beats the ANE 5–10× on the same GEMMs; and the measurement hazards that make joules lie. |
| [EXP-031](results/EXP-031-ane-perfstats-spy/) | Who zeroes the ANE counters your app sees: entitlement forensics, and why third parties read zero on every path we can forge. |
| [EXP-032](results/EXP-032-pulse-map/) | Finding a per-eval ANE counter that works on the M5 (the official one is dead), and opening the kernel driver's side door without privilege. |
| [EXP-033](results/EXP-033-door-map/) | Mapping that door: openable fleet-wide, sandbox-proof, and ~20× under the daemon hop — with live third-party calls succeeding. |
| [EXP-034](results/EXP-034-full-access/) | Walking through: decoding ANE device properties unprivileged, and naming exactly which check rejects our program submission. |
| [EXP-035](results/EXP-035-chaining-blob/) | The 3 KB argument blob was never the gate — a client-state check upstream is, located by disassembly and a live-handle test battery. |
| [EXP-036](results/EXP-036-side-door-inject/) | Closing the door question with a clean negative: zero weight codes move through the direct path for unprivileged clients — plus the grammar note that prevents the next misread. |
| [EXP-037](results/EXP-037-fp8-nax/) | fp8 on the tensor units: native and bit-exact, yet fp16-parallel at naive tiles — and the compiler-version gate that explains why published numbers claim 7×. |

*Two numbering notes, so citations don't trip.* Two folders share the EXP-023
slot: the small-LLM pilot (linked above) and a reconstructed per-engine energy
baseline in [`results/EXP-023-m5max-energy/`](results/EXP-023-m5max-energy/) —
both are first-class records, and the ledger row spells it out. **EXP-030 is
deliberately unused** in this repo; that id belongs to a sibling project, and
the full id map is in [`results/README.md`](results/README.md).
