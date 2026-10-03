#!/usr/bin/env python3
"""Train a decision model: ModernBERT-base + marker-pointer head, on typed-decisions.

The head and the sequence format are **Laya's**, reused verbatim, so whatever this produces exports
to the ANE through the pipeline we already built and measured (`export_laya_ane.py` ->
`coreai-build` -> `aot_verify.sh` -> `latency_protocol.py`).

Design decisions, each with a reason:
  * **Base, not Large.** `verdict-2.0` stopped at Base deliberately: their pre-registered shipping
    gate was dev acc >= 0.760 and Brier <= 0.120, Base delivered 0.785/0.0639 and had converged.
    Large needs 8-bit AdamW + gradient checkpointing to fit 6 GB at all. We start where they landed.
  * **Three losses**, because each fixes a failure we have actually observed:
      soft CE + Brier   -- the objective and probability quality
      Ranked Probability Score -- ordinal questions (predicting 1 when truth is 5 must cost more)
      Permutation-KL    -- option-order sensitivity, which our own JevBench work found in this class
  * **Case-id-level split.** Sibling questions from one case must never straddle folds. This is the
    discipline that decides whether the resulting number means anything.
  * **Test split is not read here at all.** It is reserved for a single, later, gated evaluation.

usage:
    python bench/train_decision_model.py --epochs 8            # full run
    python bench/train_decision_model.py --smoke              # 20 steps, proves it runs
"""
from __future__ import annotations

import argparse, json, math, random, sys, time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
from losses import rps_loss, permutation_kl

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "models" / "typed-decisions"
BASE = ROOT / "models" / "modernbert-base"
OUT = ROOT / "work" / "training"

K_SLOTS = 32          # option slots, fixed — matches the ANE graph
MAX_LEN = 256         # sequence budget; set from --max-len (the ANE export uses 256/512)


def load_rows(split: str) -> list[dict]:
    import pandas as pd
    return pd.read_parquet(DATA / "all" / f"{split}-00000-of-00001.parquet").to_dict("records")


def build_items(rows: list[dict], tok, limit: int = 0) -> list[dict]:
    """One training item per (row, question). Options are marker tokens inside one sequence."""
    sys.path.insert(0, str(ROOT / "bench"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("lc", ROOT / "work" / "laya-repo" / "laya" / "common.py")
    lc = importlib.util.module_from_spec(spec); spec.loader.exec_module(lc)

    def _d(v):
        """The parquet stores these as JSON strings; accept either."""
        if isinstance(v, str):
            try: return json.loads(v)
            except json.JSONDecodeError: return v
        return v

    items = []
    for r in rows:
        qs = _d(r["questions"])
        gold = _d(r["gold"])
        state = _d(r["state"])
        for qname, q in qs.items():
            g = gold.get(qname)
            if not g or "probabilities" not in g:
                continue
            labels = list(g["probabilities"].keys())
            if len(labels) < 2 or len(labels) > K_SLOTS:
                continue
            qtype = "noul" if len(labels) == 2 else ("score" if _is_ordinal(labels) else "choice")
            crit = q.get("criteria") if isinstance(q, dict) else None
            if isinstance(crit, list):
                crit = {str(i): c for i, c in enumerate(crit)}
            if qtype == "noul":
                crit = {"false": "the statement does not hold", "true": "the statement holds"}
            q_int = {"t": qtype, "ins": str(q.get("instructions", q.get("ins", "")))[:400], "crit": crit}
            seq, markers = lc.build_sequence(tok, state, q_int, MAX_LEN, 192)
            if len(markers) != len(labels):
                continue
            target = [float(g["probabilities"][l]) for l in labels]
            items.append({"id": r["id"], "seq": seq, "markers": markers, "qtype": lc.QTYPES[qtype],
                          "target": target, "labels": labels, "qname": qname})
    return items[:limit] if limit else items


def _is_ordinal(labels: list[str]) -> bool:
    try:
        return sorted(int(x) for x in labels) == list(range(len(labels)))
    except (TypeError, ValueError):
        return False


def collate(items: list[dict], pad_id: int) -> dict:
    B = len(items)
    ids = np.full((B, MAX_LEN), pad_id, dtype=np.int64)
    am = np.zeros((B, MAX_LEN), dtype=np.int64)
    sel = np.zeros((B, K_SLOTS, MAX_LEN), dtype=np.float32)
    tgt = np.zeros((B, K_SLOTS), dtype=np.float32)
    qt = np.zeros(B, dtype=np.int64)
    mask = np.zeros((B, K_SLOTS), dtype=np.float32)
    for i, it in enumerate(items):
        s = it["seq"][:MAX_LEN]
        ids[i, :len(s)] = s
        am[i, :len(s)] = 1
        for j, mp in enumerate(it["markers"]):
            if mp < MAX_LEN:
                sel[i, j, mp] = 1.0
        k = len(it["target"])
        tgt[i, :k] = it["target"]
        mask[i, :k] = 1.0
        qt[i] = it["qtype"]
    return {"input_ids": torch.tensor(ids), "attention_mask": torch.tensor(am),
            "selection": torch.tensor(sel), "qtype": torch.tensor(qt),
            "target": torch.tensor(tgt), "mask": torch.tensor(mask)}


class DecisionModel(nn.Module):
    """ModernBERT-base + Laya's marker-pointer head, in Laya's own shape."""

    def __init__(self, base: Path, head_layers: int = 2) -> None:
        super().__init__()
        from transformers import AutoModel, AutoConfig
        cfg = AutoConfig.from_pretrained(base)
        self.encoder = AutoModel.from_pretrained(base, dtype=torch.float32)
        d = cfg.hidden_size
        nhead = max(1, d // 64)
        layer = nn.TransformerEncoderLayer(d, nhead, 4 * d, 0.0, batch_first=True, norm_first=True)
        self.head = nn.TransformerEncoder(layer, head_layers, enable_nested_tensor=False)
        self.type_emb = nn.Embedding(3, d)
        self.scorer = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, d), nn.GELU(), nn.Linear(d, 1))
        self.k_slots = K_SLOTS

    def forward(self, input_ids, attention_mask, selection, qtype):
        h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        h = h + self.type_emb(qtype)[:, None, :]
        pad = ~attention_mask.bool()
        h = self.head(h, src_key_padding_mask=pad)
        m = torch.matmul(selection, h)                      # (B, K, D) — the gather, as a matmul
        return self.scorer(m).squeeze(-1)                   # (B, K) logits


def losses(logits, target, mask, qtype, pkl=0.0):
    """soft CE + Brier, plus RPS on ordinal rows, plus an optional permutation-KL term."""
    logp = F.log_softmax(logits, dim=-1)
    ce = -(target * logp).sum(-1)
    p = logp.exp()
    brier = ((p - target) ** 2).sum(-1)
    base = (ce + brier).mean()
    # RPS only where the question is ordinal (score type)
    ord_rows = (qtype == 1)
    if bool(ord_rows.any()):
        base = base + rps_loss(logits[ord_rows], target[ord_rows], mask[ord_rows])
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--head-layers", type=int, default=2)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--pkl", type=float, default=0.0,
                    help="weight for permutation-KL (0 = off; 0.5 is a reasonable start)")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="gradient checkpointing: less memory, more compute")
    ap.add_argument("--smoke", action="store_true", help="20 steps then exit — proves it runs")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    global MAX_LEN
    MAX_LEN = args.max_len

    torch.manual_seed(0); random.seed(0); np.random.seed(0)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"  device: {dev}", flush=True)

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(BASE)

    rows = load_rows("train")
    # ---- case-id-level split: sibling questions must never straddle folds ----
    ids = sorted({r["id"] for r in rows})
    random.shuffle(ids)
    n_fit, n_cal = int(len(ids) * 0.80), int(len(ids) * 0.15)
    fit_ids, cal_ids = set(ids[:n_fit]), set(ids[n_fit:n_fit + n_cal])
    fit = [r for r in rows if r["id"] in fit_ids]
    cal = [r for r in rows if r["id"] in cal_ids]
    print(f"  cases: {len(fit_ids)} fit / {len(cal_ids)} calib  (of {len(ids)})", flush=True)

    fit_items = build_items(fit, tok, limit=40 if args.smoke else 0)
    cal_items = build_items(cal, tok, limit=20 if args.smoke else 0)
    print(f"  decisions: {len(fit_items)} fit / {len(cal_items)} calib", flush=True)
    if not fit_items:
        print("  FATAL: no training items built — sequence format mismatch"); return 1

    model = DecisionModel(BASE, args.head_layers).to(dev)
    if args.grad_ckpt:
        model.encoder.gradient_checkpointing_enable()
        print("  gradient checkpointing ON", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = (len(fit_items) + args.batch - 1) // args.batch
    if args.smoke:
        steps = 20
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=args.epochs * steps)

    args.out.mkdir(parents=True, exist_ok=True)
    best = 1e9
    t0 = time.perf_counter()
    step_i = 0
    for ep in range(args.epochs):
        random.shuffle(fit_items)
        model.train()
        run = 0.0
        for bi in range(steps):
            batch = fit_items[bi * args.batch:(bi + 1) * args.batch]
            if not batch:
                break
            b = collate(batch, tok.pad_token_id or 0)
            b = {k: v.to(dev) for k, v in b.items()}
            logits = model(b["input_ids"], b["attention_mask"], b["selection"], b["qtype"])
            loss = losses(logits, b["target"], b["mask"], b["qtype"])
            if args.pkl > 0:
                # a twin pass with the option markers shuffled; scatter back and penalise the KL
                perm = torch.stack([torch.randperm(b["selection"].shape[1])
                                    for _ in range(b["selection"].shape[0])]).to(dev)
                sel2 = torch.zeros_like(b["selection"])
                for i in range(b["selection"].shape[0]):
                    for j in range(b["selection"].shape[1]):
                        sel2[i, j] = b["selection"][i, perm[i, j]]
                lg2 = model(b["input_ids"], b["attention_mask"], sel2, b["qtype"])
                loss = loss + args.pkl * permutation_kl(logits, lg2, perm, b["mask"])
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step()
            run += float(loss)
            step_i += 1
            if step_i % 5 == 0:
                el = time.perf_counter() - t0
                print(f"  ep{ep} step{step_i:>5}  loss {run/5:.4f}  "
                      f"{el/step_i:.2f}s/step  eta {(steps*args.epochs-step_i)*el/step_i/3600:.1f}h",
                      flush=True)
                run = 0.0
            if args.smoke and step_i >= 20:
                break
        # dev check on calib
        model.eval()
        tot = cor = 0; ll = 0.0
        with torch.no_grad():
            for bi in range(0, len(cal_items), args.batch):
                batch = cal_items[bi:bi + args.batch]
                if not batch: break
                b = collate(batch, tok.pad_token_id or 0)
                b = {k: v.to(dev) for k, v in b.items()}
                lo = model(b["input_ids"], b["attention_mask"], b["selection"], b["qtype"])
                ll += float(losses(lo, b["target"], b["mask"], b["qtype"])) * len(batch)
                for i in range(len(batch)):
                    k = len(batch[i]["target"])
                    cor += int(int(lo[i, :k].argmax()) == int(b["target"][i, :k].argmax()))
                    tot += 1
        acc = cor / max(1, tot)
        print(f"  == ep{ep} dev: acc {acc:.4f}  loss {ll/max(1,len(cal_items)):.4f}", flush=True)
        if ll < best:
            best = ll
            torch.save({"model": model.state_dict(), "epoch": ep, "dev_acc": acc},
                       args.out / "best.pt")
            print(f"     saved best.pt (dev loss {best:.4f})", flush=True)
        torch.save({"model": model.state_dict(), "epoch": ep}, args.out / "last.pt")
        if args.smoke:
            print("  SMOKE OK — 20 steps and a dev pass completed"); break

    print(f"  done in {(time.perf_counter()-t0)/3600:.2f}h", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
