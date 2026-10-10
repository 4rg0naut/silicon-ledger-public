# OpenClaims — our claims, with receipts

An **OpenClaims event** is a small JSON receipt: one claim, the evidence
behind it, and who checked it — written down so the answer to "how do you
know?" never depends on anyone's memory.
(OpenClaims is a young open standard for exactly that:
https://github.com/openclaims-ai/openclaims.)

## Why our knowledge base sits on it

We make claims about hardware behavior, generated with the help of AI
models and checked against measurements. "An AI helped write it" is a fact
worth stating, not hiding. So every claim in our knowledge base is recorded
as a spine event, and every check is recorded too — with the checker named:

- **663 claims emitted** - each with its source and, when a tool produced
  it, the run that produced it.
- **108 verification events** — all `model_check` (an AI model checked
  them against our measurement ledger).
- **17 disputed** — claims kept precisely *because* someone disagreed.
- **0 human_review** — no human has signed off on any claim yet, and the
  corpus says so instead of implying otherwise.

That last number is the point of the whole exercise: the weakness is
visible in the data, not buried in a footnote.

## Check it yourself (two commands)

```sh
python3 -m venv .venv-ocl && .venv-ocl/bin/pip install "git+https://github.com/openclaims-ai/openclaims.git#subdirectory=python"
.venv-ocl/bin/python knowledge/ane/tools/to_openclaims.py --check
```

Expected final line:

```
committed events : 788 valid, 0 INVALID (of 788)
```

(The Python SDK is not on PyPI yet — install it from the upstream git
repository, as above.)

## The fine print we declare rather than hide

- The cached source copies used to pin evidence spans
  (`knowledge/ane/grounding/cache/`) are **gitignored**: they are bulk
  downloads, not our work. Spans therefore cannot be re-derived from a
  fresh clone — the committed `knowledge/ane/openclaims/claims-*.jsonl`
  are canonical as emitted, and `--check` validates them against the
  schema without the cache. The 8 origin claims (09-origins) were emitted
  span-free on a machine without the cache; every older event keeps the
  span it was first emitted with, and no commit rewrites them.
- The upstream openclaims repository **has no LICENSE file yet** (we filed
  an issue upstream). We keep pointers to it and clean-room code, not
  redistributed prose.
- The converter (`knowledge/ane/tools/to_openclaims.py`) documents every
  mapping decision in its own header, including our confidence labels and
  where they went.
- The digests in these files are self-referential hashes over each full
  event. On this public mirror, private paths inside provenance fields were
  rewritten by the publisher's redaction rules, and every affected event's
  digest was then **re-pinned with the SDK's own `with_event_digest()`** at
  publication time — so `--check` above verifies the bytes you actually
  have. The private corpus's digests differ only by those path strings.
