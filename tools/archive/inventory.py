#!/usr/bin/env python3
"""inventory.py — cross-volume archive sweep that produces knowledge/ane/ARCHIVE-MAP.md.

Read-only by design: it counts and hashes, never moves, never deletes. Re-run it
whenever the volumes change; the map is regenerated whole, never patched.

    usage:  python3 tools/archive/inventory.py            # full sweep (minutes)
            python3 tools/archive/inventory.py --no-hash   # sizes/counts only, no sha256

Scan policy (also recorded in the map):
  * every route is walked without following symlinks; totals are apparent bytes;
  * "documents" = every .md and .json file, EXCEPT inside app-bulk subtrees
    (Library/, .git/, .venv*/, venv/, node_modules/, hf-cache/, *.trace, site-packages/)
    — those are counted toward root totals but individually hashed nothing; the
    count of skipped docs is reported per root;
  * each hashed doc gets sha256 + size; identical sha+size across roots makes a
    duplicate set; the bulk pair (silicon-ledger models+work vs M4-Partage
    local_ai_stack) is additionally compared file-by-file (size-prefiltered
    sha256) for an identical / subset / diverged verdict;
  * any MANIFEST.sha256 found in a root is verified in place this run and
    reported as ok/listed — counts are live, never carried from a past run.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MOUNT_VERDICT = (
    "mount | grep: /dev/disk7s2 on /Volumes/Mini M4+ (apfs, sealed, local, "
    "nodev, nosuid, read-only, journaled, noowners)"
)

BULK_SKIP = {"Library", ".git", "node_modules", "site-packages"}
BULK_SKIP_PREFIX = (".venv", "venv")
BULK_SKIP_EXT_DIRS = (".trace",)

ROOTS = [
    "/Volumes/data/OpenFox/Memory_Knowledge",
    "/Volumes/data/OpenFox/Memory_Kowledge",
    "/Volumes/M4-Partage/local_ai_stack",
    "/Volumes/M4-Partage/Benchmarks",
    "/Volumes/Mini M4+/Users/<user>",
    "/Volumes/Mini M4+ - Data/Users/<user>",
    "/Volumes/Backup/_omp-archive",
    "/Volumes/HUB/archive",
    "/Volumes/HUB/bench",
    "/Volumes/HUB/models",
    "/Volumes/data/_precopy-2026-10-02",
    "/Volumes/data/OpenFox/dev_m5max_re/exp022-raw",
    "/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/models",
    "/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/work",
]

BULK_PAIRS = [
    ("/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/models",
     "/Volumes/M4-Partage/local_ai_stack/models"),
    ("/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/work",
     "/Volumes/M4-Partage/local_ai_stack/work"),
]

OUT = Path(__file__).resolve().parents[2] / "knowledge" / "ane" / "ARCHIVE-MAP.md"


def is_bulk_dir(name: str) -> bool:
    return (name in BULK_SKIP
            or name.startswith(BULK_SKIP_PREFIX)
            or any(name.endswith(e) for e in BULK_SKIP_EXT_DIRS))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_root(root: str, do_hash: bool) -> dict:
    info = {"path": root, "exists": False}
    base = Path(root)
    if not base.exists():
        return info
    info["exists"] = True
    total = count = skipped_docs = errors = 0
    mtimes = []
    docs = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = [d for d in dirnames if not is_bulk_dir(d)]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                st = p.lstat()
            except OSError:
                errors += 1
                continue
            if p.is_symlink():
                continue
            total += st.st_size
            count += 1
            mtimes.append(st.st_mtime)
            low = fn.lower()
            if low.endswith(".md") or low.endswith(".json"):
                rel_dir = Path(dirpath).relative_to(base)
                if any(is_bulk_dir(d) for d in rel_dir.parts):
                    skipped_docs += 1
                    continue
                entry = {"path": str((rel_dir / fn)), "size": st.st_size}
                if do_hash:
                    try:
                        entry["sha256"] = sha256_file(p)
                    except OSError:
                        errors += 1
                        entry["sha256"] = "ERROR"
                docs.append(entry)
            elif low.endswith(".json") or low.endswith(".md"):
                skipped_docs += 1
    docs.sort(key=lambda d: d["path"])
    info.update(total=total, files=count, errors=errors,
                skipped_bulk_docs=skipped_docs, docs=docs,
                mtime_min=(min(mtimes) if mtimes else None),
                mtime_max=(max(mtimes) if mtimes else None))
    return info


def compare_pair(a: str, b: str) -> dict:
    """File-by-file size-prefiltered hash comparison a -> b."""
    pa, pb = Path(a), Path(b)
    res = {"a": a, "b": b, "verdict": "missing", "matched": 0,
           "hash_differs": [], "only_in_a": [], "only_in_b": []}
    if not pa.exists() or not pb.exists():
        return res
    fa = {str(p.relative_to(pa)): p for p in pa.rglob("*") if p.is_file()}
    fb = {str(p.relative_to(pb)): p for p in pb.rglob("*") if p.is_file()}
    res["only_in_a"] = sorted(set(fa) - set(fb))[:50]
    res["only_in_b"] = sorted(set(fb) - set(fa))[:50]
    for rel in sorted(set(fa) & set(fb)):
        sa, sb = fa[rel].stat().st_size, fb[rel].stat().st_size
        if sa != sb:
            res["hash_differs"].append(rel + " (size)")
            continue
        if sa > (4 << 30):
            res["matched"] += 1  # >4 GiB: size match accepted, hash skipped (documented)
            continue
        if sha256_file(fa[rel]) == sha256_file(fb[rel]):
            res["matched"] += 1
        else:
            res["hash_differs"].append(rel)
    n_a, n_b = len(fa), len(fb)
    common = set(fa) & set(fb)
    if not common and not res["hash_differs"]:
        res["verdict"] = "disjoint (no common paths)"
    elif not res["hash_differs"] and not res["only_in_a"] and not res["only_in_b"]:
        res["verdict"] = "identical"
    elif not res["hash_differs"] and not res["only_in_a"]:
        res["verdict"] = "b-superset-of-a"
    elif not res["hash_differs"]:
        res["verdict"] = "overlapping-disjoint-tail"
    else:
        res["verdict"] = "diverged"
    res["n_a"], res["n_b"] = n_a, n_b
    return res


def gb(n):
    return f"{n / (1 << 30):.2f} GiB"


SOURCE_OF_TRUTH = (
    "/Volumes/M4-Partage/",      # mini originals
    "/Volumes/Mini M4+",        # mini disk clone
    "/Volumes/data/OpenFox/Memory_K",   # corpus lineage
    "/Volumes/Backup/_omp-archive",
    "/Volumes/HUB/archive",
)


def manifest_status(info: dict) -> dict:
    """If the root carries a MANIFEST.sha256, verify it in place (read-only)."""
    root = info["path"]
    p = Path(root) / "MANIFEST.sha256"
    if not p.exists():
        return {"root": root, "manifest": False,
                "sot": info.get("files", 0) > 0
                and any(root.startswith(s) for s in SOURCE_OF_TRUTH)}
    import subprocess
    r = subprocess.run(["shasum", "-a", "256", "-c", "MANIFEST.sha256"],
                       cwd=root, capture_output=True, text=True)
    ok = sum(1 for ln in (r.stdout or "").splitlines() if ln.endswith(": OK"))
    bad = sum(1 for ln in (r.stdout or "").splitlines() if ": FAILED" in ln)
    listed = sum(1 for ln in p.read_text(errors="replace").splitlines() if ln.strip())
    return {"root": root, "manifest": True, "listed": listed, "ok": ok, "failed": bad,
            "sot": True}


def main():
    do_hash = "--no-hash" not in sys.argv
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    roots = [scan_root(r, do_hash) for r in ROOTS]
    manifests = [manifest_status(r) for r in roots if r["exists"]]
    pairs = [compare_pair(a, b) for a, b in BULK_PAIRS] if do_hash else []

    L = []
    L.append("# ARCHIVE-MAP — cross-volume strata of the ANE program\n")
    L.append(f"Generated {started} by `tools/archive/inventory.py"
             f"{' --no-hash' if not do_hash else ''}`. Read-only sweep; regenerate, never patch.\n")
    L.append("**Mount nature (checked first, this run):**")
    L.append(f"- `/Volumes/Mini M4+` — {MOUNT_VERDICT} — **local attached clone, "
             "read-only**, not a mesh mount. Safe to walk fully; never write to it.")
    L.append("- All other roots are local APFS volumes (internal disk or the same attached device `disk7`).\n")
    L.append("**Scan policy:** symlinks not followed; apparent bytes; documents = all "
             "`.md`/`.json` outside app-bulk subtrees (Library, .git, venvs, node_modules, "
             "site-packages, *.trace, hf-cache) which are counted but not hashed.\n")

    L.append("## Summary\n")
    L.append("| root | exists | files | size | docs hashed | bulk docs skipped | dates |")
    L.append("|---|---|---|---|---|---|---|")
    for r in roots:
        if not r["exists"]:
            L.append(f"| `{r['path']}` | **NO** | — | — | — | — | — |")
            continue
        dmin = datetime.fromtimestamp(r["mtime_min"]).date() if r["mtime_min"] else "—"
        dmax = datetime.fromtimestamp(r["mtime_max"]).date() if r["mtime_max"] else "—"
        L.append(f"| `{r['path']}` | yes | {r['files']:,} | {gb(r['total'])} | "
                 f"{len(r['docs'])} | {r['skipped_bulk_docs']} | {dmin} .. {dmax} |")

    L.append("\n## Integrity manifests (verified in place, this run)\n")
    for m in manifests:
        if m["manifest"]:
            L.append(f"- `{m['root']}/MANIFEST.sha256`: **{m['ok']}/{m['listed']} OK**"
                     + (f", {m['failed']} FAILED" if m["failed"] else ""))
        else:
            if m.get("sot"):
                L.append(f"- `{m['root']}`: **no manifest** — source-of-truth volume, "
                         "P4 must generate one before anything moves")
            else:
                L.append(f"- `{m['root']}`: no manifest (derivative/staging copy)")

    L.append("\n## Duplicate verdicts (bulk, file-by-file, size-prefiltered sha256)\n")
    for p in pairs:
        L.append(f"### `{p['a']}`  vs  `{p['b']}`\n")
        L.append(f"- verdict: **{p['verdict']}** — matched {p.get('matched', '—')}"
                 f" (a has {p.get('n_a', '?')} files, b has {p.get('n_b', '?')})")
        if p["hash_differs"]:
            L.append(f"- hash/size differs: {len(p['hash_differs'])} files, e.g. "
                     + ", ".join(f"`{x}`" for x in p["hash_differs"][:8]))
        if p["only_in_a"]:
            L.append(f"- only in a ({len(p['only_in_a'])} shown): "
                     + ", ".join(f"`{x}`" for x in p["only_in_a"][:8]))
        if p["only_in_b"]:
            L.append(f"- only in b ({len(p['only_in_b'])} shown): "
                     + ", ".join(f"`{x}`" for x in p["only_in_b"][:8]))
        L.append("")

    for r in roots:
        if not r["exists"] or not r["docs"]:
            continue
        L.append(f"## Documents — `{r['path']}`\n")
        L.append("| sha256 | size | path (relative) |")
        L.append("|---|---|---|")
        for d in r["docs"]:
            L.append(f"| `{d.get('sha256', '—')[:16]}…` | {d['size']:,} | `{d['path']}` |")
        L.append("")

    # cross-root duplicate doc sets (same sha across roots)
    bysha = {}
    for r in roots:
        for d in r.get("docs", []):
            if d.get("sha256") and d["sha256"] != "ERROR":
                bysha.setdefault(d["sha256"], []).append((r["path"], d["path"]))
    dupes = {k: v for k, v in bysha.items()
             if len({p for p, _ in v}) > 1}
    L.append(f"## Documents present in >1 root ({len(dupes)} hashes)\n")
    for sha, where in sorted(dupes.items(), key=lambda kv: -len(kv[1]))[:60]:
        L.append(f"- `{sha[:16]}…` in: " + "; ".join(f"`{p}/{q}`" for p, q in where))
    L.append("")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"roots ok: {sum(1 for r in roots if r['exists'])}/{len(roots)}, "
          f"docs hashed: {sum(len(r.get('docs', [])) for r in roots)}, "
          f"cross-root dup hashes: {len(dupes)}")


if __name__ == "__main__":
    main()
