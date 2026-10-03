# PROVENANCE — predecessor sources behind the EXP records (append-only)

Appended 2026-10-03 (P5). EXP record bodies are historical and were NOT edited;
this table maps each experiment to the predecessor material that predates the
ledger, as hashed in `knowledge/ane/ARCHIVE-MAP.md` and pinned in
`/Volumes/HUB/archive/manifests/`. Unlisted EXPs (002, 006–012, 014–015, 019–021)
were born ledger-era: their provenance is inside their own records.

| EXP | Predecessor material | Hash pin |
|---|---|---|
| EXP-001 | harness-era op-scan driver + logs: `M4-Partage/local_ai_stack/work/ane_probe/` | `hub-archive`/`local-ai-stack` manifests (`HUB/archive/manifests/`, 2,742 entries for local_ai_stack) |
| EXP-003 | MiniLM export lineage: `local_ai_stack/models/minilm128*.mlpackage`, `work/…/convert` logs | same local-ai-stack manifest |
| EXP-004 | xctrace methodology notes in `knowledge/ane/06` (F-08/F-23/F-24) + `work/gate/` | same manifest |
| EXP-005 | zoo-fork porting doctrine (`work/zoo-fork/PORTING.md`) + zoo-test exports | PORTING.md `7843d13e7a49f4be904b5255a2d3200c81f983aad5637793425cd974b3b9d5d6` (ARCHIVE-MAP) |
| EXP-013 | reranker ANE era on Studio: this repo `work/exports/reranker-ane/` (now HUB-home) + mini-side precursor logs `work/memory-stack/reranker_ane*.log` | `silicon-ledger-studio/work/MANIFEST.sha256` + local-ai-stack manifest |
| EXP-016 | Von author repo clone `work/von-repo/` | local-ai-stack manifest |
| EXP-017 | Laya author repo clone `work/laya-repo/` (README `c9ab5604180d03a89514786b7f60fcd805909cf932a22672c511898a782ad682`) + `models/laya-english/`, `models/laya-multilingual/` | ARCHIVE-MAP + local-ai-stack manifest |
| EXP-018 | JevBench v1.3.0 clone `work/jevbench/` (README `3576568a9f8c6963f5385f33268d86bd138c70815e866be2f05ba981aafaab43`) | ARCHIVE-MAP + local-ai-stack manifest |
| EXP-022 | full M5 capture scratch `/Volumes/data/OpenFox/dev_m5max_re/exp022-raw/` | `exp022-raw/MANIFEST.sha256` — 3486/3486 verified in place 2026-10-03 |
| all | memory/claims lineage of the provenance discipline: `/Volumes/data/OpenFox/Memory_Knowledge/` (AGENTS.md `73ff3f48…c954`) + `Backup/_omp-archive/` (36 files) | `memory-knowledge-MANIFEST.sha256` (1,989), `omp-archive-MANIFEST.sha256` |

OpenClaims spine events carrying these findings: `ORIGIN-001` … `ORIGIN-008`
(claims-emitted.jsonl, emitted span-free 2026-10-03 — cache is mini-side, see
FLEET GAP-3).

Regeneration rule: re-run `tools/archive/inventory.py` + the manifest sweep;
append new rows/dated lines here. Never rewrite existing rows.
