// probe9_opentype — EXP-035 C-86: does the client-state word (Gate-A) depend on the
// IOServiceOpen TYPE? Kernel log (raw/sudo_kernel_log_20261023T192852Z.txt) shows the
// one KNOWN-SUCCESSFUL program load on this box rides aned's type=2 connect
// ("newUserClient: ANEDriver::newUserClient type=2" → ANE_AddClientForProgram →
// ANE_ProgramPrepare OK). Every door probe to date has used type=1.
//
// Method: one compile, one live handle. Then for each open type, arm the SAME
// canonical fill (handle@0x10, cnt=1) plus the zero control, and report kr per type.
// kr is the oracle; a Gate-A that depends on open-type shows up as a non-0xe00002c2
// for some type while type 1 stays BadArgument. Poison-0xFACE scalar round-trip per
// send. Zero-residue: every connection closed in the same run; ioreg witness after.
//
// Build (from silicon-ledger/tools/ane_door_probe/):
//   BARE="/Users/<user>/Library/Application Support/openfox/workspaces/AI_dev/ncm-fidelity-fixes/ncm-run/bare"
//   clang -fobjc-arc -o probe9_opentype probe9_opentype.m "$BARE/Sources/ANEBridge/ane_bridge.m" \
//     -I "$BARE/Sources/ANEBridge/include" \
//     -framework Foundation -framework IOSurface -framework IOKit -lobjc
// run: ./probe9_opentype [types...]   (default: 0 1 2 3 4 5 8 16)
#import <Foundation/Foundation.h>
#import <IOKit/IOKitLib.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ane_bridge.h"

int probe_main(int argc, char **argv);
int main(int argc, char **argv) { @autoreleasepool { return probe_main(argc, argv); } }

typedef uint64_t (*u64fn)(id __unsafe_unretained, SEL);

static void send2(io_connect_t c, const char *tag, uint64_t handle, uint32_t cnt) {
    unsigned char in[3152];
    memset(in, 0, sizeof(in));
    memcpy(in + 0x10, &handle, 8);
    uint32_t proc = 0;
    memcpy(in + 0x18, &proc, 4);
    memcpy(in + 0x38, &cnt, 4);
    unsigned char out[64] = {0};
    size_t osz = 64;
    unsigned long long scal[1] = {0xface0000face};
    uint32_t scount = 1;
    kern_return_t kr = IOConnectCallMethod(c, 2, NULL, 0, in, sizeof(in),
                                          scal, &scount, out, &osz);
    printf("  sel2 %-8s handle=0x%llx cnt=%u kr=0x%x scalar0=0x%llx oSz=%zu%s\n",
           tag, handle, cnt, kr, scal[0], osz,
           (scal[0] == 0xface0000face) ? "" : " [SCALAR-WRITTEN]");
    if (kr == KERN_SUCCESS) {
        printf("    out_hex=\"");
        for (size_t j = 0; j < osz && j < 64; j++) printf("%02x", out[j]);
        printf("\"\n");
    }
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

    int types[16], nt = 0;
    if (argc > 1) { for (int i = 1; i < argc && nt < 16; i++) types[nt++] = atoi(argv[i]); }
    else { int d[] = {0,1,2,3,4,5,8,16}; memcpy(types, d, sizeof(d)); nt = 8; }

    for (int t = 0; t < nt; t++) {
        io_connect_t c = MACH_PORT_NULL;
        kern_return_t okr = IOServiceOpen(svc, mach_task_self(), types[t], &c);
        printf("TYPE %d open kr=0x%x%s\n", types[t], okr, okr ? " (skipped)" : "");
        fflush(stdout);
        if (okr) continue;
        kern_return_t k0 = IOConnectCallMethod(c, 0, NULL, 0, NULL, 0, NULL, NULL, NULL, NULL);
        kern_return_t k1 = IOConnectCallMethod(c, 1, NULL, 0, NULL, 0, NULL, NULL, NULL, NULL);
        printf("  sel0 kr=0x%x  sel1(pre-arm) kr=0x%x\n", k0, k1);
        send2(c, "zero",   0,      0);
        send2(c, "live",   handle, 1);
        send2(c, "bogus",  handle ^ 0x5555, 1);
        IOServiceClose(c);
        printf("  closed\n");
        fflush(stdout);
    }
    IOObjectRelease(svc);
    fflush(stdout);
    _exit(0);
}
