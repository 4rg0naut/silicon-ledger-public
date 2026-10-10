// metal_counters.m — #8 fallback ladder stage 3: what does MTLDevice counter sampling expose on M5 Max?
//
// Context. EXP-022/EXP-024 calibration showed the unprivileged IOReport surface on macOS 27 has no
// calibrated positive signal for the M5 GPU neural accelerator ("GPU-NA"): the UT_EXT_* channels are
// PMGR utilization tracking and failed calibration (documented trick, not metric, EXP-004 rule), and
// the classic IOAccelerator PerformanceStatistics keys carry no tensor/NA names (stage 2 finding).
// This probe enumerates the Metal-level counter surface instead: MTLDevice counter sets and their
// counters, supported counter sampling points, then attempts one real MTLCounterSampleBuffer capture
// around a compute kernel to establish whether sampling works unprivileged on this machine at all,
// and what the resolved buffers actually contain (do they move with tensor dispatch?).
//
// Build: clang -O2 -o /tmp/metal_counters bench/metal_counters.m -framework Foundation -framework Metal
// Run:   /tmp/metal_counters [out.json]

#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

static NSString *q(NSString *s) { return s ?: @"null"; }

static void dumpResolved(NSMutableString *out, id<MTLCounterSet> cs, NSData *data, NSString *tag) {
    NSUInteger n = cs.counters.count;
    if (!data) { [out appendFormat:@",\n    \"%s\": \"resolve returned nil\"", tag.UTF8String]; return; }
    NSUInteger nValues = data.length / sizeof(uint64_t);
    const uint64_t *v = data.bytes;
    [out appendFormat:@",\n    \"%s\": {\"bytes\": %lu, \"values\": [", tag.UTF8String, (unsigned long)data.length];
    for (NSUInteger i = 0; i < nValues && i < 16; i++) {
        NSString *nm = (i < n) ? cs.counters[i].name : @"?";
        [out appendFormat:@"%s{\"counter\": \"%@\", \"value\": %llu}", i ? ", " : "", nm, v[i]];
    }
    [out appendString:@"]}"];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
        if (!dev) { fprintf(stderr, "no default Metal device\n"); return 1; }

        NSMutableString *out = [NSMutableString string];
        [out appendFormat:@"{\n  \"device\": \"%@\",\n", dev.name];

        // counter sampling point support
        NSArray *pts = @[
            @[@"AtStageBoundary", @(MTLCounterSamplingPointAtStageBoundary)],
            @[@"AtDrawBoundary", @(MTLCounterSamplingPointAtDrawBoundary)],
            @[@"AtDispatchBoundary", @(MTLCounterSamplingPointAtDispatchBoundary)],
            @[@"AtTileDispatchBoundary", @(MTLCounterSamplingPointAtTileDispatchBoundary)],
            @[@"AtBlitBoundary", @(MTLCounterSamplingPointAtBlitBoundary)],
        ];
        [out appendString:@"  \"counterSamplingPoints\": {"];
        for (NSUInteger i = 0; i < pts.count; i++)
            [out appendFormat:@"%s\"%@\": %s", i ? ", " : "", pts[i][0],
                [dev supportsCounterSampling:(MTLCounterSamplingPoint)[pts[i][1] integerValue]] ? "true" : "false"];
        [out appendString:@"},\n"];

        // full counter-set inventory
        [out appendString:@"  \"counterSets\": [\n"];
        id<MTLCounterSet> sample = nil;
        for (NSUInteger si = 0; si < dev.counterSets.count; si++) {
            id<MTLCounterSet> cs = dev.counterSets[si];
            [out appendFormat:@"    {\"name\": \"%@\", \"counters\": [", cs.name];
            for (NSUInteger ci = 0; ci < cs.counters.count; ci++)
                [out appendFormat:@"%s\"%@\"", ci ? ", " : "", cs.counters[ci].name];
            [out appendFormat:@"]}%s\n", si + 1 < dev.counterSets.count ? "," : ""];
            if ([cs.name isEqualToString:MTLCommonCounterSetStatistic]) sample = cs;
            if (!sample) sample = cs;
        }
        [out appendString:@"  ],\n"];

        // attempt a real sample-buffer capture around a trivial compute kernel
        [out appendString:@"  \"samplingAttempt\": {\"counterSet\": "];
        [out appendFormat:@"\"%@\"", q(sample.name)];
        NSError *err = nil;
        NSString *src = @"kernel void noop(device float *x [[buffer(0)]]) { x[0] = x[0] * 2.0f + 1.0f; }";
        id<MTLLibrary> lib = [dev newLibraryWithSource:src options:nil error:&err];
        if (!lib) {
            [out appendFormat:@", \"compileError\": \"%@\"}", q(err.localizedDescription)];
        } else {
            id<MTLFunction> fn = [lib newFunctionWithName:@"noop"];
            id<MTLComputePipelineState> pso = fn ? [dev newComputePipelineStateWithFunction:fn error:&err] : nil;
            MTLCounterSampleBufferDescriptor *d = [MTLCounterSampleBufferDescriptor new];
            d.counterSet = sample;
            d.storageMode = MTLStorageModeShared;
            d.sampleCount = 4;
            id<MTLCounterSampleBuffer> sb = pso ? [dev newCounterSampleBufferWithDescriptor:d error:&err] : nil;
            if (!sb) {
                [out appendFormat:@", \"error\": \"%@\"}", q(err.localizedDescription)];
            } else {
                id<MTLCommandQueue> q2 = [dev newCommandQueue];
                id<MTLBuffer> buf = [dev newBufferWithLength:sizeof(float) options:MTLResourceStorageModeShared];
                BOOL canDispatch = [dev supportsCounterSampling:MTLCounterSamplingPointAtDispatchBoundary];
                BOOL canStage = [dev supportsCounterSampling:MTLCounterSamplingPointAtStageBoundary];
                BOOL force = getenv("STAGE3_FORCE_ENCODER") != nil;
                id<MTLCommandBuffer> cb = [q2 commandBuffer];
                id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
                [enc setComputePipelineState:pso];
                [enc setBuffer:buf offset:0 atIndex:0];
                if (canDispatch && force) {
                    [enc sampleCountersInBuffer:sb atSampleIndex:0 withBarrier:YES];
                    [enc dispatchThreads:MTLSizeMake(32, 1, 1) threadsPerThreadgroup:MTLSizeMake(32, 1, 1)];
                    [enc sampleCountersInBuffer:sb atSampleIndex:1 withBarrier:YES];
                } else {
                    [enc dispatchThreads:MTLSizeMake(32, 1, 1) threadsPerThreadgroup:MTLSizeMake(32, 1, 1)];
                }
                [enc endEncoding];
                [cb commit];
                [cb waitUntilCompleted];
                NSData *r0 = [sb resolveCounterRange:NSMakeRange(0, 1)];
                NSData *r1 = [sb resolveCounterRange:NSMakeRange(1, 1)];
                [out appendFormat:@", \"encoderSamplingCalled\": %s, \"supportsDispatch\": %s, \"supportsStage\": %s",
                    (canDispatch && force) ? "true" : "false",
                    canDispatch ? "true" : "false", canStage ? "true" : "false"];
                dumpResolved(out, sample, r0, @"sample0");
                dumpResolved(out, sample, r1, @"sample1");
                [out appendString:@"}"];
            }
        }
        [out appendString:@",\n  \"note\": \"raw bytes; values are u64 LE aligned to counter order per resolveCounterRange doc\"\n}\n"];

        NSString *path = (argc > 1) ? [NSString stringWithUTF8String:argv[1]] : nil;
        if (path) {
            [out writeToURL:[NSURL fileURLWithPath:path] atomically:YES encoding:NSUTF8StringEncoding error:nil];
            fprintf(stderr, "wrote %s\n", path.UTF8String);
        }
        printf("%s", out.UTF8String);
    }
    return 0;
}
