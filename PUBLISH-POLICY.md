# What is public, what is private — and why

This mirror is a **friendly distillation** of a private reverse-engineering corpus. The honesty layer
is real and public: every claim carries provenance, and every finding carries a novelty label
(**NEW / EXT / KNOWN**) so nothing known is dressed up as discovered. What is *not* here is the
machine-verbose material and the sources. The corpus is **vibe-coded** — AI agents draft the prose
and the harness plumbing under human review and a receipts discipline, and this repo says so; what
stays private is the chat logs and the scratch, never the conclusions.

## Published
- `bench/`, `tools/`, `schemas/`, `ports/`, `evaluation/` — **the reusable instruments** (in full,
  including `.py`/`.m`), and the join contract with the companion benchmark repo.
- `knowledge/` — the knowledge base: narrative docs **and** the machine-checkable records.
- `results/**` as `.md` / `.json` / `.txt` / `.sh` — every experiment's README, its numbers and its
  text/shell evidence, including the failure corpus.
- `assets/*.svg` — chart images referenced from the front door (generated, never hand-drawn; e.g.
  `assets/lane-tf.svg` comes from `tools/publish/make_lane_chart.py`).

## Private by design (referenced in prose, deliberately not published)
- the per-experiment **harness sources** — `results/**/harness/*.{m,metal,c,h,py}`;
- the **gzipped raw captures** — `results/**/raw/*.gz` (multi-hundred-MB powermetrics/trace streams);
- `repos/`, `models/`, `data/`, `work/`, `bench-inbox/`, `exp022-raw/` — private clones, model weights
  and scratch;
- the **workroom docs** — `results/CONSISTENCY-PLAN.md`, `results/MORNING-BRIEF.md`,
  `results/TRAINING-PLAN.md`, `results/TRAINING-RESULTS.md`, `results/RESEARCH-WORKFLOW.md`: working
  notes where rewrites get argued out before they land in a published doc. The published tree states
  their conclusions, not the drafts;
- `knowledge/ane/ARCHIVE-MAP.md` — the private archive's file index; published prose cites it
  as `(source private)` where a predecessor hash needs an anchor;
- `.omp/` — the agent rule files.

## Path hygiene
Since 2026-10-26 the published tree carries **no local absolute paths at all**: no `/Volumes/…`
(laptop layout) and no `/Users/…` (account names) anywhere a reader could see them. The publish
step rewrites lab paths to neutral forms (`/data/…` → `/data/…`), the privacy grep in
the pipeline asserts nothing leaked, and the gate refuses to publish a tree that still carries a
path we would have to explain. The only place those literals survive is the machinery itself
(`tools/publish/`), which must quote them to filter them — that directory is deliberately
scrub-exempt, and nothing else is.

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

**Manual housekeeping (not in git):** the GitHub social-preview card is set in repo
Settings → Appearance. `assets/lane-tf.svg` is the intended artwork; GitHub wants a
1200×630 PNG or JPG there, so the owner uploads a render of it by hand.
