# Environment record — the protocol every result was produced under

Comparability depends on this file. If any row changes, results are **not**
directly comparable and the experiment should be re-run and recorded as a new
`EXP-`.

| Component | Version |
| --- | --- |
| Machine | Apple **M4** (Mac mini, `Mac16,10`), **16 GB** RAM |
| OS | **macOS 27.0** (build 26A428) |
| Xcode | **27.0** (27A266a) — Command Line Tools alone were *insufficient* |
| Python | 3.13.15 (uv-managed) |
| coremltools | 9.0 |
| torch (`.venv-conv`) | 2.7.0 |
| transformers (`.venv-conv`) | 4.57.6 |
| coreai-torch (`.venv`) | 0.4.2 (with torch 2.13.0) |
| numpy | 2.5.3 |
| `fm` (Foundation Models CLI) | `/usr/bin/fm`, model `system` |
| ane-probe | commit `c8e4600` |
| coreai-kit | commit `bebe09a` |
| container | 1.4.1 |

## Why two virtualenvs
Apple's two converters disagree on PyTorch versions, so they cannot share one env:

- **`.venv`** — general stack. `coreai-torch` 0.4.2 (Core AI path, requires torch ≤ 2.13),
  torch 2.13.0, gliner, gliner2, zvec, pycozo, duckdb, onnx/onnxruntime.
- **`.venv-conv`** — Core ML conversion + benchmarking. `coremltools` 9.0 is only
  *tested* against torch 2.7.0, so this env is pinned to torch 2.7.0 + transformers 4.57.6.

## Protocol rules (learned the hard way — follow these to keep results comparable)

0. **`coremltools==9.0` is incompatible with `numpy>=2.4`** (`int()` lowering raises
   `TypeError: only 0-dimensional arrays…`). Upstream fixed it in PR #2632 but the fix is
   **not in the 9.0 PyPI release**; `coremltools 9.1.dev1` + numpy 2.5.3 was verified here
   to convert the unpatched model fine. Our `.venv-conv` therefore either pins
   `numpy<2.4` or uses the trace-friendly embeddings patch. NumPy's change is intentional
   (numpy#29835) — do **not** patch NumPy.

1. **Core ML conversions must use `convert_to="mlprogram"`.** The legacy
   `neuralnetwork` format *never* uses the ANE. Precision is `FLOAT16`.
2. **ANE activity is read from the Instruments `Core AI` template**, table
   `ane-hw-intervals` ("Denotes an interesting period of activity in the ANE").
   It is **machine-wide, not per-process** — always run a CPU-only control so the
   attribution is defensible.
3. **`xctrace` hangs forever on the `Foundation Models` template without
   `--no-prompt`** (an unanswerable privacy prompt in a headless shell).
4. **Do not rely on `xcode-select`**; export
   `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` in every script.
5. **Power comes from `powermetrics --samplers ane_power,gpu_power,cpu_power -i 500`**
   (root required) and reads whole-system rails. Run on an **idle** machine, and
   never compare a power run taken while something else was working.
6. **Warm the model before timing.** Core ML pays an ANE program load on first
   inference; Apple's model assets are cached OS-wide across processes, so a
   cold number is a property of the cache, not the model.

## Second reference machine — Apple M5 Max (from EXP-022 onward)

Everything above this section describes the **M4** machine and is unchanged.
M5 Max rows are a separate comparability universe: they join the ledger on the
`hardware` axis (`Apple M5 Max (h17c), 128 GB` — join key uses the CoreAI device
string `h17c`, the compile-target identity per arXiv 2606.22283 Ch24 / `knowledge/ane/10`
Q8; the IOReport-visible board string `h17g` is the coarse runtime identifier, not the
ledger key) and on the bench fingerprint
(`bda452aabd60bf26`) — never rank an M4 number against an M5 number.

| Component | Version |
| --- | --- |
| Machine | Apple **M5 Max** (Mac Studio, `Mac17,14`), 18 CPU (6P+12E), 40-core GPU, **128 GB** |
| OS | **macOS 27.0** (build 26A428) — same build as the M4 machine |
| ANE identifiers | board `h17g` (M4 was `h16g`); API-visible ANE core count 16 on both (compiler per-die count is 8 / 32 by the HAL suffix sequence base=4 g=8 s=16 c=32 d=64 — arXiv 2606.22283 Ch24, see `knowledge/ane/10` Q8; CoreAI device string is `h17c`); `_ANE` private API surface unchanged (`EXP-022 raw/ane-probe.txt`) |
| Benchmark suite | `silicon-ledger-bench` v0.1 (public), reference record `examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json` |
| Xcode | 27; `coreai-build` from the Metal Toolchain MobileAsset mount (`aimodelc` in Xcode itself refuses on this machine) |
| Swift package deps (`tools/granite-runner`) | coreai-kit via **relative** local path `../../repos/coreai-kit` @0.4.2 (absolute machine path removed 2026-10-08, review #23). `Package.resolved` updated same day: swift-collections 1.6.0→**1.7.1**, swift-huggingface 0.11.0→**0.13.0** (resolved during the `tools/granite-runner` move; earlier committed granite numbers predate the bump — re-run the correctness gate on any new citation). |
| ANE telemetry | **not** `enginemon` (its M4 `AMC Stats`/`PMP` groups do not exist on M5) and **not** Instruments `ane-hw-intervals` (0 under confirmed load, same blind spot as M4). Live signal: **PMP0 `DCS BW` residency histogram, "ANE" lane**, via `exp022-raw/bin/ssample` (built on the MIT SiliconScope library). Power rails batch in a slow regime — per-op M5 energy rows are declared gaps, never zeros |

**The structural rule for this machine:** the agent runs **locally** (oMLX), so agent
inference is GPU load on the machine under test. Any measurement window requires the
agent and oMLX stopped — enforced by scheduled captures with a load-guard, never by
"the machine looks idle mid-session". Contamination is quantified in
`EXP-022-m5max-baseline/README.md` (gpu_copy 380.5 → 59–85 GB/s while generating).
