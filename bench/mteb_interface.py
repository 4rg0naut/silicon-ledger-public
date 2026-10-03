#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mteb>=2.0",
#     "requests",
#     "numpy",
# ]
# ///
"""Introspect what `mteb` expects from a custom model, before writing a wrapper.

Prints the real interface rather than a guessed one. What it established (MTEB 2.21.0):

  EncoderProtocol.encode(inputs: DataLoader[BatchedInput], *, task_metadata, hf_split, hf_subset)
  + mteb_model_meta, similarity, similarity_pairwise
  mteb.evaluate(model, tasks, *, encode_kwargs, overwrite_strategy, ...) -> ModelResult
      (results go to a ResultCache at ~/.cache/mteb, NOT an output_folder argument)
  MTEB ships OpenAIAPIEncodeWrapper for an OpenAI-compatible endpoint — which is what our ANE
      server is, so no protocol implementation was needed:
        endpoint_url must be the BASE url (MTEB appends /v1/... itself)
        use_chat_template=False is required: the default `messages` field is a vLLM extension

`bench/mteb_retrieval.py` is the evaluation that uses those findings.

usage: uv run bench/mteb_probe.py
"""

from __future__ import annotations

import inspect

import mteb


def main() -> int:
    print(f"mteb {getattr(mteb, '__version__', '?')}")

    proto = getattr(mteb.models, "EncoderProtocol", None)
    print(f"\nEncoderProtocol: {proto}")
    if proto is not None:
        for name, member in inspect.getmembers(proto):
            if name.startswith("_"):
                continue
            kind = type(member).__name__
            doc = (inspect.getdoc(member) or "").split("\n")[0][:90]
            print(f"  {name:<26} {kind:<16} {doc}")

    print("\nModelMeta fields:")
    try:
        from mteb.models.model_meta import ModelMeta

        for f, spec in ModelMeta.model_fields.items():
            print(f"  {f:<26} {str(spec.annotation)[:70]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not introspect: {exc})")

    print("\nA few retrieval tasks (English, small):")
    try:
        tasks = mteb.get_tasks(task_types=["Retrieval"], languages=["eng"])
        for t in tasks[:12]:
            print(f"  {t.metadata.name:<34} {t.metadata.n_queries if hasattr(t.metadata,'n_queries') else ''}")
        print(f"  … {len(tasks)} English retrieval tasks total")
    except Exception as exc:  # noqa: BLE001
        print(f"  (task listing failed: {exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
