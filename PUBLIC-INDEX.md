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
