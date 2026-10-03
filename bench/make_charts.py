#!/usr/bin/env python3
"""The picture: where the stack stands, what is on the ANE, and what is NOT measured.

Every number here is traced to a recorded experiment or a cited published source. Nothing is
extrapolated. The point of the figure is to make the *gaps* as visible as the results, because the
gaps are where the next gains are.

usage:
    .venv/bin/python bench/make_charts.py     -> work/charts/*.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "charts"

# colours: ours / published baseline / measured-by-us-but-not-ours
C_OURS, C_PUB, C_MEAS, C_GAP = "#1f6feb", "#8b949e", "#d29922", "#da3633"

# ---------------------------------------------------------------- data
# SciFact ndcg@10. source noted per row; all "ours"/"measured" rows are in results/EXP-00x.
STANDING = [
    ("all-MiniLM-L6-v2 (22M)", 0.64508, C_PUB, "published"),
    ("ours: chunk-indexed S=128", 0.65176, C_OURS, "EXP-011"),
    ("ours: whole-doc S=512", 0.68546, C_OURS, "EXP-009"),
    ("ours: whole-doc S=1024", 0.68760, C_OURS, "EXP-009"),
    ("bge-small-en-v1.5 (33M)", 0.71273, C_PUB, "published"),
    ("bge-base-en-v1.5 (109M)", 0.73763, C_MEAS, "EXP-014"),
    ("ours: retriever + ANE reranker", 0.75860, C_OURS, "EXP-013"),
    ("bge-base + our reranker", 0.77204, C_MEAS, "EXP-014"),
]

# the reranker's own contribution, same reranker both arms
LIFT = [
    ("our retriever\n(97M, ANE)", 0.67923, 0.75860, C_OURS),
    ("bge-base\n(109M, CPU)", 0.73763, 0.77204, C_MEAS),
]

# what actually runs on the Neural Engine today
ANE = [
    ("Embedder (Granite-97M)", 1, "EXP-009/011"),
    ("Reranker (Qwen3-Reranker-0.6B)", 1, "EXP-013"),
    ("LLM (Apple fm, 3B)", 1, "EXP-002"),
    ("Multilingual embedder", 0.4, "EXP-008 — measured, weak"),
    ("Energy measurement", 0.0, "NOT DONE"),
    ("Throughput under load", 0.0, "NOT DONE"),
    ("Second-task retrieval", 0.0, "NOT DONE"),
    ("Second-language retrieval", 0.3, "EXP-008 only"),
]

# the measurement gaps
GAPS = [
    ("retrieval: 1 task (SciFact)", 0.10),
    ("languages: 1 measured (EN)", 0.25),
    ("energy: never measured", 0.0),
    ("latency: median only, no p95", 0.35),
    ("memory / index size", 0.20),
    ("cross-harness: verified", 0.90),
    ("ANE gate: cross-process", 0.90),
    ("reranker: 1 candidate tried", 0.15),
]


def standing(ax):
    names = [s[0] for s in STANDING]
    vals = [s[1] for s in STANDING]
    cols = [s[2] for s in STANDING]
    y = range(len(names))
    ax.barh(list(y), vals, color=cols, height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0.60, 0.80)
    ax.set_xlabel("SciFact ndcg@10", fontsize=9)
    ax.set_title("Where we stand — we are NOT ahead", fontsize=11, fontweight="bold")
    for i, v in enumerate(vals):
        ax.text(v + 0.002, i, f"{v:.4f}", va="center", fontsize=8)
    ax.axvline(0.73763, color=C_GAP, ls="--", lw=1, alpha=0.7)
    ax.text(0.7385, len(names) - 0.4, "bge-base", color=C_GAP, fontsize=7, rotation=90, va="bottom")
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)


def lift(ax):
    x = range(len(LIFT))
    w = 0.34
    for i, (name, base, rer, col) in enumerate(LIFT):
        ax.bar(i - w / 2, base, w, color=col, alpha=0.45, label="retriever alone" if i == 0 else None)
        ax.bar(i + w / 2, rer, w, color=col, label="+ same reranker" if i == 0 else None)
        ax.annotate("", xy=(i + w / 2, rer), xytext=(i - w / 2, base),
                    arrowprops=dict(arrowstyle="->", color="black", lw=1.4))
        ax.text(i, max(base, rer) + 0.012, f"+{rer - base:.4f}", ha="center",
                fontsize=10, fontweight="bold")
        ax.text(i - w / 2, base - 0.016, f"{base:.4f}", ha="center", fontsize=7.5)
        ax.text(i + w / 2, rer + 0.003, f"{rer:.4f}", ha="center", fontsize=7.5)
    ax.set_xticks(list(x))
    ax.set_xticklabels([l[0] for l in LIFT], fontsize=9)
    ax.set_ylim(0.62, 0.83)
    ax.set_ylabel("SciFact ndcg@10", fontsize=9)
    ax.set_title("The reranker does real work — and helps our\nweaker retriever more", fontsize=11,
                 fontweight="bold")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)


def ane(ax):
    names = [a[0] for a in ANE]
    vals = [a[1] for a in ANE]
    cols = [C_OURS if v >= 0.9 else (C_MEAS if v > 0 else C_GAP) for v in vals]
    y = range(len(names))
    ax.barh(list(y), vals, color=cols, height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0, 0.5, 1])
    ax.set_xticklabels(["none", "partial", "done"], fontsize=8)
    ax.set_title("What is actually on the Neural Engine", fontsize=11, fontweight="bold")
    for i, (n, v, src) in enumerate(ANE):
        ax.text(1.02, i, src, fontsize=6.5, va="center", color="#555555")
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)


def gaps(ax):
    names = [g[0] for g in GAPS]
    vals = [g[1] for g in GAPS]
    cols = [C_OURS if v >= 0.8 else (C_MEAS if v > 0.2 else C_GAP) for v in vals]
    y = range(len(names))
    ax.barh(list(y), vals, color=cols, height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0, 0.5, 1])
    ax.set_xticklabels(["hole", "partial", "covered"], fontsize=8)
    ax.set_title("Coverage of the evaluation — the holes", fontsize=11, fontweight="bold")
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)



def candidates(ax):
    """The 10 candidates: ANE availability is the binding constraint, not quality."""
    # (name, ane_status 0=nothing 1=recipe 2=bundle, multilingual?, note)
    C = [
        ("Granite-Embedding-97M-Multilingual-R2", 2, True,  "ours — incumbent"),
        ("EmbeddingGemma-300m",                   2, True,  "bundle; best EN+JA in zoo"),
        ("Qwen3-Embedding-0.6B",                  2, True,  "bundle; LAST of 3 in zoo"),
        ("Qwen3-Reranker-0.6B",                   2, True,  "bundle; OUR reranker"),
        ("ColModernVBERT",                        2, False, "bundle; English only"),
        ("Nemotron-3-Embed-1B",                   1, True,  "exporter+gates, no bundle"),
        ("BAAI/bge-m3",                           0, True,  "nothing — zoo has no BGE"),
        ("bge-reranker-v2-m3",                    0, True,  "nothing — no BGE at all"),
        ("intfloat/multilingual-e5-large",        0, True,  "nothing — no recipe"),
        ("Snowflake/arctic-embed-l-v2.0",         0, True,  "nothing — no recipe"),
        ("jinaai/jina-embeddings-v3",             0, True,  "nothing; LoRA+NC licence"),
        ("sentence-transformers/LaBSE",           0, True,  "nothing — no recipe"),
    ]
    names = [c[0] for c in C]
    status = [c[1] for c in C]
    y = range(len(names))
    cols = [C_OURS if s == 2 else (C_MEAS if s == 1 else C_GAP) for s in status]
    ax.barh(list(y), status, color=cols, height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels([f"{c[0]}{'' if c[2] else '  (EN only)'}" for c in C], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 2.6)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["nothing —\nwe'd write it", "recipe only\n(needs port)", "bundle\nexists"],
                       fontsize=8)
    ax.set_title("The 10 candidates — availability is the binding constraint",
                 fontsize=11, fontweight="bold")
    for i, c in enumerate(C):
        ax.text(2.05, i, c[3], fontsize=6.5, va="center", color="#555555")
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)


def multiling(ax):
    """The zoo's own multilingual head-to-head -- and the hole: our model is not in it."""
    tasks = ["NanoSciFact\n(EN)", "JaQuAD\n(JA)", "MIRACL-ja\n(JA)"]
    series = {
        "EmbeddingGemma-300m": [0.864, 0.621, 0.825],
        "Nemotron-3-Embed-1B": [0.765, 0.616, 0.862],
        "Qwen3-Embedding-0.6B": [0.687, 0.570, 0.792],
        "Granite-97M (OURS)":  [None, None, None],
    }
    cols = [C_OURS, C_MEAS, C_PUB, C_GAP]
    x = range(len(tasks))
    w = 0.2
    for k, (name, vals) in enumerate(series.items()):
        offs = (k - 1.5) * w
        real = [v if v is not None else 0 for v in vals]
        ax.bar([i + offs for i in x], real, w, color=cols[k],
               label=name + ("  ← NOT MEASURED" if vals[0] is None else ""),
               hatch="//" if vals[0] is None else None)
        for i, v in enumerate(vals):
            if v is None:
                ax.text(i + offs, 0.02, "?", ha="center", fontsize=11, color=C_GAP,
                        fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(tasks, fontsize=8)
    ax.set_ylabel("nDCG@10", fontsize=9)
    ax.set_ylim(0, 1.0)
    ax.set_title("Multilingual quality (the zoo's own head-to-head)\n"
                 "— and the hole: OUR model was never in this comparison",
                 fontsize=11, fontweight="bold")
    ax.legend(fontsize=7.5, loc="upper right")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    standing(axes[0][0])
    lift(axes[0][1])
    ane(axes[1][0])
    candidates(axes[1][1])
    fig.suptitle("local_ai_stack — the whole picture, 2026-09-21\n"
                 "every bar traced to a recorded experiment; published rows labelled",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    p = OUT / "stack_overview.png"
    fig.savefig(p, dpi=140)
    print(f"  wrote {p}")

    # the candidate / availability picture, its own figure (it is the decision surface)
    fig3, axes3 = plt.subplots(1, 2, figsize=(16, 7))
    candidates(axes3[0])
    multiling(axes3[1])
    fig3.suptitle("Candidate landscape — what can actually run on the ANE, and what quality is "
                  "known", fontsize=13, fontweight="bold")
    fig3.tight_layout(rect=(0, 0, 1, 0.94))
    p3 = OUT / "candidates.png"
    fig3.savefig(p3, dpi=140)
    print(f"  wrote {p3}")

    # a second, single-purpose figure: the ANE port story.
    # NOTE: the first version drew the status text INSIDE the bars -- and three of the four bars are
    # zero-height (those stages produced no ANE region at all), so the text was invisible. Put the
    # annotations on their own row instead.
    fig2, ax = plt.subplots(figsize=(12, 5.5))
    stages = ["published\nbundle", "re-authored\n(1st attempt)", "re-authored\n+ [x,-x] norms",
              "re-authored\n+ RoPE as input"]
    regions = [0, 0, 0, 1]
    status = ["exit 0, 0 ANE regions\n(silent GPU fallback)",
              "SIGSEGV\n(in-graph RoPE gather)",
              "1 layer compiles,\n28 layers SIGSEGV",
              "exit 0, 1 ANE region\nGATE PASS, 6.11e-04"]
    cols = [C_GAP, C_GAP, C_MEAS, C_OURS]
    # ONLY the real residency. No decorative frame bars -- the first version had them and they made
    # every stage look like it reached the ANE, which is the opposite of the truth.
    ax.bar(stages, regions, color=cols, width=0.6)
    for i, r in enumerate(regions):
        if r == 0:
            ax.plot(i, 0, marker="x", color=cols[i], markersize=13, markeredgewidth=3)
    for i, st in enumerate(status):
        ax.text(i, -0.34, st, ha="center", va="top", fontsize=8.5, color=cols[i],
                fontweight="bold")
    ax.set_ylim(-1.15, 1.25)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["no ANE region", "1 full ANE region"])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_title("The ANE port, stage by stage — every stage before the last produced NO ANE region",
                 fontsize=12, fontweight="bold")
    p2 = OUT / "ane_port_story.png"
    fig2.tight_layout()
    fig2.savefig(p2, dpi=140)
    print(f"  wrote {p2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
