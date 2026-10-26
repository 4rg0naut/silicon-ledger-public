// probe4_grammar — EXP-033 C-75: live verdict per selector using the decoded
// per-entry contracts from _sANEDriverDirectPathClientMethods (AppleH16ANEInterface
// 10.19.2, kernelcache 26A434__Mac17,14). Zero-arg selectors called bare;
// struct selectors with exact decoded sizes.
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <string.h>
#include <mach/mach_time.h>

typedef struct { uint32_t sel; uint32_t scalarIn; uint32_t structIn; uint32_t scalarOut; uint32_t structOut; } contract_t;

static contract_t K[] = {
    {0,0,136,0,136},{1,0,0,0,0},{2,0,3152,1,64},{3,0,40,0,0},{4,0,3104,0,0},
    {5,1,2088,0,0},{6,0,2088,0,0},{7,0,16,0,24},{8,0,32,0,0},{9,1,520,0,0},{10,0,0,1,0},
};

int main(void) {
    io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("ANEDriver"));
    if (!svc) { printf("no ANEDriver service\n"); return 1; }
    io_connect_t conn = MACH_PORT_NULL;
    kern_return_t okr = IOServiceOpen(svc, mach_task_self(), 1, &conn);
    printf("open type 1 kr=0x%x\n", okr);
    if (okr != KERN_SUCCESS) return 1;
    for (size_t i = 0; i < sizeof(K)/sizeof(K[0]); i++) {
        contract_t *c = &K[i];
        char inbuf[4096]; memset(inbuf, 0, sizeof inbuf);
        char outbuf[4096]; memset(outbuf, 0, sizeof outbuf);
        uint64_t scalars[2] = {0xface0000faceULL, 0}; // poison marker (EXP-031 C-64 rule)
        uint32_t outCnt = c->scalarOut ? 1 : 0;
        size_t oSz = c->structOut;
        kern_return_t kr;
        uint64_t t0 = mach_absolute_time();
        kr = IOConnectCallMethod(conn, c->sel,
            scalars, c->scalarIn,
            c->structIn ? inbuf : NULL, c->structIn,
            scalars, &outCnt,
            c->structOut ? outbuf : NULL, c->structOut ? &oSz : NULL);
        static mach_timebase_info_data_t tb = {0,0};
        if (!tb.denom) mach_timebase_info(&tb);
        double us = (double)(mach_absolute_time() - t0) * tb.numer / tb.denom / 1000.0;
        int echo = 0;
        unsigned char *ob = (unsigned char*)outbuf;
        for (size_t j = 0; j + 2 <= c->structOut; j++)
            if (ob[j] == 0xce && ob[j+1] == 0xfa) { echo = (int)j; break; }
        printf("sel %2d contract(sIn=%u sSZ=%u sOut=%u oSZ=%u) kr=0x%x oSz_back=%zu scalar_out0=0x%llx poison_echo=%s lat_us=%.1f\n",
               c->sel, c->scalarIn, c->structIn, c->scalarOut, c->structOut, kr, oSz, scalars[0],
               echo ? "FOUND" : "none", us);
        if (kr == KERN_SUCCESS && c->structOut) {
            printf("   out hex (first %zu):", oSz > 136 ? 136 : oSz);
            unsigned char *p = (unsigned char*)outbuf;
            for (size_t j = 0; j < (oSz > 136 ? 136 : oSz); j++) printf(" %02x", p[j]);
            printf("\n");
        }
    }
    IOServiceClose(conn);
    printf("closed\n");
    return 0;
}
