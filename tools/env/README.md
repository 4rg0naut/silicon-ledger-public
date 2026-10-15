# Python environments — state after 2026-10 rebuild

**`.venv-conv` is THE canonical tool environment.** Everything new runs on it (the smoke driver,
the registry, serving, eval). Rebuilt 2026-10-11 after the audit found coremltools/mteb/requests/
matplotlib/pandas silently gone: installed against a constraint file pinning torch/numpy/
transformers/tokenizers/scipy, then the full freeze was pinned to `requirements-2026-10.txt`
(87 packages) so the September failure mode — silent dependency rot — cannot repeat unnoticed.

**`.venv` is deprecated legacy.** It is hollow (even numpy is missing). It is NOT deleted (nothing
in this lab is). Its surviving purpose: some old usage docstrings still say `.venv/bin/python` —
readers should substitute `.venv-conv/bin/python`. Rebuild it only if some tool genuinely needs a
second isolated environment; until then, one env, one freeze file.

## Known version-currency warnings (measured at install, 2026-10-11)

| package | installed | validated to | consequence |
|---|---|---|---|
| torch | 2.14.1 | coremltools tested ≤2.7.0 | conversion may drift — always gate numerically against reference pairs |
| torch | 2.14.1 | coreai-torch validated ≤2.13.0 | warning on every TorchConverter import; EXP-027/029 routes may differ from their September runs |
| scikit-learn | 1.9.1 | coremltools conversion API ≤1.5.1 | sklearn conversion API disabled (unused by this fleet) |

These are why the reranker repackage must show a before/after score comparison, not just a
"it loaded". Recorded results stay untouched (RULES 2); new evidence carries its environment stamp.

## Rebuild recipe

    python3.12 -m venv .venv-conv
    .venv-conv/bin/pip install -r tools/env/requirements-2026-10.txt

Then verify: `.venv-conv/bin/python -c "import coremltools, mteb, torch, coreai_torch"` and
`sh tools/kb_pipeline.sh` plus `tools/audit/smoke.py`.
