# EXP-023-m5max-energy — M5 Max per-engine energy baselines (reconstructed ledger)

Two directories share the EXP-023 slot in this repo (see the namespace note in
[`../README.md`](../README.md)): `EXP-023-small-llm-ane-pilot` (the reranker pilot
on M5 Max) and this one, the **first per-engine per-unit energy baselines on the
M5 Max** (sudo `powermetrics -n` capture).

The 10-row ledger here was **reconstructed verbatim from the session transcript
on 2026-10-06** after an untracked superproject `results/` directory was
displaced during workspace-clone creation; the raw powermetrics captures were
lost (F-037). No rails were fabricated — the unattributed idle total is logged
as such (F-036).

- `measurements.tsv` — the reconstructed ledger (canonical artifact of this dir)
- `RUN-PLAN.md` — arms, constraints honored, and the incident record

Twin rows in `results/README.md` reference both directories.
