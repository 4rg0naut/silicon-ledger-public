# Merge plan — the moment the quiet capture lands

**Dry-run verified 2026-10-06:** `build_measurements.py` default mode is byte-identical
(hash `2b653e5e…` stable). Note: `--apply-new` will also add ~27 historically pending M4-era
ids (granite97m-*, grid-*, von-ane-v*, etc. — curated in ROWS, never applied). That is
expected and harmless, but state it in the commit/PR note so the ledger growth isn't a
surprise.

Rows go into `bench/build_measurements.py` ROWS (22-field order:
`id, model, checkpoint, params_m, runtime, placement, dtype, seq_len, regions, benchmark,
split, scope, tiers, metric, value, unit, latency_ms, latency_unit, hardware, provenance,
date, command`), then `--apply-new`, then `results_table.py` regenerates SUMMARY.
M5 = `"Apple M5 Max (h17g), 128 GB"`. No value may be filled except from the cited raw file.

| new row id | value ← | latency_ms ← | command |
|---|---|---|---|
| `m5-minilm-all-rate` | `power_mlcore_run.log` "inferences … emb/s" (ALL) | (mean) 1000/rate | `bench/power_mlcore.py --seconds 20` |
| `m5-minilm-cpu-only-rate` | same log (CPU_ONLY) | 1000/rate | same |
| `m5-minilm-all-gpu-power-mean` | `power_ALL.txt` powermetrics GPU mean | — | same |
| `m5-minilm-cpu-only-gpu-power-mean` | `power_CPU_ONLY.txt` mean | — | same |
| `m5-minilm-all-energy-per-embedding` | mJ = mean_gpu_mW/1000/rate (CPU rail ALSO in raw once root; pick rail stated in row scope) | 1000/rate | same |
| `m5-minilm-cpu-only-energy-per-embedding` | ditto CPU_ONLY | 1000/rate | same |
| `m5-minilm-energy-per-embedding-ratio` | cpu/ane(=gpu) ratio | — | derived, mark derived-in-scope |
| `m5-granite-ane-gpu-power` | `power_coreai_run.log` neuralEngine rail table | lane median_ms | `bench/power_coreai.py --bundle …/granite97m_fp16_s128.aimodel --iters 800` |
| `m5-granite-gpu-gpu-power` | same, gpu lane | median_ms | same |
| `m5-granite-cpu-gpu-power` | same, cpuOnly lane | median_ms | same |

Placement notes (pilot-established, must appear in row scope strings):
- MiniLM rows: `placement=gpu` for the ALL lane (pilot ANE-DCS duty 0% — M4 name "ANE path"
  does NOT transfer; see `pilot/FINDINGS.md`).
- Granite rows: placement claim = whatever the rail pattern settles (EXP-022 thread 2 / S4):
  ANE rail high on neuralEngine & idle on cpuOnly → ANE; GPU rail high instead → GPU fallback.
  Quote `power_coreai` interpretation table, do not guess.
- All rows dated by capture (`meta.txt` date), provenance `ours`, quiet-window stated in
  scope (oMLX off per meta.txt check + FLEET dated line to be appended).

Extra artifacts routed elsewhere (not ROWS): `eng_list_priv.txt` (AMC-under-root →
knowledge/ane/10), `cal_*_priv.jsonl` + `powermetrics_gpu_*.txt` (EXP-024 arm A matrix +
GPU-NA verdict), `stage4_load.log` (load accounting).
