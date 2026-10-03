# EXP-006 — the local memory stack: ANE embeddings + on-device LLM

**The original goal, reached.** Small embedding models running locally to power a memory system
(`mnemopi`) — with the embeddings on the Neural Engine and the consolidation LLM on Apple's
on-device Foundation Model. No cloud, no API key, `127.0.0.1` only.

**Run:** 2026-09-20 · macOS 27.0 (26A428) · base M4 (Mac mini, 16 GB) · `mnemopi` from
`~/.omp/plugins/node_modules/@oh-my-pi/pi-mnemopi`

---

## The two slots mnemopi needs

| slot | how mnemopi takes it | what fills it |
| --- | --- | --- |
| embeddings | local `fastembed` ONNX **or** OpenAI-compatible (`MNEMOPI_EMBEDDING_API_URL`) | **our ANE server** — Granite-Embedding-97M, fp16, 1 ANE region, 384-d |
| consolidation LLM | **OpenAI-compatible only** (`MNEMOPI_LLM_*`); no local GGUF | **`fm serve`** — Apple Foundation Models, `/v1/chat/completions`, model `system` |

Both are 384-dimensional on the embedding side, matching mnemopi's `bge-small-en-v1.5` default —
so the vector *shape* matches. The *semantics* do not, so a bank must not mix models (see the
mistake below).

## What works (measured)

```
$ mnemopi stats                      # clean data dir
  Total memories: 0
$ mnemopi store "Core AI needs fp16 to reach the Neural Engine; fp32 forms zero ANE regions." notes 0.8
  Stored: 7e39cad73e3579b8
$ mnemopi recall "neural engine" 3
  0.598  Core AI needs fp16 to reach the Neural Engine; fp32 forms zero ANE regions.   ← correct
  0.224  The local_ai_stack project targets a base M4 Mac mini.
  0.213  The garden needs watering on Tuesdays.                                        ← correct last
```

- **3 memories → 3 rows in `memory_embeddings`** (1:1, one model).
- **0 crash lines.** The bundled `fastembed` path crashes Bun on exit
  (`panic: A C++ exception occurred`, after the work is done) — verified to be that module:
  `MNEMOPI_NO_EMBEDDINGS=1` gives **0** crash lines, the default gives 2. Routing embeddings
  through the HTTP endpoint bypasses it entirely.
- **Consolidation works**: with working memories backdated past the 12 h cutoff
  (`workingMemoryTtlHours ?? 24`, halved), `sleep` reports `status: consolidated`,
  `items_consolidated: 3`, `summaries_created: 1`, and `episodic_memory` goes **0 → 1**.

## What does not (yet): LLM consolidation is unreachable from the CLI

`llm_used: 0`, `method: "aaak"` — a heuristic summarizer, not the LLM. The `fm serve` log shows
**no request** during consolidation, so the call was never attempted.

Cause, in the source:

```ts
// src/core/beam/index.ts
localLlmEnabled: false,                                       // DEFAULT_CONFIG:70
localLlmEnabled: configured.localLlmEnabled ?? DEFAULT_CONFIG.localLlmEnabled,   // :87
```

and the CLI constructs `new BeamMemory({ dbPath: resolveDbPath(context) })` — it never sets that
flag, and **there is no environment fallback for it**. `MNEMOPI_LLM_ENABLED=1` *is* read
(`src/core/local-llm.ts:77`), but the `BeamMemory` gate comes first and defaults to false.

**So enabling the LLM is a host-side job**, not a CLI one: whoever constructs the engine must pass
`config: { localLlmEnabled: true }`. That is precisely the shape of **F-20** (`llmMode=smol but no
tiny/smol model resolved`) — the host wanted an LLM and could not resolve one. `fm serve` is now
verified and ready to be that backend.

## Reproduce

```bash
cd /Volumes/data/local_ai_stack
tools/memory-stack/start.sh                 # starts both servers, prints the env to export
# then, in the shell that runs mnemopi:
export MNEMOPI_DATA_DIR=$PWD/work/mnemopi-ane
export MNEMOPI_EMBEDDING_API_URL=http://127.0.0.1:8799/v1
export MNEMOPI_EMBEDDING_MODEL=granite-embedding-97m
export MNEMOPI_LLM_ENABLED=1 MNEMOPI_LLM_BASE_URL=http://127.0.0.1:1976/v1 MNEMOPI_LLM_MODEL=system
mnemopi store "..." && mnemopi recall "..."
```

## Two mistakes worth recording

**`MNEMOPI_DB_PATH` is not honoured by the CLI.** It silently wrote to the default
`~/.hermes/mnemopi/data/mnemopi.db`, so an intended "fresh DB" test actually **mixed Granite
vectors into a table holding a `bge-small` vector** — the ranking still looked plausible, which is
exactly why it needed checking. `MNEMOPI_DATA_DIR` is the working knob (it resolves
`<dir>/mnemopi.db`), and it reports `Total memories: 0` when genuinely fresh. Logged as **F-30**.

**A plausible-looking result is not a verified one.** The first recall run returned a sensible
ordering *and* was contaminated. The clean re-run gave the same ordering with 3 embeddings for
3 memories — that second run is the evidence.

## Artifacts

- `tools/embed-server/embed_server.py` — OpenAI-compatible `/v1/embeddings` on the ANE
- `tools/memory-stack/start.sh` — brings up the embedding server + `fm serve`
- `tools/enginemon/` — the unprivileged engine monitor used throughout EXP-004/005

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

No records in `measurements.json` are attributable to this experiment.
