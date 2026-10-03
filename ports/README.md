# ports — model surgery lives here, instruments live in `bench/`

Relocated 2026-10-03 (P3 THE ORCHESTRA): files that CHANGE a model into
ANE-legal form are ports; files that MEASURE are bench. Nothing else moved;
`results/EXP-*/README.md` still cite the old `bench/...` paths — those are
historical command lines, correct at run time, deliberately untouched.

| old path | new path |
|---|---|
| `bench/export_laya_ane.py` | `ports/export_laya_ane.py` |
| `bench/export_von_ane.py` | `ports/export_von_ane.py` |
| `bench/export_reranker_ane.py` | `ports/export_reranker_ane.py` |
| `bench/export_granite_fp16_placement.py` | `ports/export_granite_fp16_placement.py` |
| `bench/export_granite_w8_fp16.py` | `ports/export_granite_w8_fp16.py` |
| `bench/convert_encoder_coreml.py` | `ports/convert_encoder_coreml.py` |

Consumers: `bench/laya_ane_bench.py` imports the Laya port (its `sys.path`
now includes `ports/`). Environment for re-bakes: `.venv-conv`
(python3.12 + torch + transformers + coreai-torch), weights under `models/`
(symlink → `/Volumes/HUB/models/silicon-ledger-studio/models/`), and the
`repos/coreai-models` checkout exposed at the ChatDemo path the Laya export
expects (`repos/coreai-kit/Examples/ChatDemo/.build/checkouts/coreai-models`
symlink, machine-local like all bulk). Recipes + hashes: `MODELS.md`.
