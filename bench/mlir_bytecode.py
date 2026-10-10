#!/usr/bin/env python3
"""mlir_bytecode.py — read MLIR bytecode (the Core AI mpsgraph plans) without
MLIR, and optionally rewrite it so stock `mlir-opt` can print the IR.

Two operations:

  entries FILE          decode the file's section table, the dialect list, and the
                        Attribute/Type entry table (dialect, size, custom flag).
  rewrite IN OUT        rewrite the private dialects' attribute/type entries into
                        textual PLACEHOLDERS (loc(unknown) / i64) so that
                        `mlir-opt --load-dialect-plugin=<stub> --allow-unregistered-dialect`
                        can parse and print the IR. Only the private dialects'
                        VALUES are stubbed; builtin-encoded values (mps.aneArch,
                        mps.aneRegionsSHA, shapes, function_type) survive, and the
                        op graph / SSA wiring is fully recovered.

Mirrors MLIR 22 BytecodeReader.cpp. Stdlib only. See
results/EXP-026-ane-kitchen/results/p2b_model_src_ir.txt (recovered IR) and
p2b_mps_dialect_wall.txt (the path to it).
"""
import argparse
import sys

STOCK = {"builtin", "func", "arith", "memref", "bufferization", "async", "gpu",
         "llvm", "index", "math", "cf", "scf", "complex", "tensor", "vector",
         "linalg", "shape", "emitc", "sparse_tensor", "ub", "ptr", "acc", "amdgpu",
         "amx", "arm_neon", "arm_sme", "dlti", "irdl", "ml_program", "mpi", "nvgpu",
         "nvvm", "omp", "pdl", "pdl_interp", "quant", "rocdl", "shard", "smt",
         "spirv", "tosa", "transform", "wasmssa", "x86vector", "xegpu", "xevm"}


class R:
    def __init__(self, d, o=0):
        self.d, self.o = d, o

    def empty(self):
        return self.o >= len(self.d)

    def byte(self):
        b = self.d[self.o]; self.o += 1; return b

    def varint(self):
        b = self.byte()
        if b & 1:
            return b >> 1
        if b == 0:
            v = int.from_bytes(self.d[self.o:self.o + 8], "little"); self.o += 8; return v
        n = (b & -b).bit_length() - 1
        v = b | (int.from_bytes(self.d[self.o:self.o + n], "little") << 8)
        self.o += n
        return v >> (n + 1)

    def vflag(self):
        v = self.varint(); return v >> 1, bool(v & 1)

    def take(self, n):
        v = self.d[self.o:self.o + n]; self.o += n; return v


def enc(v):                       # MLIR: single byte if small, else 0x00 + LE64
    return bytes([(v << 1) | 1]) if v < 64 else b"\x00" + v.to_bytes(8, "little")


def enc_flag(v, flag):
    return enc((v << 1) | int(flag))


def parse(data):
    r = R(data, 4)
    ver = r.varint()
    end = data.index(b"\x00", r.o)
    producer = data[r.o:end]; r.o = end + 1
    secs = []
    while not r.empty():
        raw = r.byte()
        secid = raw & 0x7F
        aligned = bool(raw & 0x80)
        length = r.varint()
        align = r.varint() if aligned else 0
        if aligned:
            r.o += (-r.o) % align
        secs.append({"id": secid, "aligned": aligned, "align": align,
                     "data": r.take(length)})
    return ver, producer, secs


def emit(ver, producer, secs):
    out = bytearray(b"\x4d\x4c\xef\x52") + enc(ver) + producer + b"\x00"
    for s in secs:
        out += bytes([s["id"] | (0x80 if s["aligned"] else 0)])
        out += enc(len(s["data"]))
        if s["aligned"]:
            out += enc(s["align"])
            out += b"\x00" * ((-len(out)) % s["align"])
        out += s["data"]
    return bytes(out)


def strings_and_dialects(S):
    sr = R(S[0]["data"]); n = sr.varint()
    sizes = [sr.varint() for _ in range(n)][::-1]
    strs = []
    for sz in sizes:
        strs.append(S[0]["data"][sr.o:sr.o + sz - 1].decode(errors="replace")); sr.o += sz
    dr = R(S[1]["data"]); nd = dr.varint(); dnames = []
    for _ in range(nd):
        idx, vf = dr.vflag()
        nm = strs[idx]
        if vf:
            dr.byte(); dr.take(dr.varint())
        dnames.append(nm)
    return strs, dnames


def read_table(S, dnames):
    ot = R(S[3]["data"]); na = ot.varint(); nt = ot.varint()
    sec2 = S[2]["data"]; cur = 0
    groups = {"attr": [], "type": []}
    for kind, count in (("attr", na), ("type", nt)):
        got = 0
        while got < count:
            di = ot.varint(); ne = ot.varint()
            g = {"di": di, "entries": []}
            for _ in range(ne):
                size, custom = ot.vflag()
                g["entries"].append({"size": size, "custom": custom,
                                     "data": sec2[cur:cur + size]})
                cur += size; got += 1
            groups[kind].append(g)
    return na, nt, groups


def cmd_entries(path):
    _, _, secs = parse(open(path, "rb").read())
    S = {s["id"]: s for s in secs}
    _, dnames = strings_and_dialects(S)
    na, nt, groups = read_table(S, dnames)
    print(f"dialects: {dnames}")
    print(f"attributes={na} types={nt}")
    for kind in ("attr", "type"):
        for i, g in enumerate(groups[kind]):
            for e in g["entries"]:
                tag = "CUSTOM" if e["custom"] else "asm   "
                print(f"  {kind}[{i:3}] {dnames[g['di']]:9} {tag} size={e['size']:6} "
                      f"{e['data'][:20].hex()}")


def cmd_rewrite(inp, outp, pad_attrs=0):
    ver, producer, secs = parse(open(inp, "rb").read())
    order = [s["id"] for s in secs]
    S = {s["id"]: s for s in secs}
    _, dnames = strings_and_dialects(S)
    na, nt, groups = read_table(S, dnames)
    rewritten = 0
    for kind in ("attr", "type"):
        for g in groups[kind]:
            if dnames[g["di"]] in STOCK:
                continue
            for e in g["entries"]:
                e["data"] = (b"loc(unknown)" if kind == "attr" else b"i64") + b"\x00"
                e["custom"] = False
                rewritten += 1
    # Unknown ops read their "properties" as an attribute index; those bytes are
    # not a real index, so some plans reference an out-of-range slot. Padding the
    # table absorbs them as placeholders. 0 = off.
    if pad_attrs and pad_attrs > na:
        bi = dnames.index("builtin") if "builtin" in dnames else 0
        groups["attr"].append({"di": bi, "entries": [
            {"size": 12, "custom": False, "data": b"loc(unknown)\x00"}] * (pad_attrs - na)})
        na = pad_attrs
    new2 = bytearray(); new3 = bytearray(enc(na) + enc(nt))
    for kind in ("attr", "type"):
        for g in groups[kind]:
            new3 += enc(g["di"]) + enc(len(g["entries"]))
            for e in g["entries"]:
                new2 += e["data"]
                new3 += enc_flag(len(e["data"]), e["custom"])
    S[2]["data"] = bytes(new2)
    S[3]["data"] = bytes(new3)
    open(outp, "wb").write(emit(ver, producer, [S[i] for i in order]))
    print(f"rewrote {rewritten} entries (pad_attrs={pad_attrs}) -> {outp}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("entries"); e.add_argument("file")
    w = sub.add_parser("rewrite"); w.add_argument("inp"); w.add_argument("outp")
    w.add_argument("--pad-attrs", type=int, default=0)
    a = ap.parse_args(argv)
    if a.cmd == "entries":
        cmd_entries(a.file)
    else:
        cmd_rewrite(a.inp, a.outp, a.pad_attrs)


if __name__ == "__main__":
    main()
