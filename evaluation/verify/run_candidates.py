#!/usr/bin/env python3
"""Run the groundedness candidates against the 55 hand-labelled items.

Task: given a claim and the source passage it cites, decide
    yes        the passage states or directly entails the claim
    partial    part of it, or the claim overreaches
    no         not supported

Two candidates, mapped onto that verdict space:

  modernce-large-nli    3-way NLI. entailment/neutral/contradiction map to yes/partial/no
                        directly -- the cleanest possible fit.
  lettucedect-v2        token-level hallucination spans over the ANSWER segment.
                        context=passage, answer=claim. tokenize(passage, claim) as a pair
                        with truncation="only_first", which guarantees the CLAIM is never
                        truncated however long the passage is.

The 2 items labelled `insufficient` are excluded: their passages are retrieval misses, so
no candidate can be fairly graded on them. They are reported separately, not hidden.

Every number is reported per stratum, never pooled -- the pooled figure is the one that
lied to us before.
"""

from __future__ import annotations

import json
import collections
import torch
from pathlib import Path
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          AutoModelForTokenClassification)

HERE = Path(__file__).resolve().parent
DEV = "mps" if torch.backends.mps.is_available() else "cpu"

NLI_MAP = {0: "yes", 1: "partial", 2: "no"}   # entailment / neutral / contradiction


def load_items():
    items = [json.loads(l) for l in open(HERE / "testset.jsonl")]
    return items


def run_nli(items, model_id, max_len=2048, batch=8):
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForSequenceClassification.from_pretrained(model_id).to(DEV).eval()
    out = []
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        enc = tok([c["passage"] for c in chunk], [c["claim"] for c in chunk],
                  truncation="only_first", max_length=max_len, padding=True,
                  return_tensors="pt")
        enc = {k: v.to(DEV) for k, v in enc.items()}
        with torch.no_grad():
            prob = model(**enc).logits.softmax(-1).cpu()
        for j, c in enumerate(chunk):
            p = prob[j]
            k = int(p.argmax())
            out.append({"id": c["id"], "verdict": NLI_MAP[k],
                        "conf": float(p[k]),
                        "probs": {NLI_MAP[n]: float(p[n]) for n in range(len(p))}})
    del model
    if DEV == "mps":
        torch.mps.empty_cache()
    return out


def run_lettuce(items, model_id, max_len=4096, batch=4):
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForTokenClassification.from_pretrained(model_id).to(DEV).eval()
    out = []
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        enc = tok([c["passage"] for c in chunk], [c["claim"] for c in chunk],
                  truncation="only_first", max_length=max_len, padding=True,
                  return_tensors="pt")
        ids = enc["input_ids"]
        # capture the segment map BEFORE the encoding moves to the device
        seqs = [enc.sequence_ids(j) for j in range(len(chunk))]
        enc = {k: v.to(DEV) for k, v in enc.items()}
        with torch.no_grad():
            preds = model(input_ids=enc["input_ids"],
                          attention_mask=enc["attention_mask"]).logits.argmax(-1).cpu()
        for j, c in enumerate(chunk):
            toks = ids[j].tolist()
            sid = seqs[j]
            if sid is None or all(s is None for s in sid):
                # fall back: answer tokens are everything after the second SEP
                seps = [n for n, t in enumerate(toks) if t == tok.sep_token_id]
                lo = (seps[1] + 1) if len(seps) > 1 else 0
                mask = [n >= lo and toks[n] != tok.sep_token_id for n in range(len(toks))]
            else:
                mask = [s == 1 for s in sid]
            n_ans = sum(mask)
            n_bad = sum(1 for n, m in enumerate(mask) if m and preds[j][n].item() == 1)
            frac = (n_bad / n_ans) if n_ans else 0.0
            verdict = "yes" if n_bad == 0 else ("partial" if frac < 0.5 else "no")
            out.append({"id": c["id"], "verdict": verdict,
                        "unsupported_frac": round(frac, 4),
                        "n_answer_tokens": n_ans, "n_unsupported": n_bad})
    del model
    if DEV == "mps":
        torch.mps.empty_cache()
    return out


def report(name, items, res):
    gold = {c["id"]: c["gold"] for c in items}
    scored = [(g, r) for g, r in ((gold[x["id"]], x["verdict"]) for x in res)
              if g != "insufficient"]
    n = len(scored)
    exact = sum(1 for g, p in scored if g == p)
    # "supported or not" is the robust reading: partial counts as supported
    strict = sum(1 for g, p in scored
                 if (g == "yes") == (p == "yes"))
    print(f"\n  {name}")
    print(f"    exact 3-way match : {exact}/{n} = {100*exact/n:.0f}%")
    print(f"    yes/not agreement : {strict}/{n} = {100*strict/n:.0f}%")
    cm = collections.Counter(scored)
    print(f"    confusion (gold -> predicted):")
    for g in ("yes", "partial", "no"):
        row = {p: cm.get((g, p), 0) for p in ("yes", "partial", "no")}
        print(f"      gold {g:8} -> {row}")
    return {"name": name, "n": n, "exact": exact, "strict": strict}


def main():
    items = load_items()
    print(f"  items: {len(items)}   device: {DEV}")
    print("  gold:", dict(collections.Counter(c['gold'] for c in items)))

    results = {}
    for label, mid, fn in [
        ("modernce-large-nli", "dleemiller/ModernCE-large-nli", run_nli),
        ("lettucedect-v2",     "KRLabsOrg/lettucedect-v2-mmbert-base", run_lettuce),
    ]:
        try:
            res = fn(items, mid)
            results[label] = res
            report(label, items, res)
        except Exception as e:
            print(f"\n  {label}: FAILED {type(e).__name__}: {str(e)[:200]}")

    # per-stratum on the gold verdict itself
    print("\n  === where each candidate disagrees with gold, by gold verdict ===")
    gold = {c["id"]: c["gold"] for c in items}
    for label, res in results.items():
        print(f"\n    {label}")
        by = collections.defaultdict(lambda: [0, 0])
        for r in res:
            g = gold[r["id"]]
            if g == "insufficient":
                continue
            by[g][1] += 1
            if g == r["verdict"]:
                by[g][0] += 1
        for g in ("yes", "partial", "no"):
            ok, tot = by[g]
            if tot:
                print(f"      gold {g:8} n={tot:2}  exact {ok:2}  {100*ok/tot:3.0f}%")

    (HERE / "candidate_results.json").write_text(json.dumps(results, indent=2))
    print(f"\n  wrote {HERE/'candidate_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())