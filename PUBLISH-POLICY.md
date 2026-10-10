# What is public, what is private — and why

This mirror is a **friendly distillation** of a private reverse-engineering corpus. The honesty layer
is real and public: every claim carries provenance, and every finding carries a novelty label
(**NEW / EXT / KNOWN**) so nothing known is dressed up as discovered. What is *not* here is the
machine-verbose material and the sources.

## Published
- `bench/`, `tools/`, `schemas/`, `ports/`, `evaluation/` — **the reusable instruments** (in full,
  including `.py`/`.m`), and the join contract with the companion benchmark repo.
- `knowledge/` — the knowledge base: narrative docs **and** the machine-checkable records.
- `results/**` as `.md` / `.json` / `.txt` / `.sh` — every experiment's README, its numbers and its
  text/shell evidence, including the failure corpus.

## Private by design (referenced in prose, deliberately not published)
- the per-experiment **harness sources** — `results/**/harness/*.{m,metal,c,h,py}`;
- the **gzipped raw captures** — `results/**/raw/*.gz` (multi-hundred-MB powermetrics/trace streams);
- `repos/`, `models/`, `data/`, `work/`, `bench-inbox/`, `exp022-raw/` — private clones, model weights
  and scratch;
- `.omp/` — the agent rule files.

So a prose mention of e.g. `harness/aneprobe.m` is a **pointer to a private file**, not a broken
reference. Where a *markdown link* pointed into a private tree, publication rewrites it to this
repo's equivalent (`tools/publish/rewrite_links.py`) and marks it `(source private)`; the link gate
(`tools/publish/check_public.py`) refuses to publish a tree with dangling links.

## The two layers, by audience
1. **Front door** — `README.md`, `WHATSNEW.md`, `PUBLIC-INDEX.md`: what this is, what is new versus
   already known, and how to reuse the instruments.
2. **Receipts** — `knowledge/ane/records/`, `knowledge/ane/openclaims/`, `results/measurements.json`,
   the large `results/**` evidence blobs: the verification layer. It is **verbose on purpose** —
   that is what makes the claims checkable. Read it when you want to verify, not to browse.

**Known web-UI limits in the receipts layer (not defects):** `knowledge/ane/openclaims/claims-emitted.jsonl`
is **1.10 MB**, and GitHub does not render blobs that large in the browser — it offers the raw file
instead. For a readable view of the same thing use [`PUBLIC-OPENCLAIMS.md`](PUBLIC-OPENCLAIMS.md)
(counts, what a claim carries, and how to verify one). The other big evidence blobs
(`results/measurements.json`, the `powermetrics_*.txt` captures) render normally.
