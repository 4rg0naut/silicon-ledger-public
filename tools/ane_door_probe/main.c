// ane_door_probe — EXP-032 C-69: can a plain user client enumerate/open ANE
// user-client services without root? (host part of the M5 door question)
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <string.h>

static const char *kClasses[] = {
    "AppleVirtIONeuralEngineDevice",
    "ANEDriverRoot",
    "H11ANEIn",
    "ANEScheduler",
    "ANEExclaveProxy",
    "IOReport",
};

static const char *kProps[] = {
    "IOClass", "IOProviderClass", "IONameMatched", "compatible",
    "device_type", "ane-driver-loaded", "allow-ane-dumps",
};

static void dumpProps(io_service_t svc) {
    for (size_t p = 0; p < sizeof(kProps)/sizeof(kProps[0]); p++) {
        CFStringRef key = CFStringCreateWithCString(kCFAllocatorDefault, kProps[p], kCFStringEncodingUTF8);
        CFTypeRef v = IORegistryEntryCreateCFProperty(svc, key, kCFAllocatorDefault, 0);
        CFRelease(key);
        if (!v) continue;
        char buf[512] = {0};
        if (CFGetTypeID(v) == CFStringGetTypeID()) {
            CFStringGetCString((CFStringRef)v, buf, sizeof(buf), kCFStringEncodingUTF8);
        } else if (CFGetTypeID(v) == CFDataGetTypeID()) {
            snprintf(buf, sizeof(buf), "<data %ld bytes>", CFDataGetLength((CFDataRef)v));
        } else if (CFGetTypeID(v) == CFNumberGetTypeID()) {
            long long n = 0; CFNumberGetValue((CFNumberRef)v, kCFNumberSInt64Type, &n);
            snprintf(buf, sizeof(buf), "%lld", n);
        } else {
            snprintf(buf, sizeof(buf), "<type %lu>", CFGetTypeID(v));
        }
        printf("  prop %-20s = %s\n", kProps[p], buf);
        CFRelease(v);
    }
}

int main(void) {
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
            char name[256] = {0};
            io_name_t iname;
            if (IORegistryEntryGetName(svc, iname) == KERN_SUCCESS)
                strlcpy(name, iname, sizeof(name));
            printf("class %-32s instance=%s\n", kClasses[c], name);
            dumpProps(svc);
            io_connect_t conn = MACH_PORT_NULL;
            kr = IOServiceOpen(svc, mach_task_self(), 0, &conn);
            printf("  IOServiceOpen(type 0) kr=0x%x%s\n", kr,
                   kr == KERN_SUCCESS ? " (OPENED)" : (kr == kIOReturnNotPermitted ? " (NOT_PERMITTED)" : (kr == kIOReturnNoDevice ? " (NO_DEVICE)" : "")));
            if (kr == KERN_SUCCESS) {
                IOServiceClose(conn);
                printf("  IOServiceClose ok (connection closed without invoking selectors)\n");
            }
            IOObjectRelease(svc);
        }
        if (!found) printf("class %-32s (no instances)\n", kClasses[c]);
        IOObjectRelease(it);
    }
    return 0;
}
