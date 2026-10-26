// ane_hold — open ANEDriverRoot(type N) and hold for argv[2] seconds so an
// external ioreg snapshot can capture the server-side client object.
#include <IOKit/IOKitLib.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char **argv) {
    uint32_t type = argc > 1 ? (uint32_t)strtoul(argv[1], NULL, 0) : 1;
    int secs = argc > 2 ? atoi(argv[2]) : 5;
    io_connect_t conn = MACH_PORT_NULL;
    io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("ANEDriver"));
    if (!svc) { printf("no ANEDriver\n"); return 1; }
    kern_return_t kr = IOServiceOpen(svc, mach_task_self(), type, &conn);
    IOObjectRelease(svc);
    printf("open(type %u) kr=0x%x conn=0x%x holding %ds\n", type, kr, conn, secs);
    if (kr != KERN_SUCCESS) return 1;
    sleep(secs);
    IOServiceClose(conn);
    printf("closed\n");
    return 0;
}
