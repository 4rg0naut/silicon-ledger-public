// ane_door_probe2 — EXP-032 C-69: second pass — more ANE classes + open types.
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static const char *kClasses[] = {
    "ANEDriver",
    "ANEHWDevice",
    "ANEClientInterface",
    "ANEScheduler",
    "H1xANELoadBalancer",
    "H1xANELoadBalancerClient",
    "ANEClientHints",
    "ANEInVMAllocator",
    "ANEPrivilegedVMAccess",
    "ANEExclaveProxy",
    "ANEDriverDebugClient",
    "IOReport",
};

static uint32_t kTypes[] = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,0x21,0x22,0x23,0x24,0x25,0x26,0x27,0x28,0x29,0x2a,0x2b,0x2c,0x2d,0x2e,0x2f,0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39,0x3a,0x3b,0x3c,0x3d,0x3e,0x3f,0x40,0x41,0x42,0x43,0x44,0x45,0x46,0x47,0x48,0x50,0x60,0x6c,0x70,0x80,0x100,0x7100,0x7101,0x8000};

int main(int argc, char **argv) {
    int scan_types = argc > 1 && !strcmp(argv[1], "--scan-types");
    for (size_t c = 0; c < sizeof(kClasses)/sizeof(kClasses[0]); c++) {
        CFMutableDictionaryRef m = IOServiceMatching(kClasses[c]);
        if (!m) { printf("class %-32s IOServiceMatching failed\n", kClasses[c]); continue; }
        io_iterator_t it;
        kern_return_t kr = IOServiceGetMatchingServices(kIOMainPortDefault, m, &it);
        if (kr != KERN_SUCCESS) { printf("class %-32s match kr=0x%x\n", kClasses[c], kr); continue; }
        int found = 0;
        io_service_t svc;
        while ((svc = IOIteratorNext(it)) != IO_OBJECT_NULL) {
            found = 1;
            io_name_t iname;
            IORegistryEntryGetName(svc, iname);
            printf("class %-32s instance=%s\n", kClasses[c], iname);
            if (scan_types) {
                for (size_t t = 0; t < sizeof(kTypes)/sizeof(kTypes[0]); t++) {
                    io_connect_t conn = MACH_PORT_NULL;
                    kern_return_t okr = IOServiceOpen(svc, mach_task_self(), kTypes[t], &conn);
                    printf("  open type 0x%x kr=0x%x%s\n", kTypes[t], okr,
                           okr == KERN_SUCCESS ? " (OPENED)" : "");
                    if (okr == KERN_SUCCESS) IOServiceClose(conn);
                }
            } else {
                io_connect_t conn = MACH_PORT_NULL;
                kern_return_t okr = IOServiceOpen(svc, mach_task_self(), 0, &conn);
                printf("  IOServiceOpen(type 0) kr=0x%x%s\n", okr,
                       okr == KERN_SUCCESS ? " (OPENED)" : "");
                if (okr == KERN_SUCCESS) IOServiceClose(conn);
            }
            IOObjectRelease(svc);
        }
        if (!found) printf("class %-32s (no instances)\n", kClasses[c]);
        IOObjectRelease(it);
    }
    return 0;
}
