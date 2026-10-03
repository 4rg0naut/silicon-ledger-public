# EXP-009 — the grid sweep: quality vs cost from 64 to 1024

**Question.** The graph is a **fixed grid**, and the tokenizer truncates the body to S−2 tokens.
EXP-007 showed S=512 beats S=128 on SciFact (0.685 vs 0.652) but left the shape of the curve
unknown. Where is the knee, and does anything above 512 pay for itself?

**Run:** 2026-09-20 · macOS 27.0 · base M4 · MTEB 2.21.0 · SciFact, `ndcg_at_10`

---

## Result — clean diminishing returns, knee at 256–512

| grid | ndcg@10 | Δ | recall@10 | recall@100 |
| ---: | ---: | ---: | ---: | ---: |
| 64 | 0.59060 | — | 0.7286 | 0.9133 |
| 128 | 0.65176 | **+0.0612** | 0.8040 | 0.9283 |
| 256 | 0.67622 | +0.0245 | 0.8090 | 0.9417 |
| **512** | **0.68546** | +0.0092 | 0.8157 | **0.9450** |
| 1024 | 0.68760 | **+0.0021** | 0.8157 | 0.9450 |

```
ndcg@10
0.70 │                          ╭───────  1024 (+0.002)
0.68 │                     ╭────╯         512  (+0.010)
0.66 │              ╭──────╯             256  (+0.024)
0.64 │        ╭─────╯                    128  (+0.061)
0.60 │  ╭─────╯                           64
     └──┬────┬────┬────┬────┬───▶ grid
        64  128  256  512  1024
```

**Reading it:**

- **64 is badly truncated** — SciFact passages run 150–200 words, so a 64-token grid discards
  most of every document. 0.591 is the floor.
- **The knee is at 256–512.** 256 buys +0.024 over 128; 512 buys only +0.009 over 256.
- **1024 is pointless here**: +0.0021 for 2× the compute, and `recall@100` is identical to 512
  (0.9450) — there is nothing left to find.
- **`recall@100` saturates at 512** (0.9450), which is the number that matters for a two-stage
  pipeline: it says the candidate set is complete.

**Consequence for the memory system: index long documents as separate ~256–512-token chunks.**

> **Correction (see EXP-010).** This section originally recommended *"chunk to ~256–512 and
> **max-pool**"*. That was an assertion this experiment never tested, and **EXP-010 refutes it**:
> pooling chunks into one vector measured **worse** than plain truncation on `ndcg@10` at every
> grid (−0.086 / −0.032 / −0.007 for max-pool, −0.004 / −0.017 / −0.016 for mean-pool). The
> measured curve above is a *truncation* curve — it says nothing about pooling.
>
> What the curve does support is that the knee is at 256–512, and what `recall@100` ≈ 0.945 has
> been pointing at is that the candidates are there but not ranked first — which is the argument
> for **indexing chunks separately** (query matches the best chunk, not a blur of all of them),
> not for pooling them. SciFact's ~200–400-token passages also mean truncation at 512 already sees
> nearly the whole document, so this corpus cannot show chunking's benefit either way.

## Two bugs found while building this — both would have produced a confident wrong answer

**1. The grid was not in the export output path.** Every export `rmtree`'d the same directory, so
only the last grid survived. Four bundles were silently destroyed mid-sweep.

**2. The port collision (this one nearly shipped a false result).** The sweep reused one port,
killing the server between grids. But the embedder **re-execs itself** to recycle its IOSurface
pool, and the inherited listening socket keeps the port bound — so the next grid's server died
with `Errno 48: Address already in use` while the **previous grid's** server kept answering. The
MTEB run then recorded the wrong grid's score under the new grid's name.

It showed up as a **non-monotonic curve** — 256 scoring *below* 64 and 128, which is physically
impossible for the same model with less truncation:

| grid | first sweep (collided) | corrected |
| ---: | ---: | ---: |
| 256 | **0.58727** | **0.67622** |

The fix: **a distinct port per grid**, plus `/health` now self-reports `seq_len` so the sweep
asserts it got the grid it asked for. The corrected run verified each port before measuring
(`port 8964 reports grid S=64 (expected 64)`).

**Rule:** a non-monotonic result in a monotonic parameter is a measurement bug until proven
otherwise. And when a server can restart itself, "kill the server" is not a reliable way to free
its port.

## Caveats

- **Gates were skipped for 64/256/1024** — the per-grid reference fixtures only exist for the two
  published grids (128/512), where the gate passes (cos 0.999995216). For the others a synthetic
  example input was used (`--allow-missing-fixtures`).
- **Cross-grid consistency was verified instead**: the same short text through every grid gives
  **cosine 1.000000** against the S=512 vector, so the graphs agree wherever truncation does not
  differ.
- One task (SciFact), one model, English. The *shape* of the curve should transfer; the absolute
  numbers need not.
- Timings in this sweep are noisy (32–296 s for the same task across grids) because grids ran
  sequentially on a machine whose ANE state varies — see EXP-005 step 7.

## Artifacts

- `bench/granite_ane_variants.py` — exports any grid (`--seq-len`, `--allow-missing-fixtures`)
- `bench/mteb_retrieval.py` — the evaluation
- `tools/embed-server/embed_server.py` — grid-aware, self-reports `seq_len`
- `work/exports/granite-embedding-97m/ane-sweep/v3-s{64,128,256,512,1024}/` — the five bundles
- `~/.cache/mteb/results/granite-embedding-97m-s*/` — raw per-grid results

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
|---|---|---|---|---|---|---|---|---|---|---|
| granite-97m-grid64-ndcg10 | granite-embedding-97m | ANE | — | 64 | ndcg@10 | 0.5906 | ndcg@10 | — | — | ours |
| granite-97m-grid64-recall10 | granite-embedding-97m | ANE | — | 64 | recall@10 | 0.7286 | recall@10 | — | — | ours |
| granite-97m-grid64-recall100 | granite-embedding-97m | ANE | — | 64 | recall@100 | 0.9133 | recall@100 | — | — | ours |
| granite-97m-grid128-ndcg10 | granite-embedding-97m | ANE | — | 128 | ndcg@10 | 0.65176 | ndcg@10 | — | — | ours |
| granite-97m-grid128-ndcg10-delta-over-64 | granite-embedding-97m | ANE | — | 128 | ndcg@10 | 0.0612 | absolute delta over S=64 | — | — | ours |
| granite-97m-grid128-recall10 | granite-embedding-97m | ANE | — | 128 | recall@10 | 0.804 | recall@10 | — | — | ours |
| granite-97m-grid128-recall100 | granite-embedding-97m | ANE | — | 128 | recall@100 | 0.9283 | recall@100 | — | — | ours |
| granite-97m-grid256-ndcg10 | granite-embedding-97m | ANE | — | 256 | ndcg@10 | 0.67622 | ndcg@10 | — | — | ours |
| granite-97m-grid256-ndcg10-delta-over-128 | granite-embedding-97m | ANE | — | 256 | ndcg@10 | 0.0245 | absolute delta over S=128 | — | — | ours |
| granite-97m-grid256-recall10 | granite-embedding-97m | ANE | — | 256 | recall@10 | 0.809 | recall@10 | — | — | ours |
| granite-97m-grid256-recall100 | granite-embedding-97m | ANE | — | 256 | recall@100 | 0.9417 | recall@100 | — | — | ours |
| granite-97m-grid512-ndcg10 | granite-embedding-97m | ANE | — | 512 | ndcg@10 | 0.68546 | ndcg@10 | — | — | ours |
| granite-97m-grid512-ndcg10-delta-over-256 | granite-embedding-97m | ANE | — | 512 | ndcg@10 | 0.0092 | absolute delta over S=256 | — | — | ours |
| granite-97m-grid512-recall10 | granite-embedding-97m | ANE | — | 512 | recall@10 | 0.8157 | recall@10 | — | — | ours |
| granite-97m-grid512-recall100 | granite-embedding-97m | ANE | — | 512 | recall@100 | 0.945 | recall@100 | — | — | ours |
| granite-97m-grid1024-ndcg10 | granite-embedding-97m | ANE | — | 1024 | ndcg@10 | 0.6876 | ndcg@10 | — | — | ours |
| granite-97m-grid1024-ndcg10-delta-over-512 | granite-embedding-97m | ANE | — | 1024 | ndcg@10 | 0.0021 | absolute delta over S=512 | — | — | ours |
| granite-97m-grid1024-recall10 | granite-embedding-97m | ANE | — | 1024 | recall@10 | 0.8157 | recall@10 | — | — | ours |
| granite-97m-grid1024-recall100 | granite-embedding-97m | ANE | — | 1024 | recall@100 | 0.945 | recall@100 | — | — | ours |
| granite-97m-grid256-ndcg10-first-sweep-collided | granite-embedding-97m | ANE | — | 256 | ndcg@10 | 0.58727 | ndcg@10 (first sweep, port-collided — wrong grid's score recorded under 256) | — | — | ours |
| granite-97m-grid256-ndcg10-corrected | granite-embedding-97m | ANE | — | 256 | ndcg@10 | 0.67622 | ndcg@10 (corrected rerun) | — | — | ours |
