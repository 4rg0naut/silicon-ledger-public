// ane_roundtrip — EXP-032 C-69: open ANEDriverRoot user client (type 1) and
// invoke selector 0x12 (getDeviceInfo per framework disassembly, C-68).
// Read-only query; no workload, no state change.
#include <IOKit/IOKitLib.h>
#include <stdio.h>
#include <string.h>

#define kSelectorGetDeviceInfo 0x12

static void try_selector(io_connect_t conn, uint32_t sel) {
    uint64_t in[1] = {0};
    uint64_t out[8] = {0};
    uint32_t outCnt = 8;
    kern_return_t kr = IOConnectCallMethod(conn, sel, in, 1, NULL, 0, out, &outCnt, NULL, 0);
    printf("selector 0x%x kr=0x%x%s out=[%llu %llu %llu %llu] (outCnt=%u)\n",
           sel, kr, kr == KERN_SUCCESS ? " (OK)" : "",
           out[0], out[1], out[2], out[3], (unsigned)outCnt);
}

int main(int argc, char **argv) {
    uint32_t type = argc > 1 ? (uint32_t)strtoul(argv[1], NULL, 0) : 1;
    uint32_t sel = argc > 2 ? (uint32_t)strtoul(argv[2], NULL, 0) : kSelectorGetDeviceInfo;

    CFMutableDictionaryRef m = IOServiceMatching("ANEDriver");
    io_iterator_t it;
    kern_return_t kr = IOServiceGetMatchingServices(kIOMainPortDefault, m, &it);
    if (kr != KERN_SUCCESS) { printf("match kr=0x%x\n", kr); return 1; }
    io_service_t svc = IOIteratorNext(it);
    IOObjectRelease(it);
    if (!svc) { printf("no ANEDriver instance\n"); return 1; }

    io_connect_t conn = MACH_PORT_NULL;
    kr = IOServiceOpen(svc, mach_task_self(), type, &conn);
    printf("IOServiceOpen(type %u) kr=0x%x\n", type, kr);
    IOObjectRelease(svc);
    if (kr != KERN_SUCCESS) return 1;

    try_selector(conn, sel);
    if (argc <= 2) {
        for (uint32_t s = 0; s <= 0x20; s++) try_selector(conn, s);
    }
    IOServiceClose(conn);
    printf("closed\n");
    return 0;
}
