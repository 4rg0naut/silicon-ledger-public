# Language policy — the tool fleet's lane discipline (2026-10-11)

Born from the 2026-10 tool audit (165 instruments, `tools/AUDIT-2026-10.md`). The fleet's spread
was never designed — it accreted per experiment. This file freezes the lanes so reuse beats
reinvention. Borrowed shape from baseRT (one engine, one harness, thin per-language bindings):
they collapse languages around a product core; we pin languages per measurement lane instead,
because we are a knowledge base, not a runtime.

## Machine state (from the registry, 2026-10-11)

| language | files | KB | lane | status |
|---|---|---|---|---|
| Python | 82 | 509 | **default**: orchestration, ledger, reports, eval, serving, plumbing | open |
| Objective-C (.m) | 37 | 279 | Metal / CoreML / ANE private-API probes **only** | open, gated |
| shell (.sh) | 32 | 65 | glue: capture windows, build wrappers, pipeline | open, glue-only |
| Swift | 4 | 11 | **frozen** — see below | closed to new |
| Metal (.metal) | 4 | 9 | kernels, always paired with an .m/.py host | open, paired-only |
| C | 4 | 38 | tiny syscall/IO probes (enginemon, canary) | open, tiny-only |
| .h | 1 | 3 | shared bridge headers (ane_bridge.h) | case by case |
| .lldb | 1 | 1 | debugger macros | case by case |

## The rules

1. **Python is the default for everything new.** If a tool's job is orchestration, parsing,
   ledger work, reporting, eval, or serving, it is Python, in `.venv-conv`'s dependency set,
   reusing registered helpers (`bench/_power.py` for powermetrics parsing is the precedent).
2. **ObjC/Metal only for what requires the API in the hand.** A tool earns an .m file only if
   it touches Metal tensor APIs (matmul2d/MetalHLO), private ANE/CoreAI symbols, or
   IOKit/powermetrics structs that no Python route reaches. An .m harness that only shells out
   or parses output is the wrong language — it was written before `_power.py` existed.
3. **shell is glue, not harness.** `bash -n` must pass; a .sh tool may capture windows and
   orchestrate binaries, but parsing loops in awk beyond one line belong in Python
   (`tools/kb_pipeline.sh`, `bench/aot_verify.sh` are the ceiling).
4. **C stays tiny.** Only for probes where the syscall/IO pattern IS the measurement
   (`tools/enginemon/enginemon.c` — IORegistry channel walks; `canary.c`). No C data processing.
5. **Swift is frozen.** New Swift tools need an explicit exception (precedent: Swift-only APIs —
   MetalHLO in `nax_gemm/main.swift`, os-tracer in `p28_coreai_run/main.swift`). The one living
   Swift tool is `tools/granite-runner/` (SwiftPM, ANE residency runner) — kept because it is
   the measurement instrument of EXP-022+, not a style choice. The fold already happened once:
   `bench/mlpower-runner.swift` is superseded by `bench/power_mlcore.py` (same job, policy lane,
   preserved as evidence). No new Swift without naming the API that forced it.
6. **No cross-lane twins.** When a Python route and an .m route cover one capability, the
   registry names exactly one `canonical` (see `verdicts-2026-10.jsonl`); the other carries
   `duplicate`/`superseded` and a pointer. New tool opened? It must declare its lane and
   its canonical relationship in the PR description, and be seeded same-day.

## Enforcement

- `tools/registry.py --check` (pipeline step 1) catches unregistered drift.
- The census (`build_census.py`) re-counts languages every regeneration; a lane whose count
  grows without a verdict entry is visible in `tools/AUDIT-2026-10.md` §1 next rebuild.
- The de-facto venv state is part of the policy's honesty: coremltools/numpy/mteb are currently
  gone from both venvs (census finding 1). Rebuilding the venv restores ~30 tools' full runs;
  until then their smoke verdict is DEPS-BLOCKED, not "broken".
