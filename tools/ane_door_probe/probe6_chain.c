// EXP-034 C-80 chaining spike: does sel-2 (3152B) gate on a session handle in word[0]?
// Candidate handle ladder on the type-1 direct-path door. Zero-residue protocol.
#include <IOKit/IOKitLib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(void) {
    io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("ANEDriver"));
    if (!svc) { printf("no ANEDriver\n"); return 2; }
    io_connect_t conn = 0;
    kern_return_t kr = IOServiceOpen(svc, mach_task_self(), 1, &conn);
    printf("open type 1 kr=0x%x pid=%d\n", kr, getpid());
    if (kr != KERN_SUCCESS) { IOObjectRelease(svc); return 2; }

    unsigned long long cands[] = {0, 1, 2, 3, 4, 8, 0x10, 0x20, 100, (unsigned long long)getpid(), 0x1000, 0xffff};
    for (size_t i = 0; i < sizeof(cands)/sizeof(cands[0]); i++) {
        unsigned char in[3152];
        memset(in, 0, sizeof(in));
        memcpy(in, &cands[i], 8); // word[0] = candidate handle
        unsigned char out[64] = {0};
        size_t osz = 64;
        unsigned long long scal[1] = {0xface0000face};
        uint32_t scount = 1;
        kr = IOConnectCallMethod(conn, 2, NULL, 0, in, sizeof(in), scal, &scount, out, &osz);
        printf("sel2 word0=0x%llx kr=0x%x oSz_back=%zu scalar0=0x%llx\n",
               cands[i], kr, osz, scal[0]);
    }
    IOServiceClose(conn);
    IOObjectRelease(svc);
    printf("done\n");
    return 0;
}
