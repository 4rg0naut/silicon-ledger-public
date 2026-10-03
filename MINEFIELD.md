# MINEFIELD — eighteen things that broke, in plain words

Every lesson here cost real time. Each cites its full record (F-number in
`FAILURES.md`, experiment in `results/`). Read it before you debug anything
on the Neural Engine — most of these are not Apple's mistakes, they are
measurement mistakes anyone can make.

**1. A single spot-check can lie to you.** A hand-picked probe said the ANE
cannot do convolutions. The full scan says it does them fine; my parameters
just asked for a variant the compiler routes elsewhere. Use the full scan,
never one convenient probe. (F-10, EXP-001)

**2. "Prefers CPU" is not "cannot do it."** For tiny single-op models the
compiler picks the CPU because moving data costs more than computing. That
is an economics choice about one operation, not a statement about
capability. Only the capability column of a probe means anything. (F-11, EXP-001)

**3. Measure cold versus warm before blaming a cost.** A first launch showed
372 ms of model loading and I called it a permanent 2.4× tax. It wasn't —
the system caches model assets between programs, and the warm run was
fast. Load costs amortise; per-request costs do not. Know which one you
are looking at. (F-13, EXP-002)

**4. A test needs a control that MUST fire.** Our "decisive" contention
test told us a model was not on the ANE — but its positive control (the
same test on a known GPU model) barely registered, so the method could not
detect anything at all. Every row was void. Encode refusal-to-answer in
the tool, not in the operator's good intentions. (F-21, EXP-004)

**5. Fast and consistent timing does not prove which chip ran it.** A model
ran 1.9× faster with 30× tighter variance — surely a third backend? No:
the power rails showed ANE at 0 mW, GPU at 4422 mW. It was a different GPU
schedule. Timing generates hypotheses; only hardware observation is
evidence. (F-22, EXP-004)

**6. Before using an instrument, list everything it can give you.** We
treated one counter table as *the* Neural Engine answer and missed 35 other
tables in the same trace — including one that attributed 54,846 GPU
intervals to our process, decisively. The table you reach for first is the
one you already believe in. (F-23, EXP-004)

**7. A zero from a dead counter is not a negative result.** Our monitor
reported "ANE = 0 mW" — on a frozen channel that reads the same constant
whether the chip works or not. Worse, a counter with "ANE" in its name
turned out to be a free-running clock that ticks 24 million times a second
regardless of load. Before trusting a zero, prove the counter moves at all.
(F-24, EXP-004)

**8. If the compiler finishes suspiciously fast, it did nothing.** A real
Neural Engine build takes hundreds of seconds; ours took 0.87 and reported
success. The graph was never lowered — it fell back to the GPU silently.
Check that your model matches the documented requirements (half precision,
specific layout, 1×1 convolutions instead of linear layers) before blaming
the toolchain. (F-25, EXP-004/005)

**9. Fewer ANE regions can mean BETTER, not worse.** After cleaning the
graph, region count fell 13 → 1 and looked like a regression. Power dropped
4× and latency 3×. Regions count how the graph is *cut*, not how well it
*runs*. Never pair a structural metric with a verdict without runtime
evidence. (F-26, EXP-005)

**10. A wildcard that matches a folder and its file double-counts.** Our
headline region counts were all inflated by exactly one — the glob matched
the region directory *and* the file inside it. The order stayed right, so
every conclusion held, and the error survived for days behind a correct
story. Verify counting patterns against a case whose answer you know.
(F-27, EXP-005)

**11. Refuse to answer from one sample.** A power analysis declared "ANE
power is flat while throughput halves" — from exactly one sample in the
slow window. The tool now says "NO VERDICT" below three samples. An honest
silence beats a confident shrug. (F-28, EXP-005)

**12. A parser that quietly drops most of the input looks exactly like a
real signal.** We "discovered" that standard ANE instruments are blind to
Core AI — actually our parser kept 14 of 51 samples. The fix that caught
it: a second tool reading the same file honestly. Count what you parse,
compare with what you expected, keep the raw text. (F-29, EXP-005)

**13. A long-running server needs a plan for resources the runtime cannot
free.** A 32,659-item run died allocating a 768-byte buffer: the Neural
Engine runtime exposes no way to release output buffers, and two shorter
runs had passed minutes earlier. Now the server recycles itself every few
thousand calls. A short run passing is not evidence the long one will.
(F-31, EXP-005)

**14. A suspiciously round number is a broken computation.** A reranker
scored exactly 0.500 on pairs the GPU scores correctly — not garbage, a
plausible "I'm uncertain". Two-way softmax over dead logits *is* exactly
0.5, which is why it looked calibrated instead of broken. And it was
nondeterministic across processes, so a one-shot gate could pass it. Always
gate every execution path, repeatedly, across fresh processes. (F-32,
EXP-013)

**15. A crash is not your bug until controls say so.** The AI compiler
segfaulted on our re-authored model. Bisecting with a known-good model and
a known-fallback model running in the same session proved the toolchain was
healthy and one specific operation (an in-graph rotation) tripped a
compiler pass. Which it was, we found by bisection — after the first
bisection lied, because the patch silently didn't apply and every "without
it" run was secretly a "with it" run. Verify your stub actually took
effect. (F-34, EXP-013)

**16. A log line claiming success is not a test.** Our server printed
"adopted inherited listening socket" and never adopted it — died on the
next recycle, mid-run. The print was real; the mechanism was not. Force
the boundary on a small scale and count failures; the message can lie,
the request count cannot. (F-33, EXP-012)

**17. Version-chasing is the cheapest way to lose a day.** A conversion
failure was "fixed" by downgrading PyTorch, then Transformers — two
downgrades in an isolated environment built for a reason we later proved
false — before checking the actual error: NumPy 2.4 changed one `int()`
behaviour. Read the error before changing versions. (F-01/02/03, EXP-003)

**18. Write the error to a file before you decide it is noise.** The most
expensive mistake in this log is hiding suppressed `stderr` — a tool
printed nothing, we assumed silence meant health, and the real failure
surfaced hours later two layers away. Capture everything, decide later.
(F-07; pre-EXP record — FAILURES.md is the full trace here)

---
*The meta-lesson, learned three separate times: a method that cannot fail
loudly is not a method. Every fix above ends the same way — the tool
itself now refuses, counts, or verifies, so the next reader (including us)
cannot misuse it.*
