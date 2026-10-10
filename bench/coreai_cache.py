#!/usr/bin/env python3
"""coreai_cache.py — read-only decoder for the Core AI specialization cache.

The public Core AI route (AIModel / coreai-torch) specializes a portable .aimodel on
first load and persists the result user-readable under ~/Library/Caches/coreai-cache.
Nothing in that cache is documented by Apple; this tool turns one plan (or a whole
cache root) into a structured record so the format can be studied reproducibly.

Stdlib only (plistlib, gzip, json). Never writes to the cache.

  python3 bench/coreai_cache.py --plan <dir>        one plan  -> JSON on stdout
  python3 bench/coreai_cache.py --root <cache>      census    -> JSON list
  python3 bench/coreai_cache.py --root <cache> --summary
  python3 bench/coreai_cache.py --root <cache> --keys   (optsHash/modelHash derivation)

A "plan directory" is any directory containing a *.mpsgraphpackage (the compiler's
persisted output). What this decodes, and the field meanings, are in
results/EXP-026-ane-kitchen/results/coreai_cache_format.md.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import plistlib
import re

# --- MLIR bytecode (magic 4d 4c ef 52), private-dialect string dictionary ----------

MLIR_MAGIC = b"\x4d\x4c\xef\x52"
# dialects observed in the mps / anehlo / placement stack (see format note)
DIALECTS = {
    "builtin", "func", "arith", "memref", "bufferization", "async",
    "mps", "mpsx", "mps_spi", "placement", "gpu", "ane", "anehlo", "raster", "llir",
}
REGION_RE = re.compile(r"(_ANE_region_|_GPU_region_)")


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        head = f.read(2)
    if head == b"\x1f\x8b":
        with gzip.open(path, "rb") as f:
            return f.read()
    with open(path, "rb") as f:
        return f.read()


def _varint(data: bytes, off: int):
    b = data[off]
    off += 1
    if b & 1:
        return b >> 1, off
    if b == 0:
        return int.from_bytes(data[off:off + 8], "little"), off + 8
    n = (b & -b).bit_length() - 1
    return (b | (int.from_bytes(data[off:off + n], "little") << 8)) >> (n + 1), off + n


def mlir_strings(path: str):
    """Return (producer, version, strings) from an MLIR bytecode file, or None."""
    data = _read(path)
    if data[:4] != MLIR_MAGIC:
        return None
    off = 4
    ver, off = _varint(data, off)
    end = data.index(b"\x00", off)
    producer = data[off:end].decode(errors="replace")
    off = end + 1
    while off < len(data):
        raw = data[off]
        off += 1
        secid = raw & 0x7F
        length, off = _varint(data, off)
        if raw & 0x80:
            align, off = _varint(data, off)
            off += (-off) % align
        payload = data[off:off + length]
        if secid == 0:  # string section
            p = 0
            n, p = _varint(payload, p)
            sizes = []
            for _ in range(n):
                s, p = _varint(payload, p)
                sizes.append(s)
            sizes.reverse()
            out = []
            for s in sizes:
                out.append(payload[p:p + s - 1].decode(errors="replace"))
                p += s
            return producer, ver, out
        off += length
    return producer, ver, []


def classify(strings: list) -> dict:
    joined = "\n".join(strings)
    return {
        "ane_region_symbols": len(re.findall(r"_ANE_region_\d+_\d+", joined)),
        "ane_regions_distinct": len(set(re.findall(r"_ANE_region_\d+_\d+", joined))),
        "gpu_regions_distinct": len(set(re.findall(r"_GPU_region_\d+", joined))),
        "dialects": sorted(d for d in DIALECTS if d in strings),
        "mps_attributes": sorted(x for x in strings if x.startswith("mps.")),
        "ane_validation": next((x for x in strings if x.startswith("Incompatible element type for ANE")), None),
        "dtype_whitelist": sorted(m for m in re.findall(r"\b(f8E4M3|si8|ui8|si16|ui16|fp16)\b", " ".join(strings))),
        "has_placement_dialect": "placement" in strings,
        "n_strings": len(strings),
    }


# --- manifest.plist ----------------------------------------------------------------

def _find_descriptor(obj):
    """The compiler descriptor JSON ('{...deviceDescriptor...}') lives as a string."""
    if isinstance(obj, str) and "deviceDescriptor" in obj:
        try:
            return json.loads(obj)
        except Exception:
            return None
    if isinstance(obj, dict):
        for v in obj.values():
            r = _find_descriptor(v)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_descriptor(v)
            if r is not None:
                return r
    return None


def read_manifest(path: str) -> dict:
    d = plistlib.load(open(path, "rb"))
    pv = d.get("Package Version", d)
    ver = next(iter(pv), None) if isinstance(pv, dict) else None
    body = pv.get(ver, {}) if ver else {}
    desc = _find_descriptor(body)
    dd = desc.get("deviceDescriptor") if desc else None
    return {
        "package_version": ver,
        "original": body.get("Original"),
        "gpu_adapter_present": body.get("GPU adapter present"),
        "aneregions_hash": body.get("ANERegionsHash"),
        "callables_hash": body.get("CallablesHash"),
        "binary_resources": body.get("Binary File Resources"),
        "entry_function": (desc or {}).get("entryFunctionName"),
        "device_descriptor": dd,
        "arch_stamp": dd[2] if isinstance(dd, list) and len(dd) > 2 else None,
        "compilation_descriptor": (desc or {}).get("compilationDescriptor"),
        "input_shapes": (desc or {}).get("inputShapes"),
    }


# --- plan / census -----------------------------------------------------------------

def decode_plan(plandir: str) -> dict:
    pkgs = glob.glob(os.path.join(plandir, "**", "*.mpsgraphpackage"), recursive=True)
    if plandir.endswith(".mpsgraphpackage"):
        pkgs = [plandir] + [p for p in pkgs if p != plandir]
    rec = {"plan_dir": plandir, "packages": []}
    for pkg in pkgs:
        p = {"package": pkg}
        mpl = os.path.join(pkg, "manifest.plist")
        if os.path.exists(mpl):
            try:
                p["manifest"] = read_manifest(mpl)
            except Exception as e:
                p["manifest_error"] = str(e)
        for kind in ("original_model_*.mpsgraph", "specialized_model_*.mpsgraph"):
            for f in sorted(glob.glob(os.path.join(pkg, kind))):
                info = mlir_strings(f)
                if info:
                    prod, ver, strs = info
                    p[os.path.basename(f)] = {
                        "producer": prod, "bytecode_version": ver, **classify(strs),
                    }
        hwx = glob.glob(os.path.join(pkg, "**", "*.hwx"), recursive=True)
        p["hwx"] = [{"path": h, "bytes": os.path.getsize(h)} for h in hwx]
        llir = glob.glob(os.path.join(pkg, "**", "binary_*.llir.bundle"), recursive=True)
        p["llir_bundle"] = bool(llir)
        rec["packages"].append(p)
    return rec


def find_plans(root: str):
    """Yield (plan_dir, rel) for each *.mpsgraphpackage parent under root."""
    for pkg in glob.glob(os.path.join(root, "**", "*.mpsgraphpackage"), recursive=True):
        yield os.path.dirname(pkg)


def census(root: str) -> list:
    seen, out = set(), []
    for plandir in find_plans(root):
        if plandir in seen:
            continue
        seen.add(plandir)
        rel = os.path.relpath(plandir, root)
        parts = rel.split(os.sep)
        if re.fullmatch(r"\d+\.\d+\.\d+", parts[0]):
            layout, model_hash, opts_hash = "pyver", (parts[1] if len(parts) > 1 else None), None
        else:
            layout = "osbuild"
            model_hash = parts[2] if len(parts) > 2 else None
            opts_hash = parts[3] if len(parts) > 3 else None
        rec = {
            "rel": rel,
            "layout": layout,
            "model_hash": model_hash,
            "opts_hash": opts_hash,
        }
        rec.update(decode_plan(plandir))
        out.append(rec)
    return out


def summary(recs: list) -> dict:
    archs, opts_freq, model_freq, layouts = {}, {}, {}, {}
    ane_plans = 0
    for r in recs:
        layouts[r.get("layout")] = layouts.get(r.get("layout"), 0) + 1
        m = next((p.get("manifest") for p in r["packages"] if p.get("manifest")), None)
        arch = m.get("arch_stamp") if m else None
        if arch:
            archs[arch] = archs.get(arch, 0) + 1
        if r.get("opts_hash"):
            opts_freq[r["opts_hash"]] = opts_freq.get(r["opts_hash"], 0) + 1
        if r.get("model_hash"):
            model_freq[r["model_hash"]] = model_freq.get(r["model_hash"], 0) + 1
        ne = 0
        for p in r["packages"]:
            for k, v in p.items():
                if isinstance(v, dict) and k.startswith("specialized_model_"):
                    ne = max(ne, v.get("ane_regions_distinct", 0))
        if ne:
            ane_plans += 1
    return {
        "plans": len(recs),
        "layouts": layouts,
        "arch_stamps": archs,
        "plans_with_ane_regions": ane_plans,
        "distinct_opts_hash": len(opts_freq),
        "opts_hash_reused_across_models": sorted(h for h, c in opts_freq.items() if c > 1),
        "distinct_model_hash": len(model_freq),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan")
    ap.add_argument("--root", default=os.path.expanduser("~/Library/Caches/coreai-cache"))
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--keys", action="store_true")
    a = ap.parse_args(argv)
    if a.plan:
        print(json.dumps(decode_plan(a.plan), indent=2, sort_keys=True))
        return 0
    recs = census(a.root)
    if a.summary:
        print(json.dumps(summary(recs), indent=2, sort_keys=True))
    elif a.keys:
        print(json.dumps(summary(recs), indent=2, sort_keys=True))
    else:
        print(json.dumps(recs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
