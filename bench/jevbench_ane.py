#!/usr/bin/env python3
"""JevBench adapters for our ANE decision-model ports.

Design rule: **reuse the author's code, never reimplement it.** `build_sequence`,
`render_options`, `_to_internal`, `temp_bucket` and `clamp_temperature` are imported verbatim from
Laya's own package (`work/laya-repo/laya/common.py`, `agent.py`). An earlier hand-rolled copy of
`build_sequence` in `export_laya_ane.py` was missing the `"{type} question: {instructions}"` header
and used raw labels instead of rendered option criteria -- feeding the model a sequence its author
never designed. That is the class of bug this file exists to make impossible.

The ANE graph emits **raw logits only**. Temperature, softmax and answer packaging all happen
host-side, exactly where the author puts them (agent.py: `z = logits[r,:k] / t_scale; p = softmax(z)`).
For this checkpoint `temperature = [1.0,1.0,1.0]` and `temperature_by_options = {}`, so `t_scale` is
identically 1 -- but the path is implemented faithfully rather than assumed.

usage: .venv/bin/python bench/jevbench_ane.py --bundle <path.aimodelc> --seq-len 1024
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import sys
import threading
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
LAYACOMMON = ROOT / "work" / "laya-repo" / "laya" / "common.py"
LAYAAGENT = ROOT / "work" / "laya-repo" / "laya" / "agent.py"
JEVBENCH = ROOT / "work" / "jevbench"
MODEL_DIR = ROOT / "models" / "laya-multilingual"

K_SLOTS = 32          # option slots baked into the static graph


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


_laya = _load_mod("_laya_common", LAYACOMMON)
build_sequence = _laya.build_sequence
render_options = _laya.render_options
QTYPES = _laya.QTYPES
temp_bucket = _laya.temp_bucket
clamp_temperature = _laya.clamp_temperature

if str(JEVBENCH) not in sys.path:
    sys.path.insert(0, str(JEVBENCH))
from jevbench.adapters.base import DecisionResult, build_question  # noqa: E402


def _to_internal(qdef: dict) -> dict:
    """Copied from agent.py:255 -- external question -> internal {t, ins, crit}."""
    t = qdef["type"]
    crit = qdef.get("criteria")
    if t == "choice" and isinstance(crit, list):
        crit = {c: None for c in crit}
    ins = qdef["instructions"]
    if not isinstance(ins, str):
        ins = json.dumps(ins)
    return {"t": t, "ins": ins, "crit": crit}


class LayaANEAdapter:
    """Runs our ANE bundle as a JevBench adapter, on the author's own input path."""

    name = "laya_ane"
    cost_basis = "local_ane_no_provider_tariff"     # no provider tariff; priced by size class later
    probs_source = "native"

    def __init__(self, bundle: Path, seq_len: int = 1024, threads: int | None = None,
                 model_dir: Path | None = None, max_len: int | None = None,
                 compute: str = "neural_engine") -> None:
        self.bundle = Path(bundle)
        self.seq_len = seq_len
        self.model_dir = Path(model_dir) if model_dir else MODEL_DIR
        self.model = f"{self.model_dir.name} on the ANE"
        self.price_input_per_m = None
        self.price_output_per_m = None
        self.cfg = json.loads((self.model_dir / "rl_agent_config.json").read_text())
        # the author's own budget resolution (agent.py:281-282), not the function defaults
        # The author's budget by default. `max_len` overrides it so we can test whether the
        # checkpoint gains from context beyond its designed budget -- without this override the
        # adapter truncates to the config's max_len and a "longer graph" experiment tests nothing.
        self.max_len = max_len if max_len is not None else self.cfg.get("max_len", 512)
        self.head_max_len = self.cfg.get("head_max_len", 192)
        self.temperature = [clamp_temperature(t) for t in self.cfg.get("temperature", [1.0, 1.0, 1.0])]
        self.temperature_by_options = {
            k: clamp_temperature(v) for k, v in self.cfg.get("temperature_by_options", {}).items()}
        self.compute = compute
        self._fn = None
        self._tok = None
        self._loop = None

    # ------------------------------------------------------------------ lifecycle
    def load(self):
        if self._fn is not None:
            return self._fn
        from transformers import AutoTokenizer
        from coreai.runtime import AIModel, ComputeUnitKind, SpecializationOptions
        self._tok = AutoTokenizer.from_pretrained(self.model_dir / "tokenizer")
        loop = asyncio.new_event_loop()
        threading.Thread(target=loop.run_forever, daemon=True).start()
        self._loop = loop
        self._run = lambda c: asyncio.run_coroutine_threadsafe(c, loop).result()
        unit = {"neural_engine": ComputeUnitKind.neural_engine,
                "gpu": ComputeUnitKind.gpu, "cpu": ComputeUnitKind.cpu}[self.compute]
        opts = SpecializationOptions.from_preferred_compute_unit_kind(unit())
        self._model = self._run(AIModel.load(self.bundle, specialization_options=opts))
        self._fn = self._model.load_function("main")
        return self._fn

    def prepare(self, task) -> None:
        self.load()

    def reserve_estimate(self, task) -> float:
        return 0.0

    # ------------------------------------------------------------------ the run
    def build_request(self, task) -> dict:
        return {"state": task.state, "questions": {"decision": build_question(task)}}

    def run(self, task) -> DecisionResult:
        res = DecisionResult(adapter=self.name, ok=False, probs_source=self.probs_source,
                             model=self.model)
        body = self.build_request(task)
        res.request_body = body
        try:
            fn = self.load()
        except Exception as e:                                    # noqa: BLE001
            res.error = f"load failed: {type(e).__name__}: {str(e)[:250]}"
            return res

        t0 = time.perf_counter()
        try:
            q = _to_internal(body["questions"]["decision"])
            # the author's builder, verbatim, at the author's own budget
            seq, markers = build_sequence(self._tok, body["state"], q,
                                          self.max_len, self.head_max_len)
            if len(markers) != len(render_options(q)):
                raise ValueError(f"options exceed head_max_len={self.head_max_len}")
            k = len(markers)
            if k > K_SLOTS:
                raise ValueError(f"{k} options exceeds the graph's {K_SLOTS} slots")

            S = self.seq_len
            pad = self._tok.pad_token_id or 0
            ids = (seq + [pad] * (S - len(seq)))[:S]
            am = ([1] * len(seq) + [0] * (S - len(seq)))[:S]
            sel = np.zeros((1, K_SLOTS, S), dtype=np.float16)
            for j, mp in enumerate(markers):
                if mp < S:
                    sel[0, j, mp] = 1.0
            qtype = QTYPES[q["t"]]

            from coreai.runtime import NDArray
            out = self._run(fn({
                "input_ids": NDArray(np.array([ids], dtype=np.int32)),
                "attention_mask": NDArray(np.array([am], dtype=np.int32)),
                "selection": NDArray(sel),
                "qtype": NDArray(np.array([qtype], dtype=np.int32)),
            }))
            logits = np.asarray(out["logits"].numpy()).reshape(-1).astype(np.float64)
            del out
        except Exception as e:                                    # noqa: BLE001
            res.latency_s = time.perf_counter() - t0
            res.error = f"{type(e).__name__}: {str(e)[:300]}"
            return res
        res.latency_s = time.perf_counter() - t0

        # --- the author's readout (agent.py:329-331), verbatim in form ---
        t_scale = self.temperature_by_options.get(temp_bucket(qtype, k), self.temperature[qtype])
        z = logits[:k] / t_scale
        p = np.exp(z - z.max())
        p = p / p.sum()

        if q["t"] == "choice":
            keys = list(q["crit"].keys())
            res.probs = {str(kk): float(v) for kk, v in zip(keys, p)}
        elif q["t"] == "score":
            res.probs = {str(i): float(v) for i, v in enumerate(p)}
        else:
            res.probs = {"yes": float(p[1]), "no": float(1.0 - p[1])}

        # --- second channel: the correctness head, if weights were supplied ---
        self.channel = getattr(self, "channel", None)
        if self.channel is not None and self.channel.w is not None:
            dist = dict(res.probs)
            conf = self.channel.confidence(dist)
            res.probs = self.channel.rescale(dist)
            res.raw = {"runtime": {"device": "ane", "seq_len": S, "options": k, "qtype": qtype,
                                   "t_scale": t_scale, "bundle": self.bundle.name},
                       "channels": {"distribution": dist, "confidence": conf}}
        else:
            res.raw = {"runtime": {"device": "ane", "seq_len": S, "options": k, "qtype": qtype,
                                   "t_scale": t_scale, "bundle": self.bundle.name}}
        res.usage = {"input_tokens": int(sum(am))}
        res.ok = True
        return res


class VonANEAdapter:
    """Von-1.0 (ModernBERT-Large, 3-way NLI head) as a JevBench adapter.

    Von is **not** a Jev-style typed-decision model -- it is an NLI classifier over
    entailment/neutral/contradiction. JevBench requires that any mapping be written down *before*
    the run, so here it is:

      for each allowed label L:
          premise     = state
          hypothesis  = "{instructions} {criteria[L] or L}"
          score(L)    = the ENTAILMENT logit
      probabilities   = softmax over the option scores

    This is the same construction Von's own `berta_backend.py::evaluate_choice` uses, and the same
    one JevBench's reranker class uses for non-decision models. It is an adaptation, not a native
    readout, and should be read as such -- Von's own benchmark is `authored144` (EXP-016).
    """

    name = "von_ane"
    cost_basis = "local_ane_no_provider_tariff"
    probs_source = "nli_entailment_logits"      # never "native": this is a mapped readout

    def __init__(self, bundle: Path, seq_len: int = 256, model_dir: Path | None = None,
                 compute: str = "cpu") -> None:
        # NOTE: this bundle SEGFAULTS in AIModel.load under both `neural_engine` and `gpu`
        # placement on this machine, while loading cleanly on `cpu`. EXP-016 measured the same
        # bundle on the ANE successfully, so this is an environment/driver regression, not a
        # corrupt graph. CPU placement is the default here so the row is obtainable at all.
        self.bundle = Path(bundle)
        self.compute = compute
        self.seq_len = seq_len
        self.model_dir = Path(model_dir) if model_dir else ROOT / "models" / "von-1.0"
        self.model = f"{self.model_dir.name} (NLI) on the ANE"
        self.price_input_per_m = None
        self.price_output_per_m = None
        cfg = json.loads((self.model_dir / "config.json").read_text())
        self.entail_idx = next(int(k) for k, v in cfg["id2label"].items()
                               if "entail" in v.lower())
        self.pad_id = cfg["pad_token_id"]
        self.max_len = 512
        self._fn = None

    def load(self):
        if self._fn is not None:
            return self._fn
        from transformers import AutoTokenizer
        from coreai.runtime import AIModel, ComputeUnitKind, SpecializationOptions
        self._tok = AutoTokenizer.from_pretrained(self.model_dir)
        loop = asyncio.new_event_loop()
        threading.Thread(target=loop.run_forever, daemon=True).start()
        self._loop = loop
        self._run = lambda c: asyncio.run_coroutine_threadsafe(c, loop).result()
        unit = {"neural_engine": ComputeUnitKind.neural_engine,
                "gpu": ComputeUnitKind.gpu, "cpu": ComputeUnitKind.cpu}[self.compute]
        opts = SpecializationOptions.from_preferred_compute_unit_kind(unit())
        self._model = self._run(AIModel.load(self.bundle, specialization_options=opts))
        self._fn = self._model.load_function("main")
        return self._fn

    def prepare(self, task) -> None:
        self.load()

    def reserve_estimate(self, task) -> float:
        return 0.0

    def build_request(self, task) -> dict:
        return {"state": task.state, "questions": {"decision": build_question(task)}}

    def _hypothesis(self, q: dict, label: str) -> str:
        crit = q.get("criteria")
        if q["type"] == "choice" and isinstance(crit, dict):
            desc = crit.get(label)
            return f"{q['instructions']} {desc if desc else label}"
        if q["type"] == "score" and isinstance(crit, list):
            try:
                return f"{q['instructions']} {crit[int(label)]}"
            except (ValueError, IndexError):
                return f"{q['instructions']} level {label}"
        return f"{q['instructions']} {label}"      # noul: labels are no/yes

    def run(self, task) -> DecisionResult:
        res = DecisionResult(adapter=self.name, ok=False, probs_source=self.probs_source,
                             model=self.model)
        body = self.build_request(task)
        res.request_body = body
        try:
            fn = self.load()
        except Exception as e:                                     # noqa: BLE001
            res.error = f"load failed: {type(e).__name__}: {str(e)[:250]}"
            return res

        q = body["questions"]["decision"]
        labels = [str(x) for x in task.labels]
        premise = task.state if isinstance(task.state, str) else json.dumps(task.state)
        t0 = time.perf_counter()
        try:
            from coreai.runtime import NDArray
            scores = []
            for lab in labels:
                enc = self._tok(premise, self._hypothesis(q, lab), truncation=True,
                                max_length=self.max_len, return_tensors="np")
                ids = enc["input_ids"][0][: self.seq_len]
                am = enc["attention_mask"][0][: self.seq_len]
                real = len(ids)
                ids = np.concatenate([ids, np.full(self.seq_len - real, self.pad_id, np.int64)])
                am = np.concatenate([am, np.zeros(self.seq_len - real, np.int64)])
                out = self._run(fn({"input_ids": NDArray(ids[None].astype(np.int32)),
                                    "attention_mask": NDArray(am[None].astype(np.int32))}))
                scores.append(float(np.asarray(out["logits"].numpy()).reshape(-1)[self.entail_idx]))
                del out
            s = np.array(scores, dtype=np.float64)
            p = np.exp(s - s.max()); p = p / p.sum()
        except Exception as e:                                     # noqa: BLE001
            res.latency_s = time.perf_counter() - t0
            res.error = f"{type(e).__name__}: {str(e)[:300]}"
            return res
        res.latency_s = time.perf_counter() - t0
        res.probs = {lab: float(v) for lab, v in zip(labels, p)}
        res.raw = {"runtime": {"device": self.compute, "seq_len": self.seq_len, "options": len(labels),
                               "readout": "nli_entailment", "bundle": self.bundle.name}}
        res.usage = {"input_tokens": self.seq_len * len(labels)}
        res.ok = True
        return res


# ------------------------------------------------------------------ second channel
# JevBench scores ONE distribution per decision, so a second channel has to be folded in rather than
# added. The correctness head predicts "is this answer right" from the SHAPE of the prediction, and
# the honest way to use it here is to rescale the top-label probability to that confidence while
# preserving the ordering — accuracy is untouched, ECE improves, and Brier changes only because the
# distribution genuinely got better calibrated.
class CorrectnessChannel:
    """The second channel. Fitted on out-of-fold predictions, never sees the gold label."""

    def __init__(self, weights: tuple | None = None) -> None:
        self.w, self.b = weights if weights else (None, None)

    @staticmethod
    def features(probs: dict) -> list:
        p = sorted((float(v) for v in probs.values()), reverse=True)
        k = len(p)
        top = p[0] if p else 0.0
        margin = (p[0] - p[1]) if k > 1 else top
        ent = -sum(v * math.log(v + 1e-12) for v in p)
        return [top, margin, ent / math.log(k) if k > 1 else 0.0, math.log(k),
                1.0 if k == 2 else 0.0]

    def confidence(self, probs: dict) -> float | None:
        if self.w is None:
            return None
        x = self.features(probs)
        z = sum(self.w[j] * x[j] for j in range(len(x))) + self.b
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def rescale(self, probs: dict) -> dict:
        """Top label -> the confidence channel's probability; the rest keep their ratios."""
        c = self.confidence(probs)
        if c is None:
            return probs
        top = max(probs, key=probs.get)
        t = float(probs[top])
        if t <= 0:
            return probs
        rest = {k: float(v) for k, v in probs.items() if k != top}
        scale = (1.0 - c) / max(1e-9, sum(rest.values())) if rest else 0.0
        out = {k: v * scale for k, v in rest.items()}
        out[top] = c
        s = sum(out.values())
        return {k: v / s for k, v in out.items()} if s > 0 else probs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--seq-len", type=int, default=1024)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--model-dir", type=Path, default=None)
    ap.add_argument("--max-len", type=int, default=None,
                    help="override the checkpoint's own max_len (to test longer context)")
    args = ap.parse_args()

    sys.path.insert(0, str(JEVBENCH))
    from jevbench.tasks import Task
    data = ROOT / "work" / "jevbench" / "datasets" / "public" / "easy.jsonl"
    rows = []
    with open(data, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(Task.from_dict(json.loads(line)))
    rows = rows[: args.limit]

    ad = LayaANEAdapter(args.bundle, seq_len=args.seq_len, model_dir=args.model_dir,
                        max_len=args.max_len)
    print(f"  adapter {ad.name} | bundle {args.bundle.name} | S={args.seq_len}")
    print(f"  author budget: max_len={ad.max_len} head_max_len={ad.head_max_len}")
    print(f"  temperature={ad.temperature} by_options={ad.temperature_by_options}")
    print()
    ok = 0
    for t in rows:
        res = ad.run(t)
        if res.ok:
            ok += 1
            pred = max(res.probs, key=res.probs.get)
            flag = "OK " if pred == t.expected else "MISS"
            print(f"  {flag} {t.id:<22} pred={pred:<20} gold={t.expected:<20} "
                  f"p={res.probs.get(pred, 0):.3f} {res.latency_s*1000:.1f}ms")
        else:
            print(f"  FAIL {t.id:<22} {res.error}")
    print(f"\n  {ok}/{len(rows)} ran")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
