// ane_whoami — EXP-032 C-69: after IOServiceOpen(ANEDriverRoot, type N),
// enumerate the load-balancer's client children to see which client object
// our connection created (server-side identity of the door).
#include <IOKit/IOKitLib.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>

static const char *kClientClasses[] = {
    "H1xANELoadBalancerClient",
    "H1xANELoadBalancerDirectPathClient",
    "ANEClientHintsUserClient",
    "ANEDriverDebugClient",
};

static void dumpChildren(const char *cls) {
    CFMutableDictionaryRef m = IOServiceMatching(cls);
    io_iterator_t it;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, m, &it) != KERN_SUCCESS) return;
    io_service_t c;
    while ((c = IOIteratorNext(it)) != IO_OBJECT_NULL) {
        io_name_t pn = {0}, cn = {0};
        io_service_t parent = IO_OBJECT_NULL;
        if (IORegistryEntryGetParentEntry(c, kIOServicePlane, &parent) == KERN_SUCCESS) {
            IORegistryEntryGetName(parent, pn);
            IOObjectRelease(parent);
        }
        IORegistryEntryGetName(c, cn);
        printf("  child class=%-36s name=%-12s parent=%s\n", cls, cn, pn);
        IOObjectRelease(c);
    }
    IOObjectRelease(it);
}

int main(int argc, char **argv) {
    uint32_t type = argc > 1 ? (uint32_t)strtoul(argv[1], NULL, 0) : 1;
    printf("== before open ==\n");
    for (size_t i = 0; i < sizeof(kClientClasses)/sizeof(kClientClasses[0]); i++) dumpChildren(kClientClasses[i]);

    io_connect_t conn = MACH_PORT_NULL;
    io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("ANEDriver"));
    if (!svc) { printf("no ANEDriver\n"); return 1; }
    kern_return_t kr = IOServiceOpen(svc, mach_task_self(), type, &conn);
    IOObjectRelease(svc);
    printf("IOServiceOpen(type %u) kr=0x%x\n", type, kr);
    if (kr != KERN_SUCCESS) return 1;

    printf("== after open (conn port 0x%x) ==\n", conn);
    for (size_t i = 0; i < sizeof(kClientClasses)/sizeof(kClientClasses[0]); i++) dumpChildren(kClientClasses[i]);

    IOServiceClose(conn);
    usleep(200000);
    printf("== after close ==\n");
    for (size_t i = 0; i < sizeof(kClientClasses)/sizeof(kClientClasses[0]); i++) dumpChildren(kClientClasses[i]);
    return 0;
}
