#!/bin/sh
# publish.sh — deterministic generator of the public staging tree.
# Usage (from anywhere inside the repo):  sh tools/publish/publish.sh
# Refuses a dirty tree. Output: ../silicon-ledger-public-staging (relative to repo root).
# Determinism: same tracked content in => byte-identical staging out (verified by
# running twice + diff -r). Scrub rules: tools/publish/redaction.json (personal only).
# The openclaims gate needs the SDK: run as  PYTHON=.venv/bin/python sh tools/publish/publish.sh
set -eu
cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain)" ]; then
    echo "refusing: git tree is dirty — commit first" >&2
    exit 1
fi

"${PYTHON:-python3}" - <<'PY'
import json, os, subprocess, sys

repo = os.getcwd()
stage = os.path.abspath(os.path.join(repo, "..", "silicon-ledger-public-staging"))
rules = json.load(open("tools/publish/redaction.json"))["tokens"]
personal = [(r["pattern"], r.get("replacement", "")) for r in rules if r["class"] == "personal"]
# longest pattern first so nested paths collapse fully
personal.sort(key=lambda t: len(t[0]), reverse=True)

KEEP_DIRS = ("bench/", "ports/", "tools/", "knowledge/", "evaluation/", "schemas/")
KEEP_TOP = (".md", ".txt", ".json", "LICENSE")
KEEP_RESULTS_EXT = (".md", ".json", ".txt", ".sh")
OVERLAY_PREFIX = "tools/publish/public-content/"

files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()

def keep(f):
    if "__pycache__" in f:
        return False
    if f == "knowledge/ane/ARCHIVE-MAP.md":
        return False  # machine-local paths inside; stays private by rule
    if f.startswith(OVERLAY_PREFIX):
        return False
    if f.startswith("results/"):
        return f.endswith(KEEP_RESULTS_EXT)
    if f.startswith(KEEP_DIRS):
        return True
    return "/" not in f and (f.endswith(KEEP_TOP))

kept = sorted(f for f in files if keep(f))

if os.path.isdir(stage):
    subprocess.run(["rm", "-rf", stage], check=True)

scrubbed, files_scrubbed = 0, 0
for f in kept:
    data = open(f, "rb").read()
    is_text = b"\x00" not in data
    if is_text:
        for pat, rep in personal:
            hits = data.count(pat.encode())
            if hits:
                data = data.replace(pat.encode(), rep.encode())
                scrubbed += hits
                files_scrubbed += 1
    out = os.path.join(stage, f)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(data)

# optional overlay: public-only content and public variants of kept files
overlay = "tools/publish/public-content"
if os.path.isdir(overlay):
    ov = sorted(x for x in subprocess.run(
        ["git", "ls-files", "--", overlay], capture_output=True, text=True, check=True
    ).stdout.splitlines())
    for f in ov:
        rel = f[len(overlay) + 1:]
        data = open(f, "rb").read()
        for pat, rep in personal:
            data = data.replace(pat.encode(), rep.encode())
        out = os.path.join(stage, rel)
        os.makedirs(os.path.dirname(out) or stage, exist_ok=True)
        open(out, "wb").write(data)

# openclaims events are self-digested: scrubbing rewrites private paths inside
# provenance fields, which breaks digests pinned in the private corpus. Re-pin
# only the events that no longer validate, using the SDK's own function, then
# run the public tree's own verification command as a hard gate.
ocl_dir = os.path.join(stage, "knowledge", "ane", "openclaims")
try:
    import openclaims as oc
except ImportError:
    sys.exit("FAILED: openclaims SDK required (PYTHON=.venv/bin/python sh tools/publish/publish.sh)")

repinned = 0
for name in ("claims-emitted", "claims-verified", "claims-disputed"):
    p = os.path.join(ocl_dir, name + ".jsonl")
    if not os.path.exists(p):
        continue
    out = []
    for raw in open(p, encoding="utf-8").read().splitlines():
        if not raw.strip():
            continue
        try:
            oc.validate_event(json.loads(raw))
            out.append(raw)
            continue
        except Exception:
            pass
        ev = json.loads(raw)
        ev.pop("digest", None)
        out.append(json.dumps(oc.with_event_digest(ev)))
        repinned += 1
    open(p, "w", encoding="utf-8").write("\n".join(out) + "\n")

gate = subprocess.run([sys.executable,
                       os.path.join(stage, "knowledge", "ane", "tools", "to_openclaims.py"),
                       "--check"], capture_output=True, text=True)
openclaims_ok = gate.returncode == 0 and "0 INVALID" in gate.stdout
print(f"repinned digests: {repinned}")
print("openclaims gate : " + gate.stdout.strip().splitlines()[-1])

leaks = 0
for root, _, xs in os.walk(stage):
    for x in xs:
        data = open(os.path.join(root, x), "rb").read()
        if b"\x00" in data:
            continue
        for pat, _ in personal:
            leaks += data.count(pat.encode())

print(f"staged files    : {len(kept)} (+ overlay)")
print(f"scrubbed        : {scrubbed} occurrences in {files_scrubbed} file-instances")
print(f"privacy grep    : {leaks}")
if leaks:
    print("FAILED: personal tokens survived staging", file=sys.stderr)
    sys.exit(1)
if not openclaims_ok:
    print("FAILED: openclaims --check gate on staging tree", file=sys.stderr)
    print(gate.stdout + gate.stderr, file=sys.stderr)
    sys.exit(1)
print(f"staging ready   : {stage}")
PY
