// na_tiles.metal — C6 valid-tile matched A/B (R8 workaround), M5 Max h17c.
//
// Arm A replays Mference's validated shape (mpp_prefill_affine_threadgroup_f16,
// 64x32 tile, K=64, execution_simdgroups<4>) — the size our R8 probe found
// all-elements-correct while multi-tile dispatch silently no-ops on macOS 27.0-beta
// GPUCompiler 32023 (stage4_load.log). Arm B is a memory-traffic-matched
// simdgroup_matrix fp16 kernel, same thread count, same tile, same byte footprint
// except the quant path: both arms load A(64x64)+B(64x32) fp16 from device memory.
//
// Zakharko (TZAKHARKO-NA, SOURCES) measures matrix fp16 at ~1024 FLOPS/core/cycle
// and states tiles >=32x32 hit the NA path — 64x32 is on the right side of that line.
//
// build: xcrun -sdk macosx metal -std=metal4.0 -c na_tiles.metal -o na_tiles.air && \
//        xcrun -sdk macosx metallib na_tiles.air -o na_tiles.metallib

#include <metal_stdlib>
#include <metal_tensor>
using namespace metal;

constant constexpr int TM = 64;   // M
constant constexpr int TN = 32;   // N
constant constexpr int TK = 64;   // K

// ── arm A: matmul2d single tile, ITERS accumulations ─────────────────────────────
kernel void na_tile2d(
    device half* A [[buffer(0)]],   // [M,K] row-major
    device half* B [[buffer(1)]],   // [K,N] row-major
    device float*      C     [[buffer(2)]],
    constant uint&     iters [[buffer(3)]],
    uint3 lid3               [[thread_position_in_threadgroup]],
    uint3 threads3           [[threads_per_threadgroup]]) {

    constexpr auto descriptor = matmul2d_descriptor(TM, TN, TK, false, true, false);
    matmul2d<descriptor, execution_simdgroups<4>> operation;

    using device_half_tensor  = tensor<device half, dextents<int32_t, 2>, tensor_inline>;
    using threadgroup_half_tensor = tensor<threadgroup half, dextents<int32_t, 2>, tensor_inline>;

    // innermost-first per Tungsten fix: extents (K, M)/(K, N), strides (1, K)
    threadgroup half aTile[TM * TK];
    threadgroup half bTile[TK * TN];

    device_half_tensor srcA(A, dextents<int32_t, 2>(TK, TM),
                            array<int32_t, 2>({1, int32_t(TK)}));
    threadgroup_half_tensor dstA(aTile, dextents<int32_t, 2>(TK, TM),
                                 array<int32_t, 2>({1, int32_t(TK)}));
    device_half_tensor srcB(B, dextents<int32_t, 2>(TN, TK),
                            array<int32_t, 2>({1, int32_t(TN)}));
    threadgroup_half_tensor dstB(bTile, dextents<int32_t, 2>(TN, TK),
                                 array<int32_t, 2>({1, int32_t(TN)}));
    srcA.load(aTile);   // one shared load per dispatch: matched traffic, hot compute after
    srcB.load(bTile);
    threadgroup_barrier(mem_flags::mem_threadgroup);

    auto acc = operation.get_destination_cooperative_tensor<
        threadgroup_half_tensor, threadgroup_half_tensor, float>();
    for (int i = 0; i < acc.get_capacity(); ++i) acc[i] = 0.0f;

    for (uint it = 0; it < iters; ++it) {
        operation.run(dstA, dstB, acc);   // accumulate=true in descriptor
    }

    for (int i = 0; i < acc.get_capacity(); ++i) {
        if (!acc.is_valid_element(i)) continue;
        const auto pos = acc.get_multidimensional_index(i);
        C[int(i32(pos[0])) * TN + int(i32(pos[1]))] = acc[i];
    }
}

// ── arm B: simdgroup_matrix fp16, same 64x32x64, 128 threads, matched loads ──────
kernel void na_tile4(
    device half* A [[buffer(0)]],
    device half* B [[buffer(1)]],
    device float*      C     [[buffer(2)]],
    constant uint&     iters [[buffer(3)]],
    uint3 lid3               [[thread_position_in_threadgroup]]) {

    simdgroup::float8 acc[32];   // 8x4 accumulator blocks of 8x8 = 64x32, 4 simdgroups
    uint simd  = lid3.x / 32;
    uint lane  = lid3.x % 32;
    // each simdgroup owns an 8x32 slab (4 blocks of 8x8)
    simdgroup::float8 sum[4];
    for (int b = 0; b < 4; b++) sum[b] = simdgroup::float8::zero();

    for (uint it = 0; it < iters; ++it) {
        for (int k = 0; k < TK; k += 8) {
            for (int b = 0; b < 4; b++) {
                simdgroup::half8 a, w;
                // A block rows simd*8..+8, cols k..k+8  (8x8 load per lane-quad pattern)
                a.load(device A + (simd * 8) * TK + k, TK);
                // B block rows k..k+8, cols b*8..+8
                w.load(device B + (b * 8) * 1 + k * TN, TN, true); // transpose=true col trick
                simdgroup::matrix_multiply(a, w, sum[b], sum[b]);
            }
        }
    }
    (void)acc; (void)lane;
    for (int b = 0; b < 4; b++)
        sum[b].store(device C + (simd * 8) * TN + b * 8, TN);
}
