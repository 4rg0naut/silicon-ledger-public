// probe10_loadsweep — EXP-036 C-87 verification: does ANY direct-path selector
// change behavior for our type-1 connection AFTER an in-process program load?
// (the named C-87 candidate from results/EXP-035-chaining-blob/CAPTURE.md:
// "per-selector semantics sweep with poison discipline on the remaining indices,
// watching for any kr difference once the program is loaded in-process").
//
// Discipline: same sweep twice, identical buffers — pass 1 BEFORE compile+load,
// pass 2 AFTER, in-process, same connection (Gate-A word is per-client-instance).
// pass 3 (post-load): struct selectors re-sent with the LIVE handle at +0x10 and
// cnt=1 where the contract size allows (probe8 canonical fill). Then probe8's
// sel-2 arm ladder (N-zero / B-bogus / P1-live) as the Gate-A signature control.
// Poison 0xFACE on every scalar input, round-trip checked (EXP-031 C-64 rule).
//
// Build (from silicon-ledger/tools/ane_door_probe/):
//   BARE="/data/OpenFox/AI_dev/ncm-run/bare"
//   clang -fobjc-arc -O2 -o probe10_loadsweep probe10_loadsweep.m "$BARE/Sources/ANEBridge/ane_bridge.m" \
//     -I "$BARE/Sources/ANEBridge/include" \
//     -framework Foundation -framework IOSurface -framework IOKit -lobjc
//   codesign -s - -f ./probe10_loadsweep
#import <Foundation/Foundation.h>
#import <IOKit/IOKitLib.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <mach/mach_time.h>
#include <stdio.h>
#include <string.h>
#include "ane_bridge.h"

typedef uint64_t (*u64fn)(id __unsafe_unretained, SEL);
typedef struct { uint32_t sel; uint32_t scalarIn; uint32_t structIn; uint32_t scalarOut; uint32_t structOut; } contract_t;

static contract_t K[] = {
    {0,0,136,0,136},{1,0,0,0,0},{2,0,3152,1,64},{3,0,40,0,0},{4,0,3104,0,0},
    {5,1,2088,0,0},{6,0,2088,0,0},{7,0,16,0,24},{8,0,32,0,0},{9,1,520,0,0},{10,0,0,1,0},
};
static const size_t NK = sizeof(K)/sizeof(K[0]);
static io_connect_t g_conn;
static uint64_t g_handle;

static double us_since(uint64_t t0) {
    static mach_timebase_info_data_t tb = {0,0};
    if (!tb.denom) mach_timebase_info(&tb);
    return (double)(mach_absolute_time() - t0) * tb.numer / tb.denom / 1000.0;
}

static void sweep(const char *phase, int fill_handle) {
    for (size_t i = 0; i < NK; i++) {
        contract_t *c = &K[i];
        unsigned char inbuf[4096]; memset(inbuf, 0, sizeof inbuf);
        unsigned char outbuf[4096]; memset(outbuf, 0, sizeof outbuf);
        if (fill_handle && c->structIn >= 0x18) {
            memcpy(inbuf + 0x10, &g_handle, 8);
            uint32_t one = 1;
            if (c->structIn >= 0x3c) memcpy(inbuf + 0x38, &one, 4);
        }
        uint64_t scalars[2] = {0xface0000faceULL, 0};
        uint32_t outCnt = c->scalarOut ? 1 : 0;
        size_t oSz = c->structOut;
        uint64_t t0 = mach_absolute_time();
        kern_return_t kr = IOConnectCallMethod(g_conn, c->sel,
            scalars, c->scalarIn,
            c->structIn ? inbuf : NULL, c->structIn,
            scalars, &outCnt,
            c->structOut ? outbuf : NULL, c->structOut ? &oSz : NULL);
        printf("{\"phase\":\"%s\",\"sel\":%u,\"fill\":\"%s\",\"kr\":\"0x%x\",\"oSz_back\":%zu,"
               "\"poison_rt\":\"%s\",\"lat_us\":%.1f",
               phase, c->sel, fill_handle ? "handle" : "zero", kr, oSz,
               scalars[0] == 0xface0000faceULL ? "ok" : "MUTATED", us_since(t0));
        if (kr == KERN_SUCCESS && c->structOut) {
            printf(",\"out_prefix\":\"");
            size_t n = oSz > 136 ? 136 : oSz;
            for (size_t j = 0; j < n; j++) printf("%02x", outbuf[j]);
            printf("\"");
        }
        printf("}\n");
    }
    fflush(stdout);
}

int main(int argc, char **argv) { @autoreleasepool {
    io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("ANEDriver"));
    if (!svc) { fprintf(stderr, "no ANEDriver\n"); return 5; }
    kern_return_t okr = IOServiceOpen(svc, mach_task_self(), 1, &g_conn);
    fprintf(stderr, "open type1 kr=0x%x\n", okr);
    if (okr != KERN_SUCCESS) return 5;

    // CONTROL (added after run 1 observation: post-load-handle sel0 output carried
    // the handle at +0x18): fill the SAME offsets with a BOGUS same-magnitude
    // handle BEFORE any load, to attribute the output delta to fill vs load.
    g_handle = 0x2000f; // bogus, same magnitude as minted handles; never loaded
    sweep("pre-load-handle-bogus", 1);
    g_handle = 0;

    sweep("pre-load", 0);

    NSString *mil = [NSString stringWithContentsOfFile:@"baseline.mil"
                                              encoding:NSUTF8StringEncoding error:nil];
    if (!mil) { fprintf(stderr, "no baseline.mil\n"); return 2; }
    int Cin = 128, H = 64, K2 = 128, S = 32;
    size_t n1 = (size_t)H * Cin, n2 = (size_t)K2 * H;
    int8_t *w1 = malloc(n1), *w2 = malloc(n2);
    float *s1 = malloc((size_t)H * 4), *s2 = malloc((size_t)K2 * 4);
    for (size_t i = 0; i < n1; i++) w1[i] = (int8_t)((i * 37) % 200 - 100);
    for (size_t i = 0; i < n2; i++) w2[i] = (int8_t)((i * 53) % 200 - 100);
    for (int i = 0; i < H; i++) s1[i] = 0.001f;
    for (int i = 0; i < K2; i++) s2[i] = 0.001f;
    if (ane_bridge_init() != 0) { fprintf(stderr, "init failed\n"); return 3; }
    size_t blen = 0;
    uint8_t *blob = ane_bridge_build_int8_weight_blob2(w1, s1, H, Cin, w2, s2, K2, H, &blen);
    if (!blob) { fprintf(stderr, "blob failed\n"); return 3; }
    size_t inS = (size_t)Cin * S * 2, outS = (size_t)K2 * S * 2;
    void *k = ane_bridge_compile(mil.UTF8String, strlen(mil.UTF8String), blob, (int)blen,
                                1, &inS, 1, &outS);
    if (!k) { fprintf(stderr, "compile failed\n"); return 4; }
    id __unsafe_unretained model = *(__unsafe_unretained id *)k;
    uint64_t handle = ((u64fn)objc_msgSend)(model, sel_registerName("programHandle"));
    uint64_t state = ((u64fn)objc_msgSend)(model, sel_registerName("state"));
    g_handle = handle;
    printf("{\"phase\":\"load\",\"handle\":%llu,\"state\":%llu}\n", handle, state);
    fflush(stdout);

    sweep("post-load", 0);
    sweep("post-load-handle", 1);

    // Gate-A signature control (probe8 canonical arms on sel-2)
    const size_t ISZ = 3152;
    struct { const char *nm; uint64_t h; uint32_t cnt; } arms[] = {
        {"N-zero", 0, 0}, {"B-bogus", handle ^ 0x5555, 1}, {"P1-live", handle, 1},
    };
    for (size_t a = 0; a < 3; a++) {
        unsigned char in[ISZ]; memset(in, 0, sizeof in);
        memcpy(in + 0x10, &arms[a].h, 8);
        memcpy(in + 0x38, &arms[a].cnt, 4);
        unsigned char out[64] = {0}; size_t osz = 64;
        unsigned long long scal[1] = {0xface0000face}; uint32_t scount = 1;
        uint64_t t0 = mach_absolute_time();
        kern_return_t kr = IOConnectCallMethod(g_conn, 2, NULL, 0, in, ISZ, scal, &scount, out, &osz);
        printf("{\"phase\":\"arm-%s\",\"handle\":\"0x%llx\",\"kr\":\"0x%x\",\"poison_rt\":\"%s\",\"lat_us\":%.1f}\n",
               arms[a].nm, arms[a].h, kr, scal[0] == 0xface0000face ? "ok" : "MUTATED", us_since(t0));
    }

    IOServiceClose(g_conn);
    IOObjectRelease(svc);
    printf("{\"phase\":\"close\"}\n");
    fflush(stdout);
    _exit(0);
}}
