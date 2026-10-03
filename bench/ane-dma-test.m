// ane-dma-test.m — does the 1 MiB kernel-DMA erratum exist on an M4?
//
// THE QUESTION. Eileen Yoon measured on an M3 that when one ANE core is asked to stream an exact
// multiple of 1 MiB, a 14-bit prefetch-ring counter wraps to zero at the finish line, the prefetcher
// concludes there is nothing left to fetch ahead for, and throughput collapses from ~45-60 GB/s to
// 17-19 GB/s. Her fix: do not request exactly 1 MiB — split the transfer in two.
//
// The erratum was measured on M3. M1 and M5 Max are reported unaffected. **M4 is unknown.** That is
// what this measures.
//
// WHY IT IS NOW POSSIBLE. We have the hardware question and the measurement rig, but we lacked a way
// to author a program with a CHOSEN transfer size. The transfer size is set by the layer shape:
//
//     bytes/core = (Cout / 16) * Cin * 2
//
// so a 1x1 convolution with Cin=2048, Cout=4096 gives (4096/16)*2048*2 = 8,388,608 bytes over 16
// cores = exactly 1 MiB per core. Choosing the shape chooses the transfer.
//
// THE ARMS (the control is what makes the result mean anything):
//
//   notch_1mib     Cin 2048 -> Cout 4096   exactly 1 MiB/core        expect throttled
//   control_16k    Cin 2048 -> Cout 4032   1 MiB - 16 KiB/core       expect full bandwidth
//   split_2x       two convs 2048 -> 2048  two 0.5 MiB tasks          expect full bandwidth (the fix)
//   notch_2mib     Cin 4096 -> Cout 4096   exactly 2 MiB/core         expect throttled, worse
//
// If `split_2x` is faster than `notch_1mib` while `control_16k` shows no such gain over a matched
// non-split pair, the fix is doing the work. If everything is flat, the M4 does not have the erratum.
//
// CREDITS. Skeleton from maderix/ANE `inmem_basic.m` (MIT) — the minimal Path A example. MIL
// generator conventions and the BLOBFILE header format from mechramc/Orion `core/mil_builder.m`
// (MIT): weight shape [OUT,IN,1,1], pad_type "valid", BLOBFILE offset uint64(64), 128-byte header
// with magic 0xEFBEADDE at 64. Constraints respected from Orion's docs/ane_constraints.md:
// #4 minimum surface ~49 KB, #8 blob offset 64, #9 milText is NSData, #15 two weight tensors is
// well inside the 16-blob budget.
//
// build: clang -O2 -o ane-dma-test ane-dma-test.m -framework Foundation -framework IOSurface
// run:   ./ane-dma-test

#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>
#import <IOSurface/IOSurface.h>
#import <mach/mach_time.h>
#import <time.h>
#import <sys/sysctl.h>

static mach_timebase_info_data_t g_tb;
static char g_chip[64] = "unknown";
static char g_subtype[32] = "unknown";
static int  g_cores = 0;
static char g_hwmodel[64] = "unknown";
static char g_osbuild[64] = "unknown";
static char g_osver[32] = "unknown";

static void sysctl_into(const char *name, char *buf, size_t len) {
    if (sysctlbyname(name, buf, &len, NULL, 0) != 0) snprintf(buf, len, "unknown");
}

static int cmp_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

#define QOS 21          // the QoS value maderix's working example uses; nobody knows why 21

static double ms_since(uint64_t t0) {
    return (double)(mach_absolute_time() - t0) * g_tb.numer / g_tb.denom / 1e6;
}

// Emit one JSON record per arm, INCLUDING failures. A bench that only records successes cannot be
// compared across machines: "compiled: false" and "no record" mean different things, and a reader
// has no way to tell them apart.
// One record per arm in the m5max-bench/1 shape: machine / config / stats / derived / status.
// Adopted rather than invented -- the other machine's schema is more complete than ours was, and
// two benches only compare if they agree on the record, not merely on the numbers.
//
// Fields we were missing and now carry:
//   * chip identity read from the FRAMEWORK (_ANEDeviceInfo), not hardcoded -- so an H17 arm
//     labels itself without anyone editing a string
//   * per-iteration median / p95 / min / max, not just a mean. Our DMA result used medians ACROSS
//     runs; within-run distribution is strictly more information.
//   * status as a first-class field, so "compile_failed" and "no record" are distinguishable
static void bench_json(const char *label, int nconv, int in_dim, int per, int seq,
                       double per_core, double median_ms, double gbs, double compile_ms,
                       double observed, int compiled, int n_ok, int iters,
                       const double *samples) {
    const char *path = getenv("BENCH_JSON");
    if (!path) return;
    FILE *f = fopen(path, "a");
    if (!f) return;
    double mn = 0, p95 = 0, mx = 0;
    if (n_ok > 0 && samples) {
        double *s = malloc(sizeof(double) * n_ok);
        memcpy(s, samples, sizeof(double) * n_ok);
        qsort(s, n_ok, sizeof(double), cmp_double);
        mn = s[0]; mx = s[n_ok - 1]; p95 = s[(int)(0.95 * (n_ok - 1))];
        free(s);
    }
    int correct = compiled && observed > in_dim * 0.99 && observed < in_dim * 1.01;
    fprintf(f,
        "{\"schema\":\"m5max-bench/1\",\"record\":\"arm\","
        "\"machine\":{\"chip\":\"%s\",\"subtype\":\"%s\",\"cores\":%d,\"hw_model\":\"%s\",\"os\":\"%s\",\"os_build\":\"%s\",\"arch\":\"arm64\"},"
        "\"config\":{\"label\":\"%s\",\"convs\":%d,\"cin\":%d,\"cout_per\":%d,\"seq\":%d,"
        "\"shared_blob\":%d,\"bytes_per_core\":%.0f,\"mib_per_core\":%.4f},"
        "\"stats\":{\"median_ms\":%.4f,\"p95_ms\":%.4f,\"min_ms\":%.4f,\"max_ms\":%.4f,"
        "\"iters_ok\":%d,\"iters\":%d,\"gbs\":%.3f,\"compile_ms\":%.1f},"
        "\"derived\":{\"observed\":%.2f,\"expected\":%d,\"correct\":%s},"
        "\"status\":\"%s\"}\n",
        g_chip, g_subtype, g_cores, g_hwmodel, g_osver, g_osbuild, label, nconv, in_dim, per, seq,
        getenv("SHARED_BLOB") ? 1 : 0, per_core, per_core / 1048576.0,
        median_ms, p95, mn, mx, n_ok, iters, gbs, compile_ms,
        observed, in_dim, correct ? "true" : "false",
        compiled ? "ok" : "compile_failed");
    fclose(f);
}

// ── MIL generation (conventions from Orion's mil_builder, MIT) ───────────────────────────────

static NSString *mil_header(void) {
    return @"program(1.3)\n"
            "[buildInfo = dict<string, string>({{"
            "\"coremlc-component-MIL\", \"3510.2.1\"}, "
            "{\"coremlc-version\", \"3505.4.1\"}, "
            "{\"coremltools-component-milinternal\", \"\"}, "
            "{\"coremltools-version\", \"9.0\"}})]\n";
}

// one 1x1 conv: tensor<fp16,[1,IN,1,SEQ]> -> [1,OUT,1,SEQ]. weight [OUT,IN,1,1] from a blob.
static NSString *mil_conv(const char *p, const char *inp, int in_dim, int out_dim, int seq,
                          const char *blob, unsigned long long offset) {
    NSMutableString *m = [NSMutableString string];
    [m appendFormat:@"        string %s_pt = const()[name=string(\"%s_pt\"), val=string(\"valid\")];\n", p, p];
    [m appendFormat:@"        tensor<int32, [2]> %s_st = const()[name=string(\"%s_st\"), val=tensor<int32, [2]>([1,1])];\n", p, p];
    [m appendFormat:@"        tensor<int32, [4]> %s_pd = const()[name=string(\"%s_pd\"), val=tensor<int32, [4]>([0,0,0,0])];\n", p, p];
    [m appendFormat:@"        tensor<int32, [2]> %s_dl = const()[name=string(\"%s_dl\"), val=tensor<int32, [2]>([1,1])];\n", p, p];
    [m appendFormat:@"        int32 %s_gr = const()[name=string(\"%s_gr\"), val=int32(1)];\n", p, p];
    [m appendFormat:@"        tensor<fp16, [%d,%d,1,1]> %s_W = const()[name=string(\"%s_W\"), "
                    "val=tensor<fp16, [%d,%d,1,1]>(BLOBFILE(path=string(\"@model_path/weights/%s\"), offset=uint64(%llu)))];\n",
                    out_dim, in_dim, p, p, out_dim, in_dim, blob, offset];
    [m appendFormat:@"        tensor<fp16, [1,%d,1,%d]> %s_conv = conv(dilations=%s_dl, groups=%s_gr, "
                    "pad=%s_pd, pad_type=%s_pt, strides=%s_st, weight=%s_W, x=%s)[name=string(\"%s_conv\")];\n",
                    out_dim, seq, p, p, p, p, p, p, p, inp, p];
    return m;
}

static NSString *mil_program(NSString *body, NSString *input_decl, NSString *out_var) {
    return [NSString stringWithFormat:@"%@{\n    func main<ios18>(%@) {\n%@    } -> (%@);\n}\n",
            mil_header(), input_decl, body, out_var];
}

// ── BLOBFILE (128-byte header; format confirmed independently in maderix/ANE and Orion) ──────

static NSData *make_blob(int count, _Float16 fill) {
    int data_bytes = count * (int)sizeof(_Float16);
    int total = 128 + data_bytes;
    uint8_t *b = (uint8_t *)calloc(total, 1);
    b[0] = 1; b[4] = 2;
    b[64] = 0xEF; b[65] = 0xBE; b[66] = 0xAD; b[67] = 0xDE;
    b[68] = 1;
    *(uint32_t *)(b + 72) = (uint32_t)data_bytes;
    *(uint32_t *)(b + 80) = 128;
    _Float16 *w = (_Float16 *)(b + 128);
    for (int i = 0; i < count; i++) w[i] = fill;
    return [NSData dataWithBytesNoCopy:b length:total freeWhenDone:YES];
}

// ── the harness ──────────────────────────────────────────────────────────────────────────────

static Class K_CLIENT, K_DESC, K_IMM, K_REQ, K_AIO;
static NSTimeInterval g_compile_times[8];

// Build, compile, load and time ONE arm. `nconv` convs of in_dim -> out_dim/nconv each.
static double run_arm(NSString *label, int in_dim, int out_dim, int seq, int nconv, int iters,
                      double *out_ms, double *out_compile_ms) {
    @autoreleasepool {
        // SAME_SHAPE=1 keeps every conv at the full out_dim, so nconv varies the COUNT of weight
        // tensors without varying their size. That isolates the budget question -- Orion's own probe
        // held size constant for the same reason ("shape variety is irrelevant").
        int per = getenv("SAME_SHAPE") ? out_dim : out_dim / nconv;
        NSMutableString *body = [NSMutableString string];
        NSMutableDictionary *wdict = [NSMutableDictionary dictionary];

        // SHARED_BLOB=1 puts every conv's weights into ONE entry of the weights dict, at its own
        // offset. That separates "how many blob ENTRIES" from "how many const() references" --
        // which is exactly the question the M5 Max session raised against Orion's 16-tensor budget.
        int shared = getenv("SHARED_BLOB") != NULL;
        int perbytes = per * in_dim * 2;
        if (shared) {
            // One file, one block PER TENSOR: [128-byte header][payload] repeated. Tensor i is
            // referenced at (i * block) + 64 -- i.e. the payload sits 64 bytes past the reference,
            // which is what "64-byte header" means when measured from the reference rather than
            // from the file start. Each block carries its OWN magic and size; a single header for
            // the whole file cannot describe more than one tensor.
            int block = 128 + perbytes;
            NSMutableData *one = [NSMutableData dataWithCapacity:block * nconv];
            for (int c = 0; c < nconv; c++) {
                uint8_t hdr[128]; memset(hdr, 0, sizeof(hdr));
                hdr[0] = 1; hdr[4] = 2;
                hdr[64] = 0xEF; hdr[65] = 0xBE; hdr[66] = 0xAD; hdr[67] = 0xDE;
                hdr[68] = 1;
                *(uint32_t *)(hdr + 72) = (uint32_t)perbytes;
                *(uint32_t *)(hdr + 80) = 128;
                [one appendBytes:hdr length:128];
                _Float16 *w = (_Float16 *)calloc(per * in_dim, sizeof(_Float16));
                for (int i = 0; i < per * in_dim; i++) w[i] = (_Float16)1.0;
                [one appendBytes:w length:perbytes];
                free(w);
            }
            wdict[@"@model_path/weights/shared.bin"] = @{@"offset": @64, @"data": one};
            printf("      [shared blob: %d convs x %d B payload = %.1f KB, one file]\n",
                   nconv, perbytes, (block * nconv) / 1024.0);
            for (int c = 0; c < nconv; c++) {
                [body appendString:mil_conv([[NSString stringWithFormat:@"c%03d", c] UTF8String],
                                            "x", in_dim, per, seq, "shared.bin",
                                            (unsigned long long)(c * block + 64))];
            }
        } else {
        for (int c = 0; c < nconv; c++) {
            int wcount = per * in_dim;
            NSString *fname = [NSString stringWithFormat:@"w%d.bin", c];
            wdict[[NSString stringWithFormat:@"@model_path/weights/%@", fname]] =
                @{@"offset": @64, @"data": make_blob(wcount, (_Float16)1.0)};
            [body appendString:mil_conv([[NSString stringWithFormat:@"c%03d", c] UTF8String],
                                        "x", in_dim, per, seq, [fname UTF8String], (unsigned long long)(getenv("MIL_OFFSET") ? atoll(getenv("MIL_OFFSET")) : 64))];
        }
        }
        // Each conv gets an output node, then EVERY output is returned. Names are zero-padded so
        // alphabetical order equals numeric order: with unpadded names "c10_out" sorts before
        // "c2_out", and the surfaces (supplied alphabetically, Orion #3/#13) would silently
        // reorder against the tuple.
        for (int c = 0; c < nconv; c++)
            [body appendFormat:@"        tensor<fp16, [1,%d,1,%d]> c%03d_out = identity(x=c%03d_conv)[name=string(\"c%03d_out\")];\n",
                 per, seq, c, c, c];
        NSMutableArray *outs_list = [NSMutableArray array];
        for (int c = 0; c < nconv; c++)
            [outs_list addObject:[NSString stringWithFormat:@"c%03d_out", c]];
        NSString *outvar = [outs_list componentsJoinedByString:@", "];

        NSString *prog = mil_program(body,
            [NSString stringWithFormat:@"tensor<fp16, [1,%d,1,%d]> x", in_dim, seq], outvar);
        if (getenv("DUMP_MIL")) { printf("--- MIL for %s ---\n%s-------------------\n", label.UTF8String, prog.UTF8String); }
        NSData *milData = [prog dataUsingEncoding:NSUTF8StringEncoding];   // #9: NSData, not NSString

        NSError *e = nil;
        id desc = ((id(*)(Class,SEL,id,id,id))objc_msgSend)(K_DESC,
            @selector(modelWithMILText:weights:optionsPlist:), milData, wdict, nil);
        if (!desc) { printf("    %-14s modelWithMILText returned nil\n", label.UTF8String); return -1; }
        id model = ((id(*)(Class,SEL,id))objc_msgSend)(K_IMM, @selector(inMemoryModelWithDescriptor:), desc);
        id hexId = ((id(*)(id,SEL))objc_msgSend)(model, @selector(hexStringIdentifier));
        NSString *tmp = [NSTemporaryDirectory() stringByAppendingPathComponent:hexId];
        NSFileManager *fm = [NSFileManager defaultManager];
        [fm createDirectoryAtPath:[tmp stringByAppendingPathComponent:@"weights"]
            withIntermediateDirectories:YES attributes:nil error:nil];
        [milData writeToFile:[tmp stringByAppendingPathComponent:@"model.mil"] atomically:YES];
        // Write every blob the weights dictionary declares, whatever it is named. The loader reads
        // these back from disk even when the weights arrived in memory, so a dict entry with no
        // matching file on disk is simply absent -- and the program fails as InvalidMILProgram with
        // no hint that a file is missing. An earlier version assumed the w0..wN naming and so never
        // wrote the shared-file case at all.
        for (NSString *key in wdict) {
            NSString *fname = [key lastPathComponent];
            NSData *blob = wdict[key][@"data"];
            [blob writeToFile:[tmp stringByAppendingPathComponent:
                [NSString stringWithFormat:@"weights/%@", fname]] atomically:YES];
        }

        uint64_t tc = mach_absolute_time();
        BOOL ok = ((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
            model, @selector(compileWithQoS:options:error:), QOS, @{}, &e);
        double compile_ms = ms_since(tc);
        if (!ok) {
            printf("    %-14s COMPILE FAILED (%.0f ms) %s\n", label.UTF8String, compile_ms,
                   e ? [[e description] UTF8String] : "");
            bench_json(label.UTF8String, nconv, in_dim, per, seq, 0, 0, 0, compile_ms, -1, 0,
                       0, iters, NULL);
            return -1;
        }
        ok = ((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
            model, @selector(loadWithQoS:options:error:), QOS, @{}, &e);
        if (!ok) {
            printf("    %-14s LOAD FAILED %s\n", label.UTF8String, e ? [[e description] UTF8String] : "");
            return -1;
        }

        // IOSurfaces: all inputs and outputs the SAME allocation size (Orion constraint #2/#12).
        int maxc = in_dim > per ? in_dim : per;
        NSUInteger bytes = (NSUInteger)maxc * seq * 2;
        if (bytes < 49152) bytes = 49152;                     // #4: ~49 KB floor
        IOSurfaceRef inS = IOSurfaceCreate((__bridge CFDictionaryRef)@{
            (id)kIOSurfaceWidth:@(bytes), (id)kIOSurfaceHeight:@1,
            (id)kIOSurfaceBytesPerElement:@1, (id)kIOSurfaceBytesPerRow:@(bytes),
            (id)kIOSurfaceAllocSize:@(bytes), (id)kIOSurfacePixelFormat:@0});
        // Fill the input with 1.0 so the expected result is a plain arithmetic fact we can check:
        // with a 1x1 conv, all-ones weights and all-ones input, every output element is exactly
        // in_dim. A wrong BLOBFILE reference still COMPILES -- it just reads the wrong bytes -- so
        // only a value check can tell offsets apart.
        {
            IOSurfaceLock(inS, 0, NULL);
            _Float16 *p = (_Float16 *)IOSurfaceGetBaseAddress(inS);
            for (NSUInteger i = 0; i < bytes / 2; i++) p[i] = (_Float16)1.0;
            IOSurfaceUnlock(inS, 0, NULL);
        }
        id wIn = ((id(*)(Class,SEL,IOSurfaceRef))objc_msgSend)(K_AIO, @selector(objectWithIOSurface:), inS);

        NSMutableArray *outs = [NSMutableArray array], *oidx = [NSMutableArray array];
        // sized to nconv, which can be 128 -- a fixed [4] here overran the stack and aborted the
        // process AFTER the result line printed, so a valid 128-conv measurement had no JSON record
        IOSurfaceRef *outS = (IOSurfaceRef *)calloc(nconv, sizeof(IOSurfaceRef));
        for (int c = 0; c < nconv; c++) {
            outS[c] = IOSurfaceCreate((__bridge CFDictionaryRef)@{
                (id)kIOSurfaceWidth:@(bytes), (id)kIOSurfaceHeight:@1,
                (id)kIOSurfaceBytesPerElement:@1, (id)kIOSurfaceBytesPerRow:@(bytes),
                (id)kIOSurfaceAllocSize:@(bytes), (id)kIOSurfacePixelFormat:@0});
            [outs addObject:((id(*)(Class,SEL,IOSurfaceRef))objc_msgSend)(K_AIO, @selector(objectWithIOSurface:), outS[c])];
            [oidx addObject:@(c)];
        }
        id req = ((id(*)(Class,SEL,id,id,id,id,id,id,id))objc_msgSend)(K_REQ,
            @selector(requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:),
            @[wIn], @[@0], outs, oidx, nil, nil, @0);

        for (int i = 0; i < 10; i++)
            ((BOOL(*)(id,SEL,unsigned int,id,id,NSError**))objc_msgSend)(
                model, @selector(evaluateWithQoS:options:request:error:), QOS, @{}, req, &e);

        double *samples = malloc(sizeof(double) * iters);
        int done = 0;
        for (int i = 0; i < iters; i++) {
            uint64_t ti = mach_absolute_time();
            if (((BOOL(*)(id,SEL,unsigned int,id,id,NSError**))objc_msgSend)(
                    model, @selector(evaluateWithQoS:options:request:error:), QOS, @{}, req, &e)) {
                samples[done++] = ms_since(ti);
            }
        }
        double ms = 0;
        if (done > 0) {
            double *s = malloc(sizeof(double) * done);
            memcpy(s, samples, sizeof(double) * done);
            qsort(s, done, sizeof(double), cmp_double);
            ms = s[done / 2];           // within-run MEDIAN, not a mean
            free(s);
        }

        // correctness: read the first output element and compare against in_dim
        double observed = -1.0;
        {
            IOSurfaceLock(outS[0], kIOSurfaceLockReadOnly, NULL);
            _Float16 *o = (_Float16 *)IOSurfaceGetBaseAddress(outS[0]);
            observed = (double)o[0];
            IOSurfaceUnlock(outS[0], kIOSurfaceLockReadOnly, NULL);
        }
        int correct = (observed > in_dim * 0.99 && observed < in_dim * 1.01);

        double weight_bytes = (double)in_dim * per * 2.0 * nconv;
        double gbs = weight_bytes / (ms / 1000.0) / 1e9;
        double per_core = weight_bytes / 16.0;

        bench_json(label.UTF8String, nconv, in_dim, per, seq, per_core, ms, gbs,
                   compile_ms, observed, 1, done, iters, samples);
        free(samples);
        printf("    %-14s %3d conv  Cin %4d -> Cout %4d  |  %7.3f ms  %7.2f GB/s  %8.0f B/core (%.3f MiB)  out[0]=%.1f %s\n",
               label.UTF8String, nconv, in_dim, per, ms, gbs, per_core, per_core / 1048576.0,
               observed, correct ? "CORRECT" : "WRONG");

        ((BOOL(*)(id,SEL,unsigned int,NSError**))objc_msgSend)(model, @selector(unloadWithQoS:error:), QOS, &e);
        CFRelease(inS);
        for (int c = 0; c < nconv; c++) CFRelease(outS[c]);
        free(outS);
        [fm removeItemAtPath:tmp error:nil];

        if (out_ms) *out_ms = ms;
        if (out_compile_ms) *out_compile_ms = compile_ms;
        return gbs;
    }
}

int main(void) {
    setbuf(stdout, NULL);
    @autoreleasepool {
        mach_timebase_info(&g_tb);
        printf("  armed from maderix/ANE (MIT) + mechramc/Orion mil_builder (MIT)\n\n");

        if (!dlopen("/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/AppleNeuralEngine", RTLD_NOW)) {
            printf("  dlopen failed: %s\n", dlerror()); return 1;
        }
        K_CLIENT = NSClassFromString(@"_ANEClient");
        K_DESC   = NSClassFromString(@"_ANEInMemoryModelDescriptor");
        K_IMM    = NSClassFromString(@"_ANEInMemoryModel");
        K_REQ    = NSClassFromString(@"_ANERequest");
        K_AIO    = NSClassFromString(@"_ANEIOSurfaceObject");
        printf("  classes: desc=%s imm=%s req=%s aio=%s\n\n",
               K_DESC?"ok":"MISSING", K_IMM?"ok":"MISSING",
               K_REQ?"ok":"MISSING", K_AIO?"ok":"MISSING");

        {   // chip identity from the framework itself, so no machine needs its strings edited
            Class dev = NSClassFromString(@"_ANEDeviceInfo");
            SEL sArch = sel_registerName("aneArchitectureType");
            SEL sSub  = sel_registerName("aneSubType");
            SEL sCores= sel_registerName("numANECores");
            if (dev && class_respondsToSelector(object_getClass((id)dev), sArch)) {
                id v = ((id(*)(id,SEL))objc_msgSend)((id)dev, sArch);
                if (v) snprintf(g_chip, sizeof(g_chip), "%s", [[v description] UTF8String]);
            }
            if (dev && class_respondsToSelector(object_getClass((id)dev), sSub)) {
                id v = ((id(*)(id,SEL))objc_msgSend)((id)dev, sSub);
                if (v) snprintf(g_subtype, sizeof(g_subtype), "%s", [[v description] UTF8String]);
            }
            if (dev && class_respondsToSelector(object_getClass((id)dev), sCores))
                g_cores = (int)((unsigned int(*)(id,SEL))objc_msgSend)((id)dev, sCores);
        }
        sysctl_into("hw.model", g_hwmodel, sizeof(g_hwmodel));
        sysctl_into("kern.osversion", g_osbuild, sizeof(g_osbuild));
        sysctl_into("kern.osproductversion", g_osver, sizeof(g_osver));
        const char *jpath = getenv("BENCH_JSON");
        if (jpath) {
            FILE *f = fopen(jpath, "a");
            if (f) {
                fprintf(f, "{\"schema\":\"m5max-bench/1\",\"record\":\"machine\","
                           "\"machine\":{\"chip\":\"%s\",\"subtype\":\"%s\",\"cores\":%d,"
                           "\"hw_model\":\"%s\",\"os\":\"%s\",\"os_build\":\"%s\",\"arch\":\"arm64\"},\"ts\":%lld}\n",
                        g_chip, g_subtype, g_cores, g_hwmodel, g_osver, g_osbuild, (long long)time(NULL));
                fclose(f);
            }
        }
        printf("=== ANE kernel-DMA notch test — does the M4 have it? ===\n");
        printf("  chip: %s (%s), %d cores | hw_model=%s os=%s os_build=%s\n",
               g_chip, g_subtype, g_cores, g_hwmodel, g_osver, g_osbuild);

        // Standardise on the shape formula: bytes/core = (out/16)*in*2.
        //   2048->4096 = 8,388,608 over 16 cores = exactly 1 MiB
        //   2048->4032 = 8,257,536 = 1 MiB - 16 KiB  (the off-by-one-page control)
        //   2048->4096 as 2x2048 = two 0.5 MiB tasks  (the fix)
        //   4096->4096 = 2 MiB, a worse multiple
        // Order matters: a cold first arm can look slow for reasons that have nothing to do with
        // the transfer size. ORDER_REVERSE=1 flips the sequence so repeated runs can be interleaved
        // and the medians compared. That is the only way this result means anything.
        int rev = getenv("ORDER_REVERSE") != NULL;
        int it = getenv("ITERS") ? atoi(getenv("ITERS")) : 60;

        // SHAPES=cin,cout,seq,convs;cin,cout,seq,convs;...  lets the same harness bench the layer
        // shapes our real models contain, instead of only the erratum's boundary cases.
        const char *shapes = getenv("SHAPES");
        if (shapes) {
            printf("  custom shapes (%d iters):\n", it);
            NSString *all = @(shapes);
            for (NSString *spec in [all componentsSeparatedByString:@";"]) {
                NSArray *f = [spec componentsSeparatedByString:@","];
                if (f.count < 4) continue;
                run_arm([NSString stringWithFormat:@"%@", spec],
                        [f[0] intValue], [f[1] intValue], [f[2] intValue], [f[3] intValue], it, NULL, NULL);
            }
        } else {
        struct { const char *n; int in, out, nc; } arms[4] = {
            {"notch_1mib",  2048, 4096, 1},
            {"control_16k", 2048, 4032, 1},
            {"split_2x",    2048, 4096, 2},
            {"notch_2mib",  4096, 4096, 1},
        };
        printf("  arms (%s order, %d iters):\n", rev ? "REVERSE" : "forward", it);
        for (int i = 0; i < 4; i++) {
            int k = rev ? (3 - i) : i;
            run_arm(@(arms[k].n), arms[k].in, arms[k].out, 64, arms[k].nc, it, NULL, NULL);
        }
        }
        printf("  done\n");
    }
    return 0;
}