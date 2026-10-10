// kane_gate_probe.m — B5: does the 2606.22283 per-task kANE_* counter gate reproduce on h17c?
//
// The paper (Ch33) documents 24 per-task-descriptor counters (kANE_*) whose master enable is
// the stats mask at ANEProgramCreateArgs+0x6c; on the unentitled path aned zeroes the mask for
// ThirdPartyAppUsingANE, and forcing it non-zero makes kernel initStatsBufferSection bail on the
// zero-size stats-descriptor section (create->1, load->0). This probe checks, on OUR silicon
// (M5 Max h17c), what the runtime surface actually exposes: stats/perf selectors, the C entry
// points, and whether any counter name is resolvable. Recon only — no workload, no entitlement
// claims. Read-only by construction: enumeration + dlsym, one optional dry create gated behind
// --create (not run by default).
//
// build: clang -O2 -o kane_gate_probe kane_gate_probe.m -framework Foundation
// run:   ./kane_gate_probe [--create]

#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>

static const char *FRAMEWORK =
    "/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/AppleNeuralEngine";

static const char *KANE_NAMES[] = {
    "kANE_NE_COMPUTE_CYCLES","kANE_NE_INPUT_STALL_CYCLES","kANE_NE_OUTPUT_STALL_CYCLES",
    "kANE_NE_KERNEL_STALL_CYCLES","kANE_NE_THROTTLE_CYCLES","kANE_NE_NOMINAL_CYCLES",
    "kANE_NE_TO_L2_DATA","kANE_L2_TO_NE_DATA","kANE_L2PE_COMPUTE_CYCLES",
    "kANE_L2PE_INPUT_STALL_CYCLES","kANE_L2PE_OUTPUT_STALL_CYCLES","kANE_L2_NOMINAL_CYCLES",
    "kANE_L2_THROTTLE_CYCLES","kANE_L2_READ_STALL_CYCLES","kANE_L2_WRITE_STALL_CYCLES","kANE_L2_TO_AF_DATA","kANE_AF_TO_L2_DATA",
    "kANE_AF_TO_KM_DATA","kANE_KM_STALL_CYCLES","kANE_DMA_READ_BYTES",
    "kANE_DMA_READWRITE_BYTES","kANE_FP16_CYCLES","kANE_INT8_CYCLES","kANE_DPE_ENERGY",
};

static int stats_like_hits = 0;

static void scan_class(Class cls, BOOL classMethods) {
    Class target = classMethods ? object_getClass((id)cls) : cls;
    unsigned int n = 0;
    Method *ms = class_copyMethodList(target, &n);
    if (!ms) return;
    for (unsigned int i = 0; i < n; i++) {
        const char *sel = sel_getName(method_getName(ms[i]));
        if (strstr(sel, "stats") || strstr(sel, "Stats") || strstr(sel, "perf") ||
            strstr(sel, "Perf") || strstr(sel, "counter") || strstr(sel, "Counter") ||
            strstr(sel, "kane") || strstr(sel, "KANE")) {
            printf("  SEL %-52s [%s %s]\n", sel, class_getName(cls),
                   classMethods ? "(class)" : "(inst)");
            stats_like_hits++;
        }
    }
    free(ms);
}

// ── mask-forcing stage (paper Ch33 gate reproduction on h17c) ───────────────────────
#define QOS 21

static NSString *mil_prog(void) {
    NSString *p = @"c000";
    NSMutableString *body = [NSMutableString string];
    [body appendFormat:@"        string %@_pt = const()[name=string(\"%@_pt\"), val=string(\"valid\")];\n", p, p];
    [body appendFormat:@"        tensor<int32, [2]> %@_st = const()[name=string(\"%@_st\"), val=tensor<int32, [2]>([1,1])];\n", p, p];
    [body appendFormat:@"        tensor<int32, [4]> %@_pd = const()[name=string(\"%@_pd\"), val=tensor<int32, [4]>([0,0,0,0])];\n", p, p];
    [body appendFormat:@"        tensor<int32, [2]> %@_dl = const()[name=string(\"%@_dl\"), val=tensor<int32, [2]>([1,1])];\n", p, p];
    [body appendFormat:@"        int32 %@_gr = const()[name=string(\"%@_gr\"), val=int32(1)];\n", p, p];
    [body appendFormat:@"        tensor<fp16, [64,64,1,1]> %@_W = const()[name=string(\"%@_W\"), "
                       "val=tensor<fp16, [64,64,1,1]>(BLOBFILE(path=string(\"@model_path/weights/w0.bin\"), offset=uint64(64)))];\n", p, p];
    [body appendFormat:@"        tensor<fp16, [1,64,1,64]> %@_conv = conv(dilations=%@_dl, groups=%@_gr, "
                       "pad=%@_pd, pad_type=%@_pt, strides=%@_st, weight=%@_W, x=x)[name=string(\"%@_conv\")];\n", p, p, p, p, p, p, p, p];
    return [NSString stringWithFormat:
        @"program(1.3)\n[buildInfo = dict<string, string>({{\"coremlc-component-MIL\", \"3510.2.1\"}, "
        "{\"coremlc-version\", \"3505.4.1\"}, {\"coremltools-component-milinternal\", \"\"}, "
        "{\"coremltools-version\", \"9.0\"}})]\n{\n    func main<ios18>(tensor<fp16, [1,64,1,64]> x) {\n"
        "%@    } -> (c000_conv);\n}\n", body];
}

static int mask_stage(unsigned mask, Class K_DESC, Class K_IMM) {
    NSData *milData = [[mil_prog() dataUsingEncoding:NSUTF8StringEncoding] retain];
    int count = 64 * 64;
    int total = 128 + count * 2;
    uint8_t *b = (uint8_t *)calloc(total, 1);
    b[0] = 1; b[4] = 2; b[64]=0xEF; b[65]=0xBE; b[66]=0xAD; b[67]=0xDE; b[68]=1;
    *(uint32_t *)(b + 72) = (uint32_t)(count * 2); *(uint32_t *)(b + 80) = 128;
    _Float16 *w = (_Float16 *)(b + 128);
    for (int i = 0; i < count; i++) w[i] = (_Float16)1.0f;
    NSData *blob = [NSData dataWithBytesNoCopy:b length:total freeWhenDone:YES];
    NSDictionary *wdict = @{@"@model_path/weights/w0.bin": @{@"offset": @64, @"data": blob}};

    id desc = ((id(*)(Class,SEL,id,id,id))objc_msgSend)(K_DESC,
        @selector(modelWithMILText:weights:optionsPlist:), milData, wdict, nil);
    if (!desc) { printf("mask=0x%x: descriptor nil\n", mask); return -1; }
    id model = ((id(*)(Class,SEL,id))objc_msgSend)(K_IMM, @selector(inMemoryModelWithDescriptor:), desc);
    if (!model) { printf("mask=0x%x: inMemoryModel nil\n", mask); return -1; }
    if (mask) ((void(*)(id,SEL,unsigned))objc_msgSend)(model, @selector(setPerfStatsMask:), mask);
    unsigned mask_set = (unsigned)((unsigned(*)(id,SEL))objc_msgSend)(model, @selector(perfStatsMask));

    id hexId = ((id(*)(id,SEL))objc_msgSend)(model, @selector(hexStringIdentifier));
    NSString *tmp = [NSTemporaryDirectory() stringByAppendingPathComponent:hexId];
    NSFileManager *fm = [NSFileManager defaultManager];
    [fm createDirectoryAtPath:[tmp stringByAppendingPathComponent:@"weights"]
        withIntermediateDirectories:YES attributes:nil error:nil];
    [milData writeToFile:[tmp stringByAppendingPathComponent:@"model.mil"] atomically:YES];
    [blob writeToFile:[tmp stringByAppendingPathComponent:@"weights/w0.bin"] atomically:YES];

    NSError *e = nil;
    BOOL cok = ((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
        model, @selector(compileWithQoS:options:error:), QOS, @{}, &e);
    printf("mask=0x%x (set->%u): compile=%d %s\n", mask, mask_set, cok,
           (!cok && e) ? [[e description] UTF8String] : "");
    int rc = -1;
    if (cok) {
        e = nil;
        BOOL lok = ((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
            model, @selector(loadWithQoS:options:error:), QOS, @{}, &e);
        unsigned mask_after = (unsigned)((unsigned(*)(id,SEL))objc_msgSend)(model, @selector(perfStatsMask));
        printf("mask=0x%x: load=%d mask_after=%u %s\n", mask, lok, mask_after,
               (!lok && e) ? [[e description] UTF8String] : "");
        rc = lok ? 0 : 1;
        if (lok) ((BOOL(*)(id,SEL,unsigned int,NSError**))objc_msgSend)(
            model, @selector(unloadWithQoS:error:), QOS, &e);
    } else rc = 2;
    return rc;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        setbuf(stdout, NULL);
        BOOL try_create = argc > 1 && !strcmp(argv[1], "--create");
        printf("== kane_gate_probe (h17c recon) ==\n");
        if (!dlopen(FRAMEWORK, RTLD_LAZY)) { printf("dlopen failed: %s\n", dlerror()); return 1; }

        int ncls = objc_getClassList(NULL, 0);
        Class *cls = calloc(ncls, sizeof(Class));
        ncls = objc_getClassList(cls, ncls);
        printf("classes loaded: %d\n", ncls);
        for (int i = 0; i < ncls; i++) {
            const char *name = class_getName(cls[i]);
            if (strstr(name, "ANE") || strstr(name, "NeuralEngine")) {
                scan_class(cls[i], NO);
                scan_class(cls[i], YES);
            }
        }
        free(cls);
        printf("stats-like selectors found: %d\n", stats_like_hits);

        void *fw = dlopen(FRAMEWORK, RTLD_LAZY);
        const char *csyms[] = {"ANE_ProgramCreate","ANE_ProgramLoad","ANE_ProgramCreate2",
                               "ANEClientCreateWithContext","ANE_NewXPCConnection",NULL};
        for (int i = 0; csyms[i]; i++)
            printf("C sym %-28s framework: %s\n", csyms[i], dlsym(fw, csyms[i]) ? "FOUND" : "absent");
        const char *libs[] = {"/usr/lib/libANECompiler.dylib",
            "/System/Library/PrivateFrameworks/ANEServices.framework/ANEServices",
            "/System/Library/DriverExtensions/com.apple.DriverKit-AppleANS3CG.explicitcatmatch/"
            "com.apple.DriverKit-AppleANS3CG", NULL};
        for (int i = 0; libs[i]; i++) {
            void *h = dlopen(libs[i], RTLD_LAZY);
            printf("lib %s: %s\n", libs[i], h ? "loads" : "absent");
            if (h) for (int k = 0; csyms[k]; k++)
                if (dlsym(h, csyms[k])) printf("   C sym %s FOUND in %s\n", csyms[k], libs[i]);
        }

        printf("kANE_* names (paper Table 33.1): %d documented; local symbol resolution: ",
               (int)(sizeof(KANE_NAMES)/sizeof(*KANE_NAMES)));
        int resolved = 0;
        for (unsigned int i = 0; i < sizeof(KANE_NAMES)/sizeof(*KANE_NAMES); i++)
            if (dlsym(RTLD_DEFAULT, KANE_NAMES[i])) resolved++;
        printf("%d/24 (enum constants, not exported symbols — expected 0)\n", resolved);

        // the real accessor surface: _ANEPerformanceStats stringForPerfCounter:
        Class PS = objc_getClass("_ANEPerformanceStats");
        SEL sName = sel_registerName("stringForPerfCounter:");
        printf("PS class: %s | instance-method: %d\n", PS ? "found" : "nil",
               PS ? (int)(class_getInstanceMethod(PS, sName) != NULL) : -1);
        id psInst = PS ? class_createInstance((Class)PS, 0) : nil;
        SEL sInit = sel_registerName("initWithHardwareExecution:perfCounterData:ANEStatsRawData:");
        if (psInst && class_getInstanceMethod(PS, sInit))
            psInst = ((id(*)(id,SEL,double,id,id))objc_msgSend)(psInst, sInit, 0.0, nil, nil);
        printf("instance: %s\n", psInst ? "ok (designated init)" : "nil");
        if (psInst && class_getInstanceMethod(PS, sName)) {
            printf("live enumeration via -[stringForPerfCounter:] (unshared instance):\n");
            int found = 0;
            for (int i = 0; i < 48; i++) {
                @autoreleasepool {
        setbuf(stdout, NULL);
                    id s = ((id(*)(id,SEL,int))objc_msgSend)(psInst, sName, i);
                    if (s && [s isKindOfClass:NSString.class] && [(NSString*)s length]) {
                        const char *nm = [(NSString*)s UTF8String];
                        if (nm && (strstr(nm,"kANE")||strstr(nm,"ANE"))) {
                            char clean[64];
                            size_t L = strlen(nm);
                            snprintf(clean, sizeof clean, "%.*s", (int)(nm[L-1]==':' ? L-1 : L), nm);
                            int in_paper = 0;
                            for (unsigned int k = 0; k < sizeof(KANE_NAMES)/sizeof(*KANE_NAMES); k++)
                                if (!strcmp(clean, KANE_NAMES[k])) in_paper = 1;
                            printf("  [%2d] %-32s %s\n", i, nm, in_paper ? "(in paper)" :
                                   (strstr(nm,"UKNOWN") ? "(padding, Apple's typo)" : "(NEW)"));
                            if (in_paper) found++;
                        }
                    }
                }
            }
            printf("paper-named counters enumerable on h17c: %d/24\n", found);
        } else {
            printf("stringForPerfCounter: accessor absent or class missing\n");
        }

        if (try_create) {
            Class K_DESC = objc_getClass("_ANEInMemoryModelDescriptor");
            Class K_IMM  = objc_getClass("_ANEInMemoryModel");
            if (!K_DESC || !K_IMM) { printf("--create: classes missing\n"); }
            else {
                printf("--create mask-forcing stage (control then forced):\n");
                int r0 = mask_stage(0, K_DESC, K_IMM);
                int r1 = mask_stage(0xf, K_DESC, K_IMM);
                printf("MASK-VERDICT control(load)=%d forced(load)=%d "
                       "(0=load-ok 1=load-fails 2=compile-fails)\n", r0, r1);
            }
        } else printf("--create not given: mask-forcing stage skipped\n");
        printf("VERDICT: recon only; gate reproduction status in knowledge/ane/10 B5 addendum\n");
    }
    return 0;
}
