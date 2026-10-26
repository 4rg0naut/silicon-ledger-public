// probe7_capture — EXP-035 C-84: capture the LIVE ANEClientProgramHandle from our own
// in-process anectx-style compile+eval, so C-85 (probe8_replay) can arm args+0x10 on the
// raw door with a handle the kernel-global ANEDriver table actually knows.
//
// Ground so far (EXP-035 C-84a/b captures, results/EXP-035-chaining-blob/raw/):
// - the proven _ANEInMemory compile+eval path issues NO door chaining/program selector
//   in-process (door sees OPEN+sel0 only; eval rides aned XPC + _ANESharedEvents mach ports),
//   so the handle must come from the framework object graph, not from door traffic;
// - 26A434 runtime ivar dump (EXP-025 ane_class_dump pattern) confirms on this OS the
//   handle accessors ane-infer (MIT, docs/ane-internals.md, authored on macOS 26.3) names:
//   -[  _ANEInMemoryModel programHandle] / intermediateBufferHandle / string_id / state.
//
// Baseline MIL geometry = mil_battery baseline = proven ANECtx.swift ctxMil grammar.
//
// Build (from silicon-ledger/tools/ane_door_probe/):
//   BARE="/Users/<user>/Library/Application Support/openfox/workspaces/AI_dev/ncm-fidelity-fixes/ncm-run/bare"
//   clang -fobjc-arc -o probe7_capture probe7_capture.m "$BARE/Sources/ANEBridge/ane_bridge.m" \
//     -I "$BARE/Sources/ANEBridge/include" \
//     -framework Foundation -framework IOSurface -framework IOKit -lobjc
// ARC is mandatory (matches ane_bridge.m); MRC build frees the autoreleased model
// mid-flight (measured: objc_msgSend on isa-garbage, 2026-10-23).
// Run:
//   ./probe7_capture
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <stdio.h>
#include <string.h>
#include "ane_bridge.h"

int probe_main(int argc, char **argv);

// Baseline MIL = EXP-032 proven grammar dump, byte-exact (baseline.mil next to this file;
// sha256 recorded in the capture artifact). Weights = same synthetic arrays as mil_battery.

int main(int argc, char **argv) {
    @autoreleasepool {
    return probe_main(argc, argv);
    }
}

int probe_main(int argc, char **argv) {
    int Cin = 128, H = 64, K = 128, S = 32;
    const char *milPath = argc > 1 ? argv[1] : "baseline.mil";
    NSString *m = [NSString stringWithContentsOfFile:[NSString stringWithUTF8String:milPath]
                                            encoding:NSUTF8StringEncoding error:nil];
    if (!m) { fprintf(stderr, "cannot read MIL %s\n", milPath); return 2; }
    size_t n1 = (size_t)H * Cin, n2 = (size_t)K * H;
    int8_t *w1 = malloc(n1), *w2 = malloc(n2);
    float *s1 = malloc((size_t)H * 4), *s2 = malloc((size_t)K * 4);
    for (size_t i = 0; i < n1; i++) w1[i] = (int8_t)((i * 37) % 200 - 100);
    for (size_t i = 0; i < n2; i++) w2[i] = (int8_t)((i * 53) % 200 - 100);
    for (int i = 0; i < H; i++) s1[i] = 0.001f;
    for (int i = 0; i < K; i++) s2[i] = 0.001f;
    if (ane_bridge_init() != 0) { fprintf(stderr, "init failed\n"); return 3; }
    int blen = 0;
    uint8_t *blob = ane_bridge_build_int8_weight_blob2(w1, s1, H, Cin, w2, s2, K, H, &blen);
    if (!blob) { fprintf(stderr, "blob failed\n"); return 3; }

    size_t inS = (size_t)Cin * S * 2, outS = (size_t)K * S * 2;
    void *k = ane_bridge_compile(m.UTF8String, strlen(m.UTF8String), blob, blen, 1, &inS, 1, &outS);
    if (!k) { fprintf(stderr, "compile failed\n"); return 4; }
    fprintf(stderr, "compile OK\n");
    typedef id __unsafe_unretained (*obj1fn)(id __unsafe_unretained, SEL);
    typedef uint64_t (*u64fn)(id __unsafe_unretained, SEL);
    // raw struct field is not ARC-managed; assigning to a strong local retains it —
    // that IS the pin (ARC matches ane_bridge.m, the proven context).
    id model = *(__unsafe_unretained id *)k; // ANEKernelHandle.model (first field)
    uint64_t stateBefore = ((u64fn)objc_msgSend)(model, sel_registerName("state"));
    NSString *tmpDir = *(NSString *__unsafe_unretained *)((__unsafe_unretained id *)k + 4); // ANEKernelHandle.tmpDir
    id __unsafe_unretained hexObj = ((obj1fn)objc_msgSend)(model, sel_registerName("hexStringIdentifier"));
    const char *hexId = [(NSString *)hexObj UTF8String] ?: "nil";

    bool evalOK = ane_bridge_eval(k); // triggers load+eval — kernel-program registration
    fprintf(stderr, "eval ok=%d\n", evalOK);

    uint64_t ph = ((u64fn)objc_msgSend)(model, sel_registerName("programHandle"));
    uint64_t ibh = ((u64fn)objc_msgSend)(model, sel_registerName("intermediateBufferHandle"));
    uint64_t sid = ((u64fn)objc_msgSend)(model, sel_registerName("string_id"));
    uint64_t state = ((u64fn)objc_msgSend)(model, sel_registerName("state"));
    id aneModel = ((obj1fn)objc_msgSend)(model, sel_registerName("model"));
    uint64_t ph2 = 0, sid2 = 0;
    if (aneModel) {
        SEL sPH = sel_registerName("programHandle");
        if ([aneModel respondsToSelector:sPH]) ph2 = ((u64fn)objc_msgSend)(aneModel, sPH);
        SEL sID = sel_registerName("string_id");
        if ([aneModel respondsToSelector:sID]) sid2 = ((u64fn)objc_msgSend)(aneModel, sID);
    }
    const char *tdUtf = tmpDir ? tmpDir.UTF8String : "nil";
    printf("{\"eval_ok\":%s,\"state_pre_eval\":%llu,\"state\":%llu,"
           "\"programHandle\":%llu,\"intermediateBufferHandle\":%llu,\"string_id\":%llu,"
           "\"_ANEModel.programHandle\":%llu,\"_ANEModel.string_id\":%llu,"
           "\"hexStringIdentifier\":\"%s\",\"tmpDir\":\"%s\"}\n",
           evalOK ? "true" : "false", stateBefore, state, ph, ibh, sid, ph2, sid2, hexId, tdUtf);
    fflush(stdout);
    _exit(0); // same teardown rule as mil_battery: exit before private-API teardown crash
}
