// EXP-034 C-79 door decode probe: DeviceProperties read + sel-0 field key + 0x68 refutation arm.
// Unprivileged, unsandboxed; zero-residue protocol per EXP-033.
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static void plist_to_xml(CFPropertyListRef p) {
    if (!p) { printf("(null)\n"); return; }
    CFErrorRef err = NULL;
    CFDataRef xml = CFPropertyListCreateXMLData(kCFAllocatorDefault, p);
    if (xml) { fwrite(CFDataGetBytePtr(xml), 1, CFDataGetLength(xml), stdout); CFRelease(xml); }
    else { printf("(xml conversion failed)\n"); }
    if (err) CFRelease(err);
}

static void hexdump(const char *tag, const unsigned char *p, size_t n) {
    printf("%s:", tag);
    for (size_t j = 0; j < n; j++) { if (j % 16 == 0) printf("\n  %04zx:", j); printf(" %02x", p[j]); }
    printf("\n");
}

int main(int argc, char **argv) {
    const char *class = argc > 1 ? argv[1] : "ANEDriver";
    io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching(class));
    if (!svc) { printf("no service for %s\n", class); return 2; }
    char name[256] = {0};
    IORegistryEntryGetName(svc, name);
    printf("service: %s instance=%s\n", class, name);

    // 1. registry property reads (framework's getANEDeviceProperties pattern + full tree)
    printf("--- DeviceProperties ---\n");
    CFTypeRef dp = IORegistryEntryCreateCFProperty(svc, CFSTR("DeviceProperties"), kCFAllocatorDefault, 0);
    plist_to_xml(dp);
    if (dp) CFRelease(dp);
    printf("--- full properties tree ---\n");
    CFMutableDictionaryRef props = NULL;
    kern_return_t pk = IORegistryEntryCreateCFProperties(svc, &props, kCFAllocatorDefault, 0);
    printf("props kr=0x%x\n", pk);
    if (props) { plist_to_xml(props); CFRelease(props); }

    // 2. open type 1, sel-0 field key (136/136) and mdaiter 0x68 arm (104/104)
    io_connect_t conn = 0;
    kern_return_t kr = IOServiceOpen(svc, mach_task_self(), 1, &conn);
    printf("open type 1 kr=0x%x\n", kr);
    if (kr == KERN_SUCCESS) {
        unsigned char in136[136] = {0}, out136[136] = {0};
        size_t osz = 136;
        kr = IOConnectCallStructMethod(conn, 0, in136, 136, out136, &osz);
        printf("sel0 136/136 kr=0x%x oSz_back=%zu\n", kr, osz);
        hexdump("  out136", out136, osz);

        unsigned char in104[104] = {0}, out104[104] = {0};
        size_t osz2 = 104;
        kr = IOConnectCallStructMethod(conn, 0, in104, 104, out104, &osz2);
        printf("sel0 0x68/0x68 (mdaiter arm) kr=0x%x oSz_back=%zu\n", kr, osz2);
        hexdump("  out104", out104, osz2 > 104 ? 104 : osz2);

        // scalar-out flavor matching their IOConnectCallStructMethod-with-no-scalars exactly is above;
        // also probe with deviceType-ish scalars set in struct per their note (0x1c, 0x4c)
        unsigned char in104b[104] = {0};
        memset(in104b + 0x18, 0xff, 4); // int32 -1 default-init value
        size_t osz3 = 104;
        kr = IOConnectCallStructMethod(conn, 0, in104b, 104, out104, &osz3);
        printf("sel0 0x68 (int32@0x18=-1) kr=0x%x oSz_back=%zu\n", kr, osz3);
        IOServiceClose(conn);
    }
    IOObjectRelease(svc);
    printf("done\n");
    return 0;
}
