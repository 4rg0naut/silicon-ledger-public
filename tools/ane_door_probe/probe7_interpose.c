// probe7_interpose.c — EXP-035 C-84: DYLD-inserted interpose shim for the ANE door.
// Captures every IOConnectCallMethod / IOConnectCallStructMethod / IOServiceOpen issued by
// OUR OWN process (no SIP constraint) — used to watch what the proven in-process
// _ANEInMemory compile path (mil_battery baseline) actually sends to ANEDriver.
//
// Correct ABI (arm64, IOKitLib.h 26A434): IOConnectCallMethod takes 10 params — scalar
// input 3-4, STRUCT input 5-6, scalar output 7-8, struct output 9-10; IOConnectCallStructMethod
// takes 6 — inputStruct param 3, inputStructCnt param 4. The very first draft misread the
// selector (param 2) as the size and would have dumped 2 bytes of a 3152 B blob.
//
// Build:
//   clang -dynamiclib -o probe7_interpose.dylib probe7_interpose.c -framework IOKit -framework CoreFoundation
// Validate (known-good send, must show CALL sel=0x2 structIn[3152] hex):
//   ANE_CAPTURE=/tmp/p7_selftest.txt DYLD_INSERT_LIBRARIES=probe7_interpose.dylib ./probe6b_chain
// Use:
//   ANE_CAPTURE=/tmp/p7.txt DYLD_INSERT_LIBRARIES=probe7_interpose.dylib ./mil_battery baseline
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <mach/message.h>
#include <mach/mach.h>
#include <IOKit/IOKitLib.h>

#define HEXCAP 4096

static FILE *out = NULL;
static void caph(void) {
    if (!out) {
        const char *p = getenv("ANE_CAPTURE");
        out = fopen(p ? p : "/tmp/probe7_capture.txt", "w");
    }
}
// Never trust a user pointer before proving it readable in our own task — captures run
// inside arbitrary target processes (defensive, per the poison-0xFACE discipline).
static int rd32(const void *p, uint32_t *v) {
    if (!p) return 0;
    vm_size_t n = 0;
    return vm_read_overwrite(mach_task_self(), (vm_address_t)p, sizeof(uint32_t),
                             (vm_address_t)v, &n) == KERN_SUCCESS && n == sizeof(uint32_t);
}
static int rd64(const void *p, uint64_t *v) {
    if (!p) return 0;
    vm_size_t n = 0;
    return vm_read_overwrite(mach_task_self(), (vm_address_t)p, sizeof(uint64_t),
                             (vm_address_t)v, &n) == KERN_SUCCESS && n == sizeof(uint64_t);
}
static void hexlog(const unsigned char *b, size_t n) {
    if (!out || !b) return;
    if (n > HEXCAP) n = HEXCAP;
    for (size_t i = 0; i < n; i += 16) {
        fprintf(out, "    %04zx: ", i);
        for (size_t j = 0; j < 16 && i + j < n; j++) fprintf(out, "%02x ", b[i + j]);
        fprintf(out, "\n");
    }
}

// kern_return_t IOConnectCallMethod(mach_port_t connection, uint32_t selector,
//   const uint64_t *input, uint32_t inputCnt,
//   const void *inputStruct, size_t inputStructCnt,
//   uint64_t *output, uint32_t *outputCnt,
//   void *outputStruct, size_t *outputStructCnt)
// Note the ORDER: struct input is params 5-6, scalar output 7-8 (an earlier draft assumed
// scalar output at 5-6 and segfaulted dereferencing the 3152 size as a count pointer).
typedef kern_return_t (*call10fn)(io_connect_t, uint32_t, const uint64_t *,
    uint32_t, const void *, size_t, uint64_t *, uint32_t *, void *, size_t *);
static call10fn orig_Call;
static kern_return_t cap_Call(io_connect_t c, uint32_t sel, const uint64_t *si,
    uint32_t sic, const void *stin, size_t stinN, uint64_t *so, uint32_t *soc,
    void *stout, size_t *stoutN) {
    caph();
    kern_return_t kr = orig_Call(c, sel, si, sic, stin, stinN, so, soc, stout, stoutN);
    fprintf(out, "CALL conn=%u sel=0x%x scalarsIn=[", c, sel);
    for (uint32_t i = 0; i < sic && i < 32; i++) {
        uint64_t v = 0;
        if (!rd64((const uint64_t *)si + i, &v)) { fprintf(out, "<unreadable>"); break; }
        fprintf(out, "0x%llx,", v);
    }
    fprintf(out, "] structIn=%p[%zu] -> kr=0x%x scalarsOut=[", stin, stinN, kr);
    uint32_t sonc = 0;
    if (soc) {
        if (rd32(soc, &sonc)) {
            for (uint32_t i = 0; so && i < sonc && i < 32; i++) {
                uint64_t v = 0;
                if (!rd64(so + i, &v)) { fprintf(out, "<unreadable>"); break; }
                fprintf(out, "0x%llx,", v);
            }
        } else {
            fprintf(out, "<bad_count_ptr:%p>", (void *)soc);
        }
    }
    size_t sb = 0;
    fprintf(out, "] structOutSz_back=%zu\n", (stoutN && rd64(stoutN, (uint64_t*)&sb)) ? sb : 0);
    if (stin && stinN && stinN <= HEXCAP) { fprintf(out, "  structIn[%zu]:\n", stinN); hexlog(stin, stinN); }
    else if (stin && stinN) fprintf(out, "  structIn size 0x%zx implausible (garbled arg pair?)\n", stinN);
    fflush(out);
    return kr;
}

// kern_return_t IOConnectCallStructMethod(io_connect_t, uint32_t selector,
//   const void *inputStruct, size_t inputStructCnt,
//   void *outputStruct, size_t *outputStructCnt)
typedef kern_return_t (*struct6fn)(io_connect_t, uint32_t, const void *, size_t, void *, size_t *);
static struct6fn orig_Struct;
static kern_return_t cap_Struct(io_connect_t c, uint32_t sel, const void *in, size_t inN,
    void *stout, size_t *stoutN) {
    caph();
    kern_return_t kr = orig_Struct(c, sel, in, inN, stout, stoutN);
    fprintf(out, "STRUCT conn=%u sel=0x%x in[%zu] -> kr=0x%x outSz_back=%zu\n",
        c, sel, inN, kr, stoutN ? *stoutN : 0);
    if (in && inN) { fprintf(out, "  blob[%zu]:\n", inN); hexlog(in, inN); }
    fflush(out);
    return kr;
}

static kern_return_t (*orig_Open)(io_service_t, task_port_t, uint32_t, io_connect_t *);
static kern_return_t cap_Open(io_service_t s, task_port_t task, uint32_t type, io_connect_t *c) {
    char cls[128] = "?";
    IOObjectGetClass(s, cls);
    kern_return_t kr = IOServiceOpen(s, task, type, c);
    caph();
    fprintf(out, "OPEN service=%s type=0x%x -> kr=0x%x conn=%u\n", cls, type, kr,
        (kr == KERN_SUCCESS && c) ? *c : 0);
    fflush(out);
    return kr;
}

typedef struct { const void *repl, *orig; } interpose_t;
__attribute__((used, section("__DATA,__interpose")))
static interpose_t interposed[] = {
    { (const void *)cap_Call,   (const void *)IOConnectCallMethod },
    { (const void *)cap_Struct, (const void *)IOConnectCallStructMethod },
    { (const void *)cap_Open,   (const void *)IOServiceOpen },
};

__attribute__((constructor)) static void p7init(void) {
    // dlsym(RTLD_NEXT) from inside the interposing dylib returns the interposed address
    // (self-recursion, stack overflow) — dyld resolves the table's orig field to the
    // real implementations; take originals from there.
    orig_Call   = (call10fn)interposed[0].orig;
    orig_Struct = (struct6fn)interposed[1].orig;
    orig_Open   = (kern_return_t (*)(io_service_t, task_port_t, uint32_t, io_connect_t *))interposed[2].orig;
    caph();
}
