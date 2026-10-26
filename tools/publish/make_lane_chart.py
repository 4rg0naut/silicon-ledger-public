#!/usr/bin/env python3
"""Generate assets/lane-tf.svg — NAX tensor-lane throughput by input dtype.

Data source (single source of truth): knowledge/ane/16-neural-accelerators.md
"Consolidated lane table v2", Surface 1 cross-arm row @4096^3 (2026-10-26,
loaded-concurrent window — upper bounds; all arms bit-exact maxabs=0;
bare-metal hand-written MSL matmul2d, instrument fp8_ladder.m / lane_arms.m,
EXP-037). Re-run after every doc-16 revision; output is committed and shipped
by publish.sh (assets/ + *.svg are in the keep-set).

    .venv/bin/python tools/publish/make_lane_chart.py
"""
import pathlib

LANES = [
    ("int8  →  i32",  55.2, "#1b7f4d"),
    ("fp8   →  f32",  31.7, "#0f6bd7"),
    ("fp16  →  f32",  30.2, "#7a5cc4"),
    ("fp32  →  f32",  14.0, "#b0563b"),
]
TITLE = "Tensor lane throughput by input dtype — Apple M5 Max (NAX, matmul2d)"
SUBTITLE = ("hand-written MSL · bare-metal · 4096^3 GEMM · TFLOPs, median of loaded-concurrent window "
            "(upper bounds) · every arm bit-exact (maxabs = 0)")
FOOTER = ("source: silicon-ledger EXP-037, consolidated lane table v2 — knowledge/ane/16-neural-accelerators.md "
          "· dispatch floor 5.3-5.4 us · fp8 needs -std=metal4.1 (measured)")

W, H = 860, 330
ML, MR, MT = 150, 40, 66
BAR_H, GAP = 40, 18
MAX_TF = 60.0
PLOT_W = W - ML - MR
PLOT_H = (BAR_H + GAP) * len(LANES) - GAP


def x(tf):
    return ML + PLOT_W * tf / MAX_TF


def build():
    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" role="img" aria-label="{TITLE}">'
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    s.append(f'<text x="{ML}" y="30" font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial" '
             f'font-size="17" font-weight="600" fill="#1f2328">{TITLE}</text>')
    s.append(f'<text x="{ML}" y="50" font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial" '
             f'font-size="11.5" fill="#59636e">{SUBTITLE}</text>')
    for tick in range(0, 61, 10):
        s.append(f'<line x1="{x(tick)}" y1="{MT - 8}" x2="{x(tick)}" y2="{MT + PLOT_H}" '
                 f'stroke="#d8dee4" stroke-width="1"/>')
        s.append(f'<text x="{x(tick)}" y="{MT + PLOT_H + 18}" text-anchor="middle" '
                 f'font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial" '
                 f'font-size="11" fill="#59636e">{tick}</text>')
    for i, (label, tf, color) in enumerate(LANES):
        y = MT + i * (BAR_H + GAP)
        s.append(f'<text x="{ML - 10}" y="{y + BAR_H / 2 + 4}" text-anchor="end" '
                 f'font-family="ui-monospace,SFMono-Regular,Menlo,monospace" '
                 f'font-size="13" fill="#1f2328">{label}</text>')
        s.append(f'<rect x="{ML}" y="{y}" width="{x(tf) - ML:.1f}" height="{BAR_H}" rx="3" fill="{color}"/>')
        s.append(f'<text x="{x(tf) + 8}" y="{y + BAR_H / 2 + 5}" '
                 f'font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial" '
                 f'font-size="13" font-weight="600" fill="#1f2328">{tf:.1f} TF</text>')
    s.append(f'<line x1="{ML}" y1="{MT}" x2="{ML}" y2="{MT + PLOT_H}" stroke="#59636e" stroke-width="1"/>')
    s.append(f'<text x="{ML}" y="{MT + PLOT_H + 42}" font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial" '
             f'font-size="11" fill="#59636e">TFLOPs (trillion multiply-accumulate pairs counted as 2 ops)</text>')
    s.append(f'<text x="{ML}" y="{H - 12}" font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial" '
             f'font-size="10.5" fill="#59636e">{FOOTER}</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def main():
    out = pathlib.Path(__file__).resolve().parent.parent.parent / "assets" / "lane-tf.svg"
    out.parent.mkdir(exist_ok=True)
    svg = build()
    old = out.read_text() if out.exists() else None
    out.write_text(svg)
    print(("wrote " if old != svg else "unchanged ") + str(out))


if __name__ == "__main__":
    main()
