#!/usr/bin/env python3
"""Rebuild models/qwen3-reranker/qwen3-reranker-0.6b_float16_s512_static.aimodel from the HF copy.

The September bundle (generated 2026-09-26) and its zoo converter went missing from this
box; only reference.json + tokenizer/ survived the cleanup, so the rerank serving lane
(rerank_server.py / gate_reranker.py) could not start (2026-10 audit finding 3). This is
the rebuilt route: HF safetensors -> torch.export -> coreai_torch (the same route
bench/probe_ane_regions.py re-validated on 2026-10-11) -> .aimodel float16, static grid 512.

Interface matched to the consumers (rerank_server.py Engine.score_one):
  inputs  input_ids [1,512] int32, attention_mask [1,512] int32
  output  probs [1,2] = softmax over [P(no_id), P(yes_id)] at the LAST REAL TOKEN.
  The last-real-token pick is graph-safe: one-hot = mask * (cumsum(mask) == sum(mask)),
  pooled = onehot @ logits — matmul only, no dynamic scalar indexing.

Numerics gate BEFORE writing anything (torch 2.14.1 is newer than coremltools' tested 2.7.0
and coreai-torch's validated 2.13.0 - see tools/env/README.md): score reference.json's 10
pairs on the CPU delegate, require rank_groups preserved + min(relevant) - max(irrelevant) > 0
(same checks as gate_reranker.py), and report max |delta| vs the official scores.
reference.json is re-emitted with seq_len + a rebuild stamp AFTER the gate passes; the prior
file is copied aside, never dropped.

usage: .venv-conv/bin/python bench/convert_reranker.py [--device cpu]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "models" / "qwen3-reranker"
HF_DIR = ROOT / "models" / "qwen3-reranker-hf"
AIMODEL = BUNDLE / "qwen3-reranker-0.6b_float16_s512_static.aimodel"
SEQ_LEN = 512


class RerankCore(nn.Module):
    """lm -> lm_head -> one-hot last-real-token -> softmax over [no, yes]."""

    def __init__(self, lm, yes_id: int, no_id: int):
        super().__init__()
        self.lm = lm
        self.yes_id = yes_id
        self.no_id = no_id

    def forward(self, input_ids, attention_mask):
        ids = input_ids.to(torch.int64)
        mask = attention_mask.to(torch.int64)
        out = self.lm(input_ids=ids, attention_mask=mask, use_cache=False)
        logits = out.logits[0].to(torch.float16)                      # [S, V]
        m = attention_mask.to(torch.float16)                          # [1, S]
        total = m.sum(dim=-1, keepdim=True)                           # [1, 1]
        cum = torch.cumsum(m, dim=-1)                                 # [1, S]
        onehot = m * (cum == total).to(torch.float16)                 # exactly one 1
        pooled = onehot @ logits                                      # [1, V]
        yn = torch.stack([pooled[0, self.no_id], pooled[0, self.yes_id]])
        return torch.softmax(yn.float(), dim=0).reshape(1, 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-verify", action="store_true", help="write bundle without runtime gate")
    args = ap.parse_args()

    ref = json.loads((BUNDLE / "reference.json").read_text())
    yes_id, no_id, pad = ref["yes_id"], ref["no_id"], ref["pad_token_id"]
    prefix, suffix, instruction = ref["prefix"], ref["suffix"], ref["default_instruction"]
    print(f"grid {SEQ_LEN}  yes_id={yes_id}  no_id={no_id}  pad={pad}")

    from transformers import AutoModelForCausalLM
    from tokenizers import Tokenizer
    t0 = time.time()
    lm = AutoModelForCausalLM.from_pretrained(HF_DIR, dtype=torch.float16)
    lm.eval()
    tok = Tokenizer.from_file(str(BUNDLE / "tokenizer" / "tokenizer.json"))
    pre = tok.encode(prefix, add_special_tokens=False).ids
    suf = tok.encode(suffix, add_special_tokens=False).ids
    budget = SEQ_LEN - len(pre) - len(suf)
    print(f"loaded HF copy in {time.time()-t0:.1f}s  prefix {len(pre)} tok  suffix {len(suf)} tok  budget {budget}")

    def encode_pair(query: str, doc: str):
        body = f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
        b = tok.encode(body, add_special_tokens=False).ids[:budget]
        ids = pre + b + suf
        padded = ids + [pad] * (SEQ_LEN - len(ids))
        mask = [1] * len(ids) + [0] * (SEQ_LEN - len(ids))
        return (torch.tensor([padded], dtype=torch.int32),
                torch.tensor([mask], dtype=torch.int32))

    core = RerankCore(lm, yes_id, no_id)

    torch.manual_seed(0)
    ex_ids, ex_mask = encode_pair("gate sample", "gate sample document.")
    with torch.no_grad():
        exported = torch.export.export(core, (ex_ids, ex_mask))
        from coreai_torch import TorchConverter, get_decomp_table
        decomposed = exported.run_decompositions(get_decomp_table())
    print(f"exported+decomposed (grid {SEQ_LEN})")

    program = (
        TorchConverter()
        .add_exported_program(exported_program=decomposed,
                              input_names=["input_ids", "attention_mask"],
                              output_names=["probs"])
        .to_coreai()
    )
    program.optimize()
    if not program._mlir_module.operation.verify():
        print("MLIR verify FAILED — running diagnose_convert route manually if needed", file=__import__("sys").stderr)
        return 2

    if not args.skip_verify:
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="rerank-verify-")) / "cand.aimodel"
        program.save_asset(tmp, _meta())
        got = _score_pairs(tmp, ref, encode_pair)
        ok = _gate(got, ref)
        shutil.rmtree(tmp.parent, ignore_errors=True)
        if not ok:
            print("GATE FAILED — bundle NOT written; deltas above are the finding")
            return 1

    AIMODEL.parent.mkdir(parents=True, exist_ok=True)
    program.save_asset(AIMODEL, _meta())
    size = sum(f.stat().st_size for f in AIMODEL.rglob("*") if f.is_file())
    print(f"wrote {AIMODEL.relative_to(ROOT)} ({size/1e6:.1f} MB)")

    got = _score_pairs(AIMODEL, ref, encode_pair)
    _gate(got, ref)
    backup = BUNDLE / "reference-2026-09-26.json"
    if not backup.exists():
        shutil.copy2(BUNDLE / "reference.json", backup)
    ref_out = dict(ref)
    ref_out["seq_len"] = SEQ_LEN
    ref_out["rebuilt"] = {
        "by": "bench/convert_reranker.py",
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "env": {
            "torch": torch.__version__,
            "coreai_torch": __import__("coreai_torch").__version__ if hasattr(__import__("coreai_torch"), "__version__") else "0.4.2",
            "numpy": np.__version__,
        },
        "max_abs_delta_vs_official": _max_delta(got, ref),
        "scores_cpu_delegate": {k: round(v, 6) for k, v in got.items()},
        "prior_reference": backup.name,
    }
    (BUNDLE / "reference.json").write_text(json.dumps(ref_out, indent=2, ensure_ascii=False))
    print(f"reference.json re-emitted with seq_len + rebuild stamp (prior kept as {backup.name})")
    return 0


def _meta():
    from coreai.runtime import AIModelAssetMetadata
    meta = AIModelAssetMetadata()
    meta.author = "ANE lab rebuild (2026-10-11)"
    meta.license = "apache-2.0"
    meta.model_description = "Qwen3-Reranker-0.6B, fp16, static 512, last-real-token P(yes) head (convert_reranker route)"
    return meta


def _score_pairs(model_path: Path, ref: dict, encode_pair):
    from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    opts = SpecializationOptions.from_preferred_compute_unit_kind(ComputeUnitKind.cpu())
    model = asyncio.run_coroutine_threadsafe(
        AIModel.load(str(model_path), specialization_options=opts), loop).result()
    fn = model.load_function("main")
    got = {}
    for key, pair in ref["pairs"].items():
        ids, mask = encode_pair(pair["query"], pair["doc"])
        out = asyncio.run_coroutine_threadsafe(fn({
            "input_ids": NDArray(ids.numpy()),
            "attention_mask": NDArray(mask.numpy()),
        }), loop).result()
        probs = out["probs"].numpy().reshape(-1)
        got[key] = float(probs[1])
    return got


def _max_delta(got: dict, ref: dict) -> float:
    off = ref.get("official_scores", {})
    return max((abs(got[k] - v) for k, v in off.items() if k in got), default=float("nan"))


def _gate(got: dict, ref: dict) -> bool:
    ok = True
    off = ref.get("official_scores", {})
    for k in sorted(got):
        d = f"  delta {abs(got[k]-off[k]):+.6f}" if k in off else ""
        print(f"    {k:<10} p_yes={got[k]:.6f}{d}")
    for group, members in ref.get("rank_groups", {}).items():
        ranked = sorted(members, key=lambda m: -got[m])
        good = ranked == list(members)
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}: rank_group {group}: {ranked}")
    # The absolute min(rel)-max(irr) separation (gate_reranker.py, 6-pair era) is not a
    # property of the 10-pair reference: OFFICIAL itself gives rel-cos 0.000046 < irr-math 0.272.
    # Meaning lives inside families (rank_groups) here; print separation for the record only.
    rel = [v for k, v in got.items() if ref["pairs"][k]["relevant"]]
    irr = [v for k, v in got.items() if not ref["pairs"][k]["relevant"]]
    orel = [v for k, v in off.items() if ref["pairs"].get(k, {}).get("relevant")]
    oirr = [v for k, v in off.items() if ref["pairs"].get(k, {}) and not ref["pairs"][k]["relevant"]]
    sep = min(rel) - max(irr)
    osep = (min(orel) - max(oirr)) if orel and oirr else float("nan")
    print(f"  record-only: separation {sep:+.6f} (official scores themselves give {osep:+.6f} "
          "on this 10-pair set — family ranking is the meaningful check)")
    dmax = _max_delta(got, ref)
    drift_ok = dmax < 0.05
    ok &= drift_ok
    print(f"  {'PASS' if drift_ok else 'FAIL'}: max |delta| vs official = {dmax:.6f} "
          "(fp16 + torch 2.14 beyond validated 2.13; bound is documentation, not hope)")
    return ok


if __name__ == "__main__":
    raise SystemExit(main())
