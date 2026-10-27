#!/usr/bin/env python3
"""Build / maintain results/measurements.json from a compact source table.

The committed measurements.json is the single source of truth and is NOT
regenerable from this table alone: it also holds the verified-extracted rows
(merged by bench/verify_extraction.py from fragments that are ephemeral, not
in this repo). So this tool is NON-DESTRUCTIVE by default:

  default         validate the table + ledger, report shared/new/drift, and
                  leave measurements.json BYTE-IDENTICAL
  --apply-new     append ROW ids that are not yet in the ledger
  --force         also overwrite shared ids with the ROWS values
  (no file)       fresh build from ROWS only

Re-curation of a row that is already in the ledger is reported as drift and
applied only with --force; a ROW removed from this table does NOT remove the
ledger record. Adding a row is still one tuple (22 fields through
provenance/date/command, or all 26 with the energy slots).
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "measurements.json"

M4 = "Apple M4 (h16g), 16 GB"
M4MAX = "Apple M4 Max"
RYZEN = "AMD Ryzen 5 3600, 4 threads"
M5MAX = "Apple M5 Max (h17c), 128 GB"
# id, model, checkpoint, params_m, runtime, placement, dtype, seq_len, regions,
#   benchmark, split, scope, tiers, metric, value, unit,
#   latency_ms, latency_unit, hardware, provenance, date, command
ROWS = [
    # ---------------- EXP-045/046 closed-claims receipts (2026-10-27) ----------------
    ("exp045-pso-cold-vs-warm", "MTLComputePipelineState cold vs MTLBinaryArchive warm", None, None, "Metal", "GPU", None, None, None,
     "EXP-045 arm A", None, "64 PSOs, loaded window (upper-bound)", None, "cold-over-warm ratio", 2550.44, "x per-PSO",
     3.866, "per PSO cold (warm 0.002)", M5MAX, "ours", "2026-10-27", "results/EXP-045-closed-claims/harness/mtl_compile_ladder.m a"),
    ("exp045-metallib-load-per-variant", "8.5k-variant metallib load vs runtime compile", None, None, "Metal", "GPU", None, None, None,
     "EXP-045 arm B", None, "ladder 128/512/2048 + extrap 8582, loaded window", None, "load per variant", 0.0006, "ms @2048-rung (runtime compile 0.275)",
     None, None, M5MAX, "ours", "2026-10-27", "mtl_compile_ladder.m b"),
    ("exp045-fastmath-tanh-bitdiff", "fastMathEnabled tanh bit-equality vs strict", None, None, "Metal", "GPU", "fp32", None, None,
     "EXP-045 arm C", None, "1024-pt band vs double ref", None, "bit-equal fraction", 0.556, "OFF vs ON (sin = 1.000)",
     None, None, M5MAX, "ours", "2026-10-27", "mtl_compile_ladder.m c"),
    ("exp045-cpu-copy-64mb-ratio", "CPU memcpy-into-shared vs GPU copy @64 MB", None, None, "Metal/Accelerate", "GPU+CPU", None, None, None,
     "EXP-045 arm D", None, "5-size ladder, ssh window", None, "cpu-over-gpu ratio", 1.65, "x @64 MB (3x claim upper-bounded)",
     2.279, "per 64 MB copy CPU (GPU 1.382)", M4, "ours", "2026-10-27", "retro_probe.m d"),
    ("exp045-qos-itps-mini", "DEFAULT vs USER_INITIATED itps under 9 default-class loaders", None, None, "pthread QoS", "CPU", None, None, None,
     "EXP-045 arm E", None, "5 s window, mini", None, "itps ratio", 0.703, "DEFAULT/USER_INITIATED (Studio homogeneous 1.003)",
     None, None, M4, "ours", "2026-10-27", "retro_probe.m e"),
    ("exp045-residency-2p2gb", "2.2 GB pinned working set on 16 GB box", None, None, "vm", "CPU", None, None, None,
     "EXP-045 arm F", None, "latency percentiles during pin", None, "touch time", 0.16, "s (p50 <1us p999 7us max 1182us)",
     None, None, M4, "ours", "2026-10-27", "retro_probe.m f"),
    ("exp045-sgemm-512-m5", "cblas_sgemm 512^3 CPU AMX", None, None, "Accelerate", "CPU", "fp32", None, None,
     "EXP-045 B5", None, "200 reps, loaded window upper-bound", None, "throughput", 1428.9, "GFLOPS (NCM external claim 1540)",
     None, None, M5MAX, "ours", "2026-10-27", "retro_probe.m b"),
    ("exp045-sgemm-512-mini", "cblas_sgemm 512^3 CPU AMX", None, None, "Accelerate", "CPU", "fp32", None, None,
     "EXP-045 B5", None, "200 reps, load 1.2 retake", None, "throughput", 1688.5, "GFLOPS (first run 1493.9 @1.4)",
     None, None, M4, "ours", "2026-10-27", "retro_probe.m b"),
    ("exp045-vdsp-stream-mini", "vDSP_sve contiguous stream 4 Mi elements", None, None, "Accelerate", "CPU", "fp32", None, None,
     "EXP-045 B5", None, "two runs stable", None, "bandwidth", 105.4, "GB/s (NCM external claim 37.8 - path-limited)",
     None, None, M4, "ours", "2026-10-27", "retro_probe.m b"),
    ("exp045-vdsp-stream-m5", "vDSP_sve contiguous stream 4 Mi elements", None, None, "Accelerate", "CPU", "fp32", None, None,
     "EXP-045 B5", None, "loaded window upper-bound", None, "bandwidth", 53.6, "GB/s (above NCM claim 37.8 - their path limiter)",
     None, None, M5MAX, "ours", "2026-10-27", "retro_probe.m b"),
    ("exp046-bracket-p50-m5", "commit->complete empty-kernel bracket", None, None, "Metal", "GPU", None, None, None,
     "EXP-046 P46", None, "idle pass, loaded window, WindowServer present", None, "bracket p50", 113.0, "us (GPU-exec span p50 2.0 us)",
     0.113, "per commit->complete", M5MAX, "ours", "2026-10-27", "retro_probe.m p"),
    ("exp046-bracket-p50-mini", "commit->complete empty-kernel bracket", None, None, "Metal", "GPU", None, None, None,
     "EXP-046 P46", None, "idle pass, loadavg 1.2 window", None, "bracket p50", 185.0, "us (GPU-exec span p50 3.46 us)",
     0.185, "per commit->complete", M4, "ours", "2026-10-27", "retro_probe.m p"),

    # ---------------- EXP-020: ANE DMA notch (M4) — closes O-8 ----------------
    ("exp020-ane-dma-1mib", "ANE DMA transfer, 1 MiB/core", None, None, "bare-metal", "ANE", None, None, 1,
     "EXP-020 DMA window", None, "6-run median fwd+rev", None, "throughput", 23.65, "GB/s",
     None, None, M4, "ours", "2026-09-25", "results/EXP-020-ane-dma-notch (notch_1mib)"),
    ("exp020-ane-dma-control-16k", "ANE DMA transfer, 16 KiB control", None, None, "bare-metal", "ANE", None, None, 1,
     "EXP-020 DMA window", None, "6-run median fwd+rev", None, "throughput", 43.53, "GB/s",
     None, None, M4, "ours", "2026-09-25", "results/EXP-020-ane-dma-notch (control_16k)"),
    ("exp020-ane-dma-split-2x", "ANE DMA transfer, 1 MiB/core split in two", None, None, "bare-metal", "ANE", None, None, 1,
     "EXP-020 DMA window", None, "6-run median fwd+rev", None, "throughput", 43.55, "GB/s",
     None, None, M4, "ours", "2026-09-25", "results/EXP-020-ane-dma-notch (split_2x) = 1.84x recovery"),

    # ---------------- decision models: JevBench v1.3.0 ----------------
    ("laya-en-ane-s256", "Laya English (ModernBERT-large)", "convaiinnovations/laya", 421,
     "Core AI", "ANE", "fp16", 256, 2, "JevBench v1.3.0", "public", "231 of 534", "easy+standard+hard",
     "Intelligence", 41.5, "chance-corrected 0-100", 68.1, "per decision (all options, one pass)", M4,
     "ours", "2026-09-22", "bench/jevbench_ane.py + laya_ane_bench.py"),
    ("laya-en-cpu-published", "Laya English (ModernBERT-large)", "convaiinnovations/laya", 421,
     "CPU", "CPU", "fp32", 512, None, "JevBench v1.3.0", "full", "534 items", "easy+standard+judge+hard",
     "Intelligence", 45.8, "chance-corrected 0-100", 790.0, "per decision", RYZEN,
     "third-party (JevBench v1.3.0 #33)", "2026-09-21", "jevbench/adapters/laya_local.py"),
    ("von-ane-s256", "Von-1.0 (ModernBERT-large, NLI)", "wfzyx/von", 395,
     "Core AI", "ANE", "fp16", 256, 3, "JevBench v1.3.0", "public", "231 of 534", "easy+standard+hard",
     "Intelligence", 36.2, "chance-corrected 0-100", 105.0, "per decision (N option passes)", M4,
     "ours", "2026-09-22", "bench/jevbench_ane.py (VonANEAdapter)"),
    ("von-cpu-s256", "Von-1.0 (ModernBERT-large, NLI)", "wfzyx/von", 395,
     "Core AI", "CPU", "fp16", 256, None, "JevBench v1.3.0", "public", "231 of 534", "easy+standard+hard",
     "Intelligence", 36.2, "chance-corrected 0-100", 98.0, "per decision (N option passes)", M4,
     "ours", "2026-09-22", "bench/jevbench_ane.py --compute cpu"),
    ("laya-ml-ane-s1024", "Laya-multilingual (mmBERT-base)", "convaiinnovations/laya-multilingual", 149,
     "Core AI", "ANE", "fp16", 1024, 2, "JevBench v1.3.0", "public", "231 of 534", "easy+standard+hard",
     "Intelligence", 22.3, "chance-corrected 0-100", 106.8, "per decision (all options, one pass)", M4,
     "ours", "2026-09-22", "bench/jevbench_ane.py --model-dir models/laya-multilingual"),

    # ---------------- embedders: MTEB SciFact / NFCorpus ----------------
    ("granite97m-ane-scifact", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 512, 1, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.68546, "ndcg@10", 2.14, "per embedding", M4,
     "ours", "2026-09-20", "bench/granite_ane_variants.py"),
    ("minilm-l6-scifact", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     None, None, None, None, None, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.64508, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),
    ("bge-small-scifact", "bge-small-en-v1.5", "BAAI/bge-small-en-v1.5", 33,
     None, None, None, None, None, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.71273, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),
    ("bge-base-scifact", "bge-base-en-v1.5", "BAAI/bge-base-en-v1.5", 110,
     None, None, None, None, None, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.74345, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),
    ("mpnet-base-scifact", "mpnet-base", "sentence-transformers/all-mpnet-base-v2", 110,
     None, None, None, None, None, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.65570, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),
    ("granite97m-ane-nfcorpus", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 512, 1, "MTEB NFCorpus", "test", "full", None,
     "ndcg@10", 0.29470, "ndcg@10", None, "per embedding", M4,
     "ours", "2026-09-20", "bench/granite_ane_variants.py"),
    ("granite97m-ane-french", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 512, 1, "MTEB (French subset)", "test", "full", None,
     "ndcg@10", 0.6551, "ndcg@10", None, "per embedding", M4,
     "ours", "2026-09-21", "bench/mteb_french_tasks.py"),
    ("e5-small-french", "multilingual-e5-small", "intfloat/multilingual-e5-small", 118,
     None, None, None, None, None, "MTEB (French subset)", "test", "full", None,
     "ndcg@10", 0.6334, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),

    # ---------------- reranker + pipeline ----------------
    ("qwen3-reranker-ane", "Qwen3-Reranker-0.6B", "Qwen/Qwen3-Reranker-0.6B", 600,
     "Core AI", "ANE", "fp16", 512, 1, "SciFact (BEIR)", "test", "full", None,
     "ndcg@10 delta", 0.07861, "absolute delta over retriever order", None, None, M4,
     "ours", "2026-09-21", "bench/gate_reranker_ane.py"),
    ("pipeline-ours-reranked", "Granite-97M chunk-indexed + Qwen3-Reranker", "see EXP-014", 97,
     "Core AI", "ANE", "fp16", 512, 1, "SciFact (BEIR)", "test", "full", None,
     "ndcg@10", 0.75860, "ndcg@10", None, None, M4,
     "ours", "2026-09-21", "bench/rerank_retrieval.py"),
    ("pipeline-bgebase-reranked", "bge-base-en-v1.5 + Qwen3-Reranker", "BAAI/bge-base-en-v1.5", 109,
     None, None, None, None, None, "SciFact (BEIR)", "test", "full", None,
     "ndcg@10", 0.77204, "ndcg@10", None, None, None,
     "ours (same reranker, swapped retriever)", "2026-09-21", "bench/rerank_retrieval.py"),

    # ---------------- ANE encoder ports: residency + speed ----------------
    ("minilm-coreml-ane", "all-MiniLM-L6-v2 (Core ML)", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "ANE (compute_units=ALL)", "fp16", 128, None, "latency microbench", None, "128-token encodes", None,
     "throughput", 1363.0, "embeddings/s", 0.73, "per embedding (mean)", M4,
     "ours", "2026-09-20", "bench/bench_encoder.py"),
    ("minilm-coreml-cpu", "all-MiniLM-L6-v2 (Core ML)", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "CPU_ONLY", "fp16", 128, None, "latency microbench", None, "128-token encodes", None,
     "throughput", 597.0, "embeddings/s", 1.68, "per embedding (mean)", M4,
     "ours", "2026-09-20", "bench/bench_encoder.py"),
    ("minilm-coreml-gpu", "all-MiniLM-L6-v2 (Core ML)", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "CPU_AND_GPU", "fp16", 128, None, "latency microbench", None, "128-token encodes", None,
     "throughput", 480.0, "embeddings/s", 2.08, "per embedding (mean)", M4,
     "ours", "2026-09-20", "bench/bench_encoder.py"),
    ("granite97m-fp16-13reg", "Granite-Embedding-97M fp16 (as exported)", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 128, 13, "latency microbench", None, "4000 warm iterations", None,
     "latency", 13.19, "ms", 13.19, "per embedding", M4,
     "ours", "2026-09-20", "bench/granite_ane_variants.py"),
    ("granite97m-fp16-1reg", "Granite-Embedding-97M fp16 + 2 fp32-op removals", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 128, 1, "latency microbench", None, "4000 warm iterations", None,
     "latency", 4.60, "ms", 4.60, "per embedding", M4,
     "ours", "2026-09-20", "bench/granite_ane_variants.py"),
    ("granite97m-fp32-0reg", "Granite-Embedding-97M fp32 (published)", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "GPU (silent fallback)", "fp32", 128, 0, "latency microbench", None, "4000 warm iterations", None,
     "latency", 4.31, "ms", 4.31, "per embedding", M4,
     "ours", "2026-09-20", "coreai-build compile --preferred-compute neural-engine"),
    ("granite97m-w8", "Granite-Embedding-97M w8", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "int8-affine + fp16", 128, 13, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.68546, "ndcg@10", 19.48, "per embedding", M4,
     "ours", "2026-09-20", "bench/export_granite_w8_fp16.py --bits 8"),
    ("granite97m-w6", "Granite-Embedding-97M w6", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "int6-affine + fp16", 128, 14, "MTEB SciFact", "test", "full", None,
     "ndcg@10", None, "ndcg@10 (FAILED the gate: min cosine 0.9983865)", None, None, M4,
     "ours", "2026-09-20", "bench/export_granite_w8_fp16.py --bits 6"),
    ("granite97m-w4", "Granite-Embedding-97M w4", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "none (won't compile)", "int4-affine + fp16", 128, 0, "MTEB SciFact", "test", "full", None,
     "ndcg@10", None, "ndcg@10 (FAILED: 16 pair flips)", None, None, M4,
     "ours", "2026-09-20", "bench/export_granite_w8_fp16.py --bits 4"),
    # EXP-039 M5 Max cross-fleet re-measure (loaded window: p50 matched same-window A/B only, no energy)
    ("granite97m-fp16-m5max", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE (h17c)", "fp16", 128, 1, "latency microbench", None, "warm median, LOADED window declared", None,
     "latency", 12.17, "ms", 12.17, "per embedding", M5MAX,
     "ours", "2026-10-26", "granite-runner --compute neuralEngine --iters 110/150; results/EXP-039-w8-palettization/raw/lat-fp16-20261026T233525Z.json"),
    ("granite97m-w8-m5max", "Granite-Embedding-97M w8", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE (h17c)", "int8-affine + fp16", 128, 14, "latency microbench", None, "warm median, LOADED window declared; 1.57x fp16 vs 4.8x on M4", None,
     "latency", 19.11, "ms", 19.11, "per embedding", M5MAX,
     "ours", "2026-10-26", "ports/export_granite_w8_fp16.py --seq-len 128 --bits 8; results/EXP-039-w8-palettization/raw/lat-w8-20261026T233525Z.json"),
    ("laya-ml-ane-s256", "Laya-multilingual (mmBERT-base)", "convaiinnovations/laya-multilingual", 149,
     "Core AI", "ANE", "fp16", 256, 2, "latency microbench", None, "231 decisions", None,
     "latency", 11.83, "ms", 11.83, "per decision (all options, one pass)", M4,
     "ours", "2026-09-22", "bench/laya_ane_bench.py"),
    ("von-ane-v0", "Von-1.0 v0 (fp32 softmax)", "wfzyx/von", 395,
     "Core AI", "ANE", "fp16", 256, 31, "latency microbench", None, "5 cases", None,
     "latency", 74.0, "ms", 74.0, "per decision (N option passes)", M4,
     "ours", "2026-09-22", "bench/export_von_ane.py --variant v0"),
    ("von-ane-v1", "Von-1.0 v1 (softmax in graph dtype)", "wfzyx/von", 395,
     "Core AI", "ANE", "fp16", 256, 3, "latency microbench", None, "5 cases", None,
     "latency", 24.0, "ms", 24.0, "per decision (N option passes)", M4,
     "ours", "2026-09-22", "bench/export_von_ane.py --variant v1"),

    # ---------------- Core AI placement (EXP-004) ----------------
    ("granite97m-coreai-cpuonly", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "cpuOnly", "fp32", 128, None, "latency microbench", None, "warm median", None,
     "latency", 8.28, "ms", 8.28, "per embedding", M4,
     "ours", "2026-09-20", "tools/granite-runner"),
    ("granite97m-coreai-gpu", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "gpu", "fp32", 128, None, "latency microbench", None, "warm median", None,
     "latency", 6.06, "ms", 6.06, "per embedding", M4,
     "ours", "2026-09-20", "tools/granite-runner"),
    ("granite97m-coreai-ane", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "neuralEngine", "fp32", 128, 0, "latency microbench", None, "warm median", None,
     "latency", 4.33, "ms", 4.33, "per embedding", M4,
     "ours", "2026-09-20", "tools/granite-runner"),

    # ---------------- ANE dtype probe (EXP-005) ----------------
    ("tiny-fp16", "tiny probe (ANE-shaped)", "n/a", None,
     "Core AI", "ANE", "fp16", None, 66, "dtype control", None, "trivial graph", None,
     "ANE regions", 66.0, "regions", None, None, M4,
     "ours", "2026-09-20", "bench/probe_ane_regions.py"),
    ("tiny-fp32", "tiny probe (ANE-shaped)", "n/a", None,
     "Core AI", "none", "fp32", None, 0, "dtype control", None, "trivial graph", None,
     "ANE regions", 0.0, "regions", None, None, M4,
     "ours", "2026-09-20", "bench/probe_ane_regions.py"),

    # ---------------- energy ----------------
    ("laya-en-ane-energy", "Laya English (ModernBERT-large)", "convaiinnovations/laya", 421,
     "Core AI", "ANE", "fp16", 512, 2, "energy microbench", None, "432 decisions", None,
     "GPU power", 15.9, "mW", None, None, M4,
     "ours", "2026-09-22", "tools/enginemon/enginemon -- <adapter>"),

    # ---------------- M5 Max energy close (EXP-022 follow-up, quiet window 2026-10-06) ----
    # Quiet: oMLX quit 07:30Z; reload noise (~07:35Z) lands only in powermetrics tail.
    ("m5-minilm-all-rate", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "GPU", "fp16", 128, None, "power A/B", None, "fixed 4 texts, 20 s window", None,
     "throughput", 598, "emb/s", 1.673, "per embedding", M5MAX,
     "ours", "2026-10-06", "bench/power_mlcore.py --seconds 20 (all lane)"),
    ("m5-minilm-cpu-only-rate", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "CPU", "fp16", 128, None, "power A/B", None, "fixed 4 texts, 20 s window", None,
     "throughput", 712, "emb/s", 1.404, "per embedding", M5MAX,
     "ours", "2026-10-06", "bench/power_mlcore.py --seconds 20 (cpuOnly lane)"),
    ("m5-minilm-all-gpu-power-mean", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "GPU", "fp16", 128, None, "power A/B", None,
     "quiet oMLX-off; ANE rail 0.0 mW — M5 never places this model on ANE (pilot-calibrated)", None,
     "GPU power", 1426.3, "mW", None, None, M5MAX,
     "ours", "2026-10-06", "powermetrics via bench/power_mlcore.py; raw results/EXP-024-engine-attribution/raw/sudo/power_ALL.txt"),
    ("m5-minilm-cpu-only-gpu-power-mean", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "CPU", "fp16", 128, None, "power A/B", None, "quiet oMLX-off", None,
     "GPU power", 163.1, "mW", None, None, M5MAX,
     "ours", "2026-10-06", "powermetrics via bench/power_mlcore.py; raw results/EXP-024-engine-attribution/raw/sudo/power_CPU_ONLY.txt"),
    ("m5-minilm-all-energy-per-embedding", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "GPU", "fp16", 128, None, "power A/B", None,
     "combined rail 2954.9 mW / 597.70 emb/s = 4.944 mJ/emb (rail split GPU 2.386 + CPU 2.561 mJ, ANE 0); throughput anomaly declared: 598 emb/s quiet vs 1038 in oMLX-active pilot — mJ from this window's own rate", None,
     "energy per embedding", 4.944, "mJ", 1.673, "per embedding", M5MAX,
     "ours", "2026-10-06", "powermetrics via bench/power_mlcore.py (mean mW / 598 emb/s)"),
    ("m5-minilm-cpu-only-energy-per-embedding", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "CPU", "fp16", 128, None, "power A/B", None, "combined rail 8114.7 mW / 711.80 emb/s = 11.400 mJ/emb (rail split CPU 11.171 + GPU 0.229 mJ)", None,
     "energy per embedding", 11.400, "mJ", 1.404, "per embedding", M5MAX,
     "ours", "2026-10-06", "powermetrics via bench/power_mlcore.py (mean mW / 712 emb/s)"),
    ("m5-minilm-energy-per-embedding-ratio", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "GPU vs CPU", "fp16", 128, None, "power A/B", None,
     "derived: 11.400 / 4.944 = 2.306, rounded 2.31 (cpu/all, combined rails)", None,
     "energy ratio", 2.31, "× (CPU/GPU)", None, None, M5MAX,
     "ours (derived)", "2026-10-06", "derived: m5-minilm-*-energy-per-embedding"),
    # ---------------- EXP-024 C7 NA matched A/B tile energy (quiet window 2026-10-06 18:06Z) ----
    ("m5-naab-tensorops-tile-energy", "matmul2d 64x32 K=64 single tile (na_tiles arm A)",
     "bench/na_tiles.py --tag tensorops", None,
     "coreai-torch TorchMetalKernel", "GPU", "fp16", None, None, "na matched A/B", None,
     "window-energy per completed tile: (1670.4-172.7) mW x 90 s = 134.8 J over 48 rounds x 5000 predicts = 240000 tiles; 16 relaunches (IOSurface leak, F-39); med 237.0 us/tile = 1.11 GFLOPS; GPU boost 951 MHz; idle drift 0.1 mW; dispatch-bound — 0.004% of HAL-32 ceiling, tile energy = launch+memory path, NOT NA-pipe throughput",
     None, "energy per million tiles", 561612.0, "mJ/Mtile", 0.237, "per predict", M5MAX,
     None, 1670.4, "powermetrics gpu_power", 172.7,
     "ours", "2026-10-06",
     "bash results/EXP-024-engine-attribution/raw/na_ab_window.sh; raw results/EXP-024-engine-attribution/raw/na-ab-20261006T180625Z/"),
    ("m5-naab-simdgroup-tile-energy", "SIMT fp16 dot-product 64x32 K=64 matched (na_tiles arm B)",
     "bench/na_tiles.py --tag simdgroup", None,
     "MSL via MPSGraph runtime", "GPU", "fp16", None, None, "na matched A/B", None,
     "window-energy per completed tile: (1791.4-172.7) mW x 90 s = 145.7 J over 45 rounds x 5000 predicts = 225000 tiles; 15 relaunches; med 262.0 us/tile = 1.00 GFLOPS; boost 976 MHz; same window/floor as arm A",
     None, "energy per million tiles", 647457.0, "mJ/Mtile", 0.262, "per predict", M5MAX,
     None, 1791.4, "powermetrics gpu_power", 172.7,
     "ours", "2026-10-06",
     "bash results/EXP-024-engine-attribution/raw/na_ab_window.sh; raw results/EXP-024-engine-attribution/raw/na-ab-20261006T180625Z/"),
    ("m5-naab-tile-energy-delta", "arm A (matmul2d) minus arm B (SIMT shader), matched tile",
     "na_tiles A/B", None,
     "derived", "GPU", "fp16", None, None, "na matched A/B", None,
     "derived from this window: 561612 - 647457 = -85845 mJ/Mtile = -13.3%; signal = inter-arm Δ 121.0 mW = 1210x the 0.1 mW idle-drift floor (arm deltas +1497.6/+1618.6 mW); honest label: dispatch-bound launch+memory cost at 64x32, NA-pipe share unproven (see C6 note — both arms may ride shader pipes)",
     None, "energy delta", -85845.0, "mJ/Mtile", None, None, M5MAX,
     None, None, None, None,
     "ours (derived)", "2026-10-06",
     "derived: m5-naab-tensorops-tile-energy - m5-naab-simdgroup-tile-energy"),
    ("m5-granite-ane-ane-rail", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 128, None, "Core AI power A/B", None,
     "S4 settle (EXP-022 thread 2): ANE rail moves ONLY on neuralEngine (0.0 on gpu/cpuOnly) — placement real; GPU rail 240.7 mW alongside = GPU-assisted partition; gate PASS 35/35", None,
     "ANE power", 261.1, "mW", 12.10, "per embedding", M5MAX,
     "ours", "2026-10-06", "powermetrics via bench/power_coreai.py --iters 800; raw results/EXP-022-m5max-baseline/raw/energy-close-2026-10-06/power_neuralEngine.txt"),
    ("m5-granite-gpu-gpu-power", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "GPU", "fp16", 128, None, "Core AI power A/B", None, "quiet oMLX-off; gate PASS", None,
     "GPU power", 739.9, "mW", 1.82, "per embedding", M5MAX,
     "ours", "2026-10-06", "powermetrics via bench/power_coreai.py; raw results/EXP-022-m5max-baseline/raw/energy-close-2026-10-06/power_gpu.txt"),
    ("m5-granite-cpu-gpu-power", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "CPU", "fp16", 128, None, "Core AI power A/B", None, "quiet oMLX-off; gate PASS; CPU rail 7192.7 mW", None,
     "GPU power", 174.9, "mW", 4.43, "per embedding", M5MAX,
     "ours", "2026-10-06", "powermetrics via bench/power_coreai.py; raw results/EXP-022-m5max-baseline/raw/energy-close-2026-10-06/power_cpuOnly.txt"),

    # ---------------- grid sweep (EXP-009) ----------------
    *[(f"grid-{g}", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
       "Core AI", "ANE", "fp16", g, 1, "MTEB SciFact", "test", "full", None,
       "ndcg@10", v, "ndcg@10", None, None, M4,
       "ours", "2026-09-20", "bench/mteb_retrieval.py")
      for g, v in ((64, 0.59060), (128, 0.65176), (256, 0.67622), (512, 0.68546), (1024, 0.68760))],

    # ---------------- WX-2 paper cross-validation (arXiv:2606.22283 tables 9.1/34.1, web-check 2026-10-08) ----
    # External-measured anchors (paper, M5-base/H17s) diffed against our M5 Max rows.
    # Conflicts are declared in scope, never resolved silently. Report:
    # results/EXP-027-nax/results/p27_paper_xval.md
    ("xval-m5-gpu-compute-roof-fp16", "arXiv:2606.22283 table 9.1 (paper-measured M5/H17s)", "web-check 2026-10-08 SearXNG/mini", None,
     "paper MPS/matmul sweep", "GPU", "fp16", None, None, "paper-xval", "roofline",
     "paper GPU compute roof 30862 GFLOP/s on M5/H17s (base M5, 10-core GPU; per-core 3086 GF/s); our anchor m5max-s2-gemm8192-fp16-mps = 60750 GFLOP/s on the 40-core-GPU M5 Max (Apple: 128 GB Studio is the 40-core SKU) = 1519 GF/s per GPU core = 49% of the paper per-core roof. SUPERSEDES the 2026-10-08 reading: the '(18-core)' label was the CPU count (fingerprint cores=18) leaked into a GPU row and manufactured a false +9.3% per-core agreement. Correct verdict: CONFLICT-DECLARED — measured GEMM vs theoretical roof on different silicon classes, never adjudicated", None,
     "compute roof", 30862.0, "GFLOP/s", None, None, "Apple M5 (H17s)", None, None, None, None,
     "arxiv:2606.22283 (external measured)", "2026-10-08",
     "results/EXP-027-nax/raw/research-2026-10-08/arxiv_2606.22283v1.pdf; report results/EXP-027-nax/results/p27_paper_xval.md"),
    ("xval-m5-gpu-bandwidth-roof", "arXiv:2606.22283 table 9.1 (paper-measured M5/H17s)", "web-check 2026-10-08 SearXNG/mini", None,
     "paper streaming sweep", "GPU", None, None, None, "paper-xval", "roofline",
     "paper GPU bandwidth roof 229.7 GB/s (streaming regime, base M5 bus) vs our m5max-s1-gpu-read 561.6 / triad 555.1 GB/s (steady-state, Max bus) — declared CONFLICT of regime/die, NOT adjudicated: different measurement definitions and dies cannot share a verdict", None,
     "bandwidth roof", 229.7, "GB/s", None, None, "Apple M5 (H17s)", None, None, None, None,
     "arxiv:2606.22283 (external measured)", "2026-10-08",
     "results/EXP-027-nax/results/p27_paper_xval.md"),
    ("xval-m5-cpu-bandwidth-roof", "arXiv:2606.22283 table 9.1 (paper-measured M5/H17s)", "web-check 2026-10-08 SearXNG/mini", None,
     "paper streaming sweep", "CPU", None, None, None, "paper-xval", "roofline",
     "paper CPU bandwidth roof 130.4 GB/s vs our m5max-s1-cpu-read 273.5 GB/s — same regime/die caveat as xval-m5-gpu-bandwidth-roof; declared CONFLICT, not adjudicated", None,
     "bandwidth roof", 130.4, "GB/s", None, None, "Apple M5 (H17s)", None, None, None, None,
     "arxiv:2606.22283 (external measured)", "2026-10-08",
     "results/EXP-027-nax/results/p27_paper_xval.md"),
    ("xval-m5-ane-matmul-roof", "arXiv:2606.22283 table 9.1 (paper-measured M5/H17s)", "web-check 2026-10-08 SearXNG/mini", None,
     "paper ANE saturation sweep", "ANE", "fp16", None, None, "paper-xval", "roofline",
     "paper ANE compute roof 10191 GFLOP/s matmul / 18771 conv with ridge 424 FLOP/byte; NO local anchor yet — our tile-level matmul2d work (EXP-024) rides the GPU tensor units, direct ANE TFLOPs battery is the declared GAP; anchor kept for the ANE matmul2d-free op path", None,
     "compute roof", 10191.0, "GFLOP/s", None, None, "Apple M5 (H17s)", None, None, None, None,
     "arxiv:2606.22283 (external measured)", "2026-10-08",
     "results/EXP-027-nax/results/p27_paper_xval.md"),
    ("xval-m5-ane-dispatch-floor", "arXiv:2606.22283 §9.3 (paper-measured M5/H17s)", "web-check 2026-10-08 SearXNG/mini", None,
     "paper ANE dispatch battery", "ANE", None, None, None, "paper-xval", "latency floor",
     "paper per-dispatch floor 0.23 ms on the ANE; numerically adjacent to our NX-C coreai matmul2d eval median 0.2398 ms — DIFFERENT stacks (ANE dispatch vs GPU tensor-op eval), conflation forbidden; kept as the floor an ANE dispatch arm must clear", None,
     "dispatch floor", 0.23, "ms", None, None, "Apple M5 (H17s)", None, None, None, None,
     "arxiv:2606.22283 (external measured)", "2026-10-08",
     "results/EXP-027-nax/results/p27_paper_xval.md"),
    ("xval-h17c-num-nes", "arXiv:2606.22283 table 34.1 (28 compiler targets)", "web-check 2026-10-08 SearXNG/mini", None,
     "compiler HAL core-count field @0x238", "ANE", None, None, None, "paper-xval", "cross-check",
     "the h17c OBSERVATION is triple-sourced (EXP-026 coreai-cache dir names + mpsgraphtool -specializeForDevice emitting mps.aneArch h17c, results/EXP-027-nax/results/p27_mpsgraphtool_write_side.txt + EXP-028 e6 AOT gate accepting h17c alone); the decoded value 32 is single-sourced — the guide table 34.1 num_nes field (suffix ladder base=4 g=8 s=16 c=32 d=64 at HAL offset 0x238), not a measured core count. Correction 2026-10-10 (Apple public spec): the M5 Max ANE is 16 cores on every SKU and this 128 GB Studio is the 40-core GPU bin — 32 matches neither the 16-core ANE nor the 40 GPU/NA units; it matches the sibling 32-core M5 Max GPU class, while the real 32-core ANE (M5 Ultra) sits at H17d (64). The 2026-10-08 'compiler-visible NE cores' reading is SUPERSEDED; num_nes semantics OPEN (on-probe target)", None,
     "HAL num_nes @0x238 (semantics OPEN)", 32.0, "cores", None, None, M5MAX, None, None, None, None,
     "arxiv:2606.22283 (external) + ours (device observation)", "2026-10-08",
     "results/EXP-027-nax/results/p27_paper_xval.md"),
]

# Every row must say what it measured and where the number comes from. Rows WE
# ran must additionally say WHEN and HOW — date and command are the substance
# of reproducibility, and no row we ran lacks them. runtime/placement/dtype
# stay in the schema's mandatory-but-nullable set (results_table.py --gaps
# prints them as gaps) because hybrid rows (e.g. a third-party retriever plus
# our ANE reranker) have no single runtime to name, and forcing one would be
# false precision — the ledger's rule is null = NOT MEASURED, printed, never
# invented. Third-party leaderboard rows have no date/command of ours either.
MANDATORY = ("id", "model", "benchmark", "metric", "value", "unit", "provenance")
MANDATORY_OURS = MANDATORY + ("date", "command")
KEYS = ("id", "model", "checkpoint", "params_m", "runtime", "placement", "dtype", "seq_len",
        "ane_regions", "benchmark", "split", "scope", "tiers", "metric", "value", "unit",
        "latency_ms", "latency_unit", "hardware", "load_factor", "energy_mw", "energy_rail",
        "energy_baseline", "provenance", "date", "command")
SCHEMA_NOTE = "bench/results_table.py — every field is mandatory; null means NOT MEASURED and prints as an em-dash"
BASE_NOTE = ("Built by bench/build_measurements.py. Rows are ranked only when "
             "benchmark+split+scope+tiers+metric+unit+latency_unit all agree.")


def expand(r: tuple) -> tuple:
    """Map a ROWS tuple onto the 26-field KEYS schema.

    The table rows carry 22 fields: everything through `hardware`, then
    provenance/date/command. The schema has four slots between hardware and
    provenance (load_factor, energy_mw, energy_rail, energy_baseline) that are
    NOT MEASURED for these rows — pad them with None. A row that already
    carries all 26 fields passes through untouched. Anything else is a
    builder bug and is rejected loudly, because a silently shifted row
    mislabels its provenance.
    """
    if len(r) == len(KEYS):
        return r
    if len(r) == 22:
        return r[:19] + (None, None, None, None) + r[19:]
    raise SystemExit(f"row {r[0]!r}: expected {len(KEYS)} or 22 fields, got {len(r)}")


def build_rows() -> list[dict]:
    recs = []
    for r in ROWS:
        d = dict(zip(KEYS, expand(r)))
        required = MANDATORY_OURS if str(d.get("provenance") or "").startswith("ours") else MANDATORY
        missing = [k for k in required if d.get(k) in (None, "") and k != "value"]
        # A measured non-result: the row exists to record that a number does NOT
        # exist (the gate failed before the task ran). That is allowed, but only
        # when the unit field says so — a bare null value is a silent gap.
        if d.get("value") in (None, "") and "FAILED" not in str(d.get("unit") or "").upper():
            missing.append("value")
        if missing:
            raise SystemExit(f"{d['id']}: missing mandatory {missing}")
        recs.append({k: d.get(k) for k in KEYS})
    return recs


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-new", action="store_true",
                    help="append ROW ids that are not yet in the existing file")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing records with the ROWS values "
                         "(default: existing records are authoritative and never touched)")
    args = ap.parse_args()

    recs = build_rows()
    by_row = {r["id"]: r for r in recs}
    if len(by_row) != len(recs):
        dupes = sorted({r["id"] for r in recs if [x["id"] for x in recs].count(r["id"]) > 1})
        raise SystemExit(f"ROWS table has duplicate ids: {dupes}")

    if not OUT.exists():
        OUT.write_text(json.dumps({"_schema": SCHEMA_NOTE, "_note": BASE_NOTE,
                                   "measurements": recs}, indent=1))
        print(f"  wrote {len(recs)} records (fresh build) -> {OUT.relative_to(ROOT)}")
        return 0

    cur = json.loads(OUT.read_text())
    existing = {m["id"]: m for m in cur["measurements"]}
    if len(existing) != len(cur["measurements"]):
        raise SystemExit(f"{OUT.name}: duplicate ids in the existing file — "
                         "refusing to merge into an inconsistent ledger")

    shared = sorted(set(by_row) & set(existing))
    new = sorted(set(by_row) - set(existing))
    drift = [(rid, k, existing[rid].get(k), by_row[rid].get(k))
             for rid in shared for k in KEYS
             if existing[rid].get(k) != by_row[rid].get(k)]

    if not (args.apply_new or args.force):
        # Default: validate the table and the ledger, report, and leave the file
        # BYTE-IDENTICAL. The committed file is the source of truth; its records
        # (including verified-extracted rows that no longer live in ROWS) are
        # never overwritten or dropped by this tool. Re-curation is reported as
        # drift and applied only with an explicit flag.
        print(f"  existing ledger  : {len(existing)} records — UNTOUCHED (byte-identical)")
        print(f"  ROWS table       : {len(recs)} rows — {len(shared)} ids shared with the ledger, "
              f"{len(new)} new")
        if drift:
            ids = sorted({d[0] for d in drift})
            print(f"  drift            : {len(drift)} fields on {len(ids)} shared ids "
                  f"(ledger values authoritative; rows shown for review, NOT applied):")
            for rid, k, a, b in drift[:20]:
                print(f"    {rid}.{k}: ledger={a!r}  rows={b!r}")
            if len(drift) > 20:
                print(f"    … and {len(drift)-20} more")
        if new:
            print(f"  new ids          : {', '.join(new)} (apply with --apply-new)")
        print("  safety           : no record in the ledger is overwritten or dropped "
              "without --force; a removed ROW does not remove a ledger record.")
        return 0

    merged = [dict(m) for m in cur["measurements"]]
    pos = {m["id"]: i for i, m in enumerate(merged)}
    added = overwritten = 0
    for r in recs:
        if r["id"] in pos:
            if args.force:
                merged[pos[r["id"]]] = r
                overwritten += 1
        else:
            merged.append(r)
            added += 1
    cur["measurements"] = merged
    OUT.write_text(json.dumps(cur, indent=1))
    print(f"  merged -> {len(merged)} records (+{added} added, {overwritten} overwritten, "
          f"existing order preserved) -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
