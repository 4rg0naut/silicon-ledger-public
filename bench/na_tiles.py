#!/usr/bin/env python3
"""C6 valid-tile matched A/B — matmul2d (64x32 tile, K=64) vs matched non-tensor matmul.

R8 (EXP-024 stage4_load.log): matmul2d MULTI-tile dispatch silently no-ops on macOS
27.0-beta GPUCompiler 32023; the single 64x32 K=64 tile computes ALL-CORRECT. Zakharko
(SOURCES TZAKHARKO-NA) puts the NA threshold at tiles >=32x32 and matrix fp16 at
~1024 FLOPS/core/cycle, so the valid shape is the honest probe size.

Plumbing is our proven TorchMetalKernel route (repos/coreai-model-zoo
knowledge/_tensorops_proto/m4_speed_ab.py; tensor coords are TRANSPOSED vs numpy —
torch[M,K] -> extents [K,M], tgid.x -> N step 32, tgid.y -> M step 64).

Arms:
  A  tensorops : embedded matmul2d kernel, grid (1,1), 128 threads  (NA-path candidate)
  B  mpsgraph  : torch a@b default CoreAI/MPSGraph lowering, same shape, same traffic
                 (shader-path at this size per Tungsten envelope M>=400 caveat)

Correctness gate BEFORE timing: numpy fp32-reference checksum PASS on both arms.
Then >=2 alternations of timed rounds; GFLOPS printed per arm. Unprivileged.
Honesty: at 64x32 even the tensor-ops arm may execute on shader pipes (small tile,
dispatch-bound); a near-zero delta is a documented outcome, not a failed measurement —
the NA ceiling number comes from the C7 sudo window with sustained load.

Run: .venv-conv/bin/python -u bench/na_tiles.py [--iters 200] [--rounds 3]
"""
import argparse, asyncio, time
from pathlib import Path
import tempfile
import numpy as np
import torch
import torch.nn as nn
from coreai_torch import TorchMetalKernel, TorchConverter, get_decomp_table, MetalParameter
from coreai.runtime import NDArray

M, N, K = 64, 32, 64

MM_TENSOR_SRC = r"""
    constexpr auto desc = matmul2d_descriptor(64, 32,
        static_cast<int>(metal::dynamic_extent), false, false, false);
    matmul2d<desc, execution_simdgroups<4>> op;
    auto mA = A.slice(0, tgid.y * 64);
    auto mB = B.slice(tgid.x * 32, 0);
    auto mC = C.slice(tgid.x * 32, tgid.y * 64);
    op.run(mA, mB, mC);
"""


MM_SIMDGRP_SRC = r"""
    threadgroup half a_t[4096];
    threadgroup half b_t[2048];
    for (uint i = lid.x; i < 4096u; i += 128u)
        a_t[i] = A[metal::array<uint, 2>{{i % 64u, i / 64u}}];
    for (uint i = lid.x; i < 2048u; i += 128u)
        b_t[i] = B[metal::array<uint, 2>{{i % 32u, i / 32u}}];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    for (uint o = lid.x; o < 2048u; o += 128u) {
        uint m = o / 32u, n = o % 32u;
        float acc = 0.0f;
        for (int k = 0; k < 64; k++)
            acc += float(a_t[m * 64 + k]) * float(b_t[k * 32 + n]);
        C[metal::array<uint, 2>{{n, m}}] = acc;
    }
"""


def build(mod, a, b, kernels):
    ep = torch.export.export(mod.eval(), (a, b)).run_decompositions(get_decomp_table())
    conv = TorchConverter()
    if kernels:
        conv.register_custom_kernels(kernels)
    conv.add_exported_program(ep, input_names=["A", "B"], output_names=["C"])
    prog = conv.to_coreai(); prog.optimize()
    return prog


async def bench(prog, a, b, iters, rounds):
    with tempfile.TemporaryDirectory() as td:
        asset = prog.save_asset(Path(td) / "m.aimodel")
        async with asset.executable() as ai:
            import time as _t
            fn = None
            for attempt in range(4):
                try:
                    fn = ai.load_function("main")
                    break
                except RuntimeError as e:
                    if "no memory" in str(e) and attempt < 3:
                        wait = 2 * (attempt + 1)
                        print(f"  load failed (e53 class), retry {attempt+1}/3 in {wait}s")
                        _t.sleep(wait); continue
                    raise
            A = NDArray(a); B = NDArray(b)
            out = await fn({"A": A, "B": B})
            await fn({"A": A, "B": B})
            g = out["C"].numpy().astype(np.float32)
            medians = []
            for _ in range(rounds):
                ts = []
                for _ in range(iters):
                    t0 = time.perf_counter()
                    await fn({"A": A, "B": B})
                    ts.append((time.perf_counter() - t0) * 1e6)
                medians.append(float(np.median(ts)))
    return medians, g


def _mmdef(x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    return x @ y


class _Tee:
    def __init__(self, *streams): self.s = streams
    def write(self, d):
        for st in self.s: st.write(d); st.flush()
    def flush(self):
        for st in self.s: st.flush()
    def isatty(self): return False
    @property
    def encoding(self): return 'utf-8'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--tag", choices=["tensorops", "simdgroup", "mpsgraph", "both", "all"], default="both")
    ap.add_argument("--log", default=None, help="also write harness stdout to this file")
    ap.add_argument("--dry", action="store_true", help="compile+convert only (CPU); skip program load/timing")
    args = ap.parse_args()

    torch.manual_seed(0)
    a_np = torch.randn(M, K, dtype=torch.float16).numpy()
    b_np = torch.randn(K, N, dtype=torch.float16).numpy()
    ref = a_np.astype(np.float32) @ b_np.astype(np.float32)
    a = torch.from_numpy(a_np); b = torch.from_numpy(b_np)

    kernel = TorchMetalKernel(
        name="mm2d_valid", input_names=["A", "B"], result_names=["C"], src=MM_TENSOR_SRC,
        torch_defn=_mmdef,
        metal_params=[MetalParameter("tgid", "uint2", "threadgroup_position_in_grid")])

    class MM2D(nn.Module):
        def forward(self, x, y):
            return kernel(x, y, threads_per_grid=(128, 1, 1),
                          threads_per_thread_group=(128, 1, 1),
                          result_shapes=[[M, N]])

    ksimd = TorchMetalKernel(
        name="msl_simt_fp16", input_names=["A", "B"], result_names=["C"], src=MM_SIMDGRP_SRC,
        torch_defn=_mmdef,
        metal_params=[MetalParameter("lid", "uint3", "thread_position_in_threadgroup")])

    class MM2DS(nn.Module):
        def forward(self, x, y):
            return ksimd(x, y, threads_per_grid=(128, 1, 1),
                         threads_per_thread_group=(128, 1, 1),
                         result_shapes=[[M, N]])

    class MMref(nn.Module):
        def forward(self, x, y):
            return x @ y

    import contextlib, sys
    logs = [sys.stdout]
    if args.log:
        logs.append(open(args.log, "w"))
    ctx = contextlib.redirect_stdout(_Tee(*logs))
    ctx.__enter__()

    progs = {"tensorops_64x32": build(MM2D(), a, b, [kernel])}
    try:
        progs["msl_simdgroup"] = build(MM2DS(), a, b, [ksimd])
    except Exception as e:
        print(f"simdgroup arm build failed (continuing without it): {str(e)[:160]}")
    progs["mpsgraph_ref"] = build(MMref(), a, b, None)
    if args.tag in ("tensorops", "simdgroup", "mpsgraph"):
        key = {"simdgroup": "msl_simdgroup"}.get(args.tag, args.tag)
        progs = {k: v for k, v in progs.items() if k.startswith(key) or (key == "tensorops" and False)}
    if args.tag == "both":
        progs = {k: v for k, v in progs.items() if k in ("tensorops_64x32", "mpsgraph_ref")}

    if args.dry:
        print('DRY: both arms compiled+converted (CPU path) — program load skipped')
        ctx.__exit__(None, None, None)
        return 0

    flops = 2.0 * M * N * K
    checksums = {}
    rounds = {t: [] for t in progs}
    for rnd in range(args.rounds):          # alternation lives here: arm order per round
        for tag, prog in progs.items():
            med, g = asyncio.run(bench(prog, a_np, b_np, args.iters, 1))
            err = float(np.max(np.abs(g - ref)))
            checksums[tag] = (err, err < 5e-2)
            rounds[tag].append(med[0])
            if rnd == 0:
                print(f"checksum {tag:15s} max_abs_err={err:.3e} -> {'PASS' if err < 5e-2 else 'FAIL'}")
    if not all(v[1] for v in checksums.values()):
        print("GATE FAIL: arm(s) failed checksum — no timing claimed (R8 discipline)"); return 1

    for rnd in range(args.rounds):
        for tag in progs:
            us = rounds[tag][rnd]
            print(f"round {rnd} {tag:15s} {us:8.1f} us/predict  {flops/(us*1e-6)/1e9:7.3f} GFLOPS")
    if "tensorops_64x32" in progs and "mpsgraph_ref" in progs:
        a_us = np.median(rounds["tensorops_64x32"]); b_us = np.median(rounds["mpsgraph_ref"])
        print(f"VERDICT: matched A/B delivered; tensorops/mpsgraph median ratio {b_us/a_us:.3f}")
    else:
        print(f"VERDICT: single-arm run ({list(progs)}); checksum PASS, GFLOPS above")
    print("note: at 64x32 both arms may ride shader pipes (Tungsten envelope); "
          "NA attribution awaits the C7 sustained-load sudo window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
