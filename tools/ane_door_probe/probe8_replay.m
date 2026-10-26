// probe8_replay — EXP-035 C-85: sel-2 submit through the type-1 direct-path door with
// the offset map FROM C-83 (results/EXP-035-chaining-blob/OFFSET_MAP.md) and a LIVE
// handle minted by our own compile+load in-process (probe7_capture pattern).
//
// Shape note: the original "replay captured bytes" plan died on the C-84 capture
// (framework never puts chaining on our door — CAPTURE.md); the gap collapsed to
// one fill value, so this forge-from-offset-map IS the replay, with the same gate
// discipline: one offset at a time, kr + structOut as oracle (poison-0xFACE rule:
// a field's offset is trusted only when changing it changes the outcome).
//
// Arms (per run, fresh handle):
//   N   handle=0            -> control: expect 0xe00002c2 (reproduces C-80)
//   B   handle=live^0x5555  -> bogus same-magnitude: expect 0xe00002c2
//   P0  handle=live, cnt=0  -> handle-gate pass?
//   P1  handle=live, cnt=1  -> canonical fill
//   P2  P1 + procIndex=1    -> out-of-range arm (same kr expected; info only)
//   F   full-substitution   -> txn=0xFACE0001@0x20, 0x28=0xFF
// Every arm: scalarsOut poison 0xface0000face round-trip check + structOut hex (64 B).
//
// Meter: run under enginemon to witness SOC-NI9 per-eval counters — a
// bookkeeping-only prepare must show ZERO engine-band movement (parity-kernel band
// 0.488-0.503 / field 1.00-1.06, EXP-030/032 calibration). Engine-work claims only
// with meter witnesses.
//
// Build (from silicon-ledger/tools/ane_door_probe/):
//   BARE="/Users/<user>/Library/Application Support/openfox/workspaces/AI_dev/ncm-fidelity-fixes/ncm-run/bare"
//   clang -fobjc-arc -o probe8_replay probe8_replay.m "$BARE/Sources/ANEBridge/ane_bridge.m" \
//     -I "$BARE/Sources/ANEBridge/include" \
//     -framework Foundation -framework IOSurface -framework IOKit -lobjc
#import <Foundation/Foundation.h>
#import <IOKit/IOKitLib.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <stdio.h>
#include <string.h>
#include "ane_bridge.h"

int probe_main(int argc, char **argv);
int main(int argc, char **argv) { @autoreleasepool { return probe_main(argc, argv); } }

typedef uint64_t (*u64fn)(id __unsafe_unretained, SEL);

static io_connect_t g_conn;

static void arm(const char *name, uint64_t handle, uint32_t proc, uint64_t txn,
                uint32_t off28, uint32_t cnt);

static void arm_cnt(const char *name, uint64_t handle, uint32_t proc, uint64_t txn,
                    uint32_t off28, uint32_t cnt) {
    char nm[64]; snprintf(nm, sizeof(nm), "%s%u", name, cnt);
    arm(nm, handle, proc, txn, off28, cnt);
}

static void arm(const char *name, uint64_t handle, uint32_t proc, uint64_t txn,
                uint32_t off28, uint32_t cnt) {
    unsigned char in[3152];
    memset(in, 0, sizeof(in));
    memcpy(in + 0x10, &handle, 8);
    memcpy(in + 0x18, &proc, 4);
    memcpy(in + 0x20, &txn, 8);
    memcpy(in + 0x28, &off28, 4);
    memcpy(in + 0x38, &cnt, 4);
    unsigned char out[64] = {0};
    size_t osz = 64;
    unsigned long long scal[1] = {0xface0000face};
    uint32_t scount = 1;
    kern_return_t kr = IOConnectCallMethod(g_conn, 2, NULL, 0, in, sizeof(in),
                                          scal, &scount, out, &osz);
    printf("{\"arm\":\"%s\",\"handle\":\"0x%llx\",\"proc\":%u,\"txn\":\"0x%llx\","
           "\"off28\":%u,\"cnt\":%u,\"kr\":\"0x%x\",\"oSz_back\":%zu,\"scalar0\":\"0x%llx\"",
           name, handle, proc, txn, off28, cnt, kr, osz, scal[0]);
    if (kr == KERN_SUCCESS || osz) {
        printf(",\"out_hex\":\"");
        for (size_t j = 0; j < osz && j < 64; j++) printf("%02x", out[j]);
        printf("\"");
    }
    printf("}\n");
    fflush(stdout);
}

int probe_main(int argc, char **argv) {
    int Cin = 128, H = 64, K = 128, S = 32;
    NSString *mil = [NSString stringWithContentsOfFile:@"baseline.mil"
                                              encoding:NSUTF8StringEncoding error:nil];
    if (!mil) { fprintf(stderr, "no baseline.mil\n"); return 2; }
    size_t n1 = (size_t)H * Cin, n2 = (size_t)K * H;
    int8_t *w1 = malloc(n1), *w2 = malloc(n2);
    float *s1 = malloc((size_t)H * 4), *s2 = malloc((size_t)K * 4);
    for (size_t i = 0; i < n1; i++) w1[i] = (int8_t)((i * 37) % 200 - 100);
    for (size_t i = 0; i < n2; i++) w2[i] = (int8_t)((i * 53) % 200 - 100);
    for (int i = 0; i < H; i++) s1[i] = 0.001f;
    for (int i = 0; i < K; i++) s2[i] = 0.001f;
    if (ane_bridge_init() != 0) { fprintf(stderr, "init failed\n"); return 3; }
    int blen = 0;
    size_t blen_sz = 0;
    uint8_t *blob = ane_bridge_build_int8_weight_blob2(w1, s1, H, Cin, w2, s2, K, H, &blen_sz);
    blen = (int)blen_sz;
    if (!blob) { fprintf(stderr, "blob failed\n"); return 3; }
    size_t inS = (size_t)Cin * S * 2, outS = (size_t)K * S * 2;
    void *k = ane_bridge_compile(mil.UTF8String, strlen(mil.UTF8String), blob, blen,
                                1, &inS, 1, &outS);
    if (!k) { fprintf(stderr, "compile failed\n"); return 4; }
    id __unsafe_unretained model = *(__unsafe_unretained id *)k;
    uint64_t handle = ((u64fn)objc_msgSend)(model, sel_registerName("programHandle"));
    uint64_t state = ((u64fn)objc_msgSend)(model, sel_registerName("state"));
    fprintf(stderr, "live handle=%llu state=%llu\n", handle, state);

    io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("ANEDriver"));
    if (!svc) { fprintf(stderr, "no ANEDriver\n"); return 5; }
    kern_return_t okr = IOServiceOpen(svc, mach_task_self(), 1, &g_conn);
    fprintf(stderr, "open type1 kr=0x%x\n", okr);
    if (okr != KERN_SUCCESS) return 5;
    kern_return_t k1 = IOConnectCallMethod(g_conn, 1, NULL, 0, NULL, 0, NULL, NULL, NULL, NULL);
    fprintf(stderr, "sel1 pre-arm kr=0x%x\n", k1);

    arm("N-zero",   0,              0, 0, 0, 0);
    arm("B-bogus",  handle ^ 0x5555, 0, 0, 0, 1);
    for (uint32_t c = 0; c <= 4; c++) arm_cnt("C-cnt", handle, 0, 0, 0, c);
    arm("P2-proc1", handle,         1, 0, 0, 1);
    arm("F-full",   handle,         0, 0xFACE0001ULL, 0xFF, 1);

    IOServiceClose(g_conn);
    IOObjectRelease(svc);
    fflush(stdout);
    _exit(0);
}
