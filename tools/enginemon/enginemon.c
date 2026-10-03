// enginemon — per-engine (CPU / GPU / ANE) activity on Apple Silicon, WITHOUT root.
//
// WHY THIS EXISTS
//   `powermetrics` needs sudo, and `xctrace`'s `ane-hw-intervals` is blind to Core AI
//   graphs (measured: 0 intervals while a Core ML control in the same session logged
//   1310). Placement therefore needs a third instrument. Apple's IOReport channels are
//   readable by an unprivileged process, so this is it.
//
// WHAT IT READS
//   A single group is not enough. ANE telemetry is spread across:
//     AMC Stats                       ANE DCS RD/WR, ANE NRT AF RD/WR   (bytes moved)
//     Interrupt Statistics (by index) subgroup "ane 0": handler counts/time
//     SoC Stats                       ANE_* triggers                    (24M ticks)
//     PMP                             ANE0 RD/WR/RD+WR                  (events)
//     Energy Model                    ANE / GPU / CPU Energy            (mJ; ANE frozen on M4)
//   Groups are copied and merged into one subscription, then sampled with
//   IOReportCreateSamplesDelta so state channels are handled correctly.
//
// METHOD NOTE — the trap this tool is built to avoid
//   `Energy Model -> ANE` never changes on this M4, not even under a known-ANE Core ML
//   workload. Reporting its zero as "no ANE usage" would be a fabricated negative. So this
//   tool reports *which counters moved*, and a zero is only meaningful for a channel that is
//   known to move — established by running the controls in tools/enginemon/README.md.
//   Use `AMC Stats` (bytes) and the `ane 0` interrupt counts, not `Energy Model -> ANE`.
//
// build: clang -O2 -o enginemon enginemon.c -framework CoreFoundation
// usage: ./enginemon --list
//        ./enginemon --interval 500 --duration 5
//        ./enginemon --interval 500 --duration 25 -- <command> [args...]

#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

typedef CFMutableDictionaryRef (*fn_copy_in_group)(CFStringRef, CFStringRef, uint64_t, uint64_t, uint64_t);
typedef void (*fn_merge)(CFMutableDictionaryRef, CFDictionaryRef, CFTypeRef);
typedef CFDictionaryRef (*fn_create_sub)(void *, CFMutableDictionaryRef, CFMutableDictionaryRef *, uint64_t, CFTypeRef);
typedef CFDictionaryRef (*fn_create_samples)(CFDictionaryRef, CFMutableDictionaryRef, CFTypeRef);
typedef CFDictionaryRef (*fn_create_delta)(CFDictionaryRef, CFDictionaryRef, CFTypeRef);
typedef int64_t (*fn_simple_get)(CFDictionaryRef, int32_t);
typedef CFStringRef (*fn_str)(CFDictionaryRef);
typedef int32_t (*fn_state_count)(CFDictionaryRef);
typedef CFStringRef (*fn_state_name)(CFDictionaryRef, int32_t);
typedef int64_t (*fn_state_res)(CFDictionaryRef, int32_t);

static fn_copy_in_group p_copy_in_group;
static fn_merge p_merge;
static fn_create_sub p_create_sub;
static fn_create_samples p_create_samples;
static fn_create_delta p_create_delta;
static fn_simple_get p_simple_get;
static fn_str p_group, p_subgroup, p_name, p_unit;
static fn_state_count p_state_count;
static fn_state_name p_state_name;
static fn_state_res p_state_res;

// Groups carrying engine telemetry. "Energy Model" gives GPU/CPU power; the rest give
// ANE activity. Merging them into one subscription is what aneperf does, and what
// makes a single sample cover every engine.
static const char *GROUPS[] = {
    "Energy Model",
    "AMC Stats",
    "Interrupt Statistics (by index)",
    "PMP",
    "SoC Stats",
    "GPU Stats",
};

#define MAXCH 4096

typedef struct {
    char group[64], sub[64], name[64], unit[32];
    int64_t total;
    long samples;
} chan_t;

static int unfiltered = 0;
static chan_t chans[MAXCH];
static int nchan = 0;

static void S(CFStringRef s, char *b, size_t n) {
    b[0] = 0;
    if (!s) return;
    if (!CFStringGetCString(s, b, (CFIndex)n, kCFStringEncodingUTF8)) { b[0] = 0; return; }
    // Driver-supplied channel names arrive space-padded; trim so columns line up.
    char *p = b;
    while (*p == ' ' || *p == '\t') p++;
    if (p != b) memmove(b, p, strlen(p) + 1);
    for (size_t i = strlen(b); i > 0 && (b[i - 1] == ' ' || b[i - 1] == '\t'); i--) b[i - 1] = 0;
}

// "ANE" at a word boundary: matches "ANE0"/"dart-ane"/"ANE DCS RD" but not
// "VLane"/"Miscellaneous"/"LanesEng".
static int has_ane(const char *s) {
    for (int i = 0; s[i]; i++)
        if ((s[i] == 'a' || s[i] == 'A') && (s[i + 1] == 'n' || s[i + 1] == 'N') &&
            (s[i + 2] == 'e' || s[i + 2] == 'E')) {
            if (i == 0 || !((s[i - 1] >= 'a' && s[i - 1] <= 'z') || (s[i - 1] >= 'A' && s[i - 1] <= 'Z')))
                return 1;
        }
    return 0;
}

static int relevant(const char *g, const char *sg, const char *nm) {
    // "SoC Stats" ANE_*_TRIG channels are a free-running 24 MHz clock: they advance by
    // exactly (elapsed x 24e6) regardless of load (measured: 5.46 s -> 131110395 ticks).
    // Reporting them would look like activity and mean nothing, so they are excluded.
    if (strstr(nm, "TRIG") || strstr(nm, "TRG")) return 0;
    return has_ane(g) || has_ane(sg) || has_ane(nm) ||
           strstr(nm, "GPU") || strstr(nm, "CPU Energy");
}

static int find(const char *g, const char *sg, const char *nm) {
    for (int i = 0; i < nchan; i++)
        if (!strcmp(chans[i].group, g) && !strcmp(chans[i].sub, sg) && !strcmp(chans[i].name, nm))
            return i;
    return -1;
}

static CFArrayRef channels_of(CFDictionaryRef d) {
    CFTypeRef r = CFDictionaryGetValue(d, CFSTR("IOReportChannels"));
    return (r && CFGetTypeID(r) == CFArrayGetTypeID()) ? (CFArrayRef) r : NULL;
}

// Accumulate one delta sample into the table.
static void absorb(CFArrayRef arr) {
    if (!arr) return;
    CFIndex m = CFArrayGetCount(arr);
    for (CFIndex i = 0; i < m; i++) {
        CFDictionaryRef c = (CFDictionaryRef) CFArrayGetValueAtIndex(arr, i);
        if (!c || CFGetTypeID(c) != CFDictionaryGetTypeID()) continue;
        char g[64], sg[64], nm[64], u[32];
        S(p_group(c), g, sizeof g);
        S(p_subgroup ? p_subgroup(c) : NULL, sg, sizeof sg);
        S(p_name(c), nm, sizeof nm);
        S(p_unit ? p_unit(c) : NULL, u, sizeof u);
        if (!unfiltered && !relevant(g, sg, nm)) continue;

        int64_t v = 0;
        int32_t ns = p_state_count ? p_state_count(c) : 0;
        if (ns > 0) {
            for (int32_t j = 0; j < ns; j++) v += p_state_res(c, j);   // residency sum
        } else {
            v = p_simple_get(c, 0);
        }

        int idx = find(g, sg, nm);
        if (idx < 0) {
            if (nchan >= MAXCH) continue;
            idx = nchan++;
            memset(&chans[idx], 0, sizeof chans[idx]);
            snprintf(chans[idx].group, sizeof chans[idx].group, "%s", g);
            snprintf(chans[idx].sub, sizeof chans[idx].sub, "%s", sg);
            snprintf(chans[idx].name, sizeof chans[idx].name, "%s", nm);
            snprintf(chans[idx].unit, sizeof chans[idx].unit, "%s", u);
        }
        if (v > 0) chans[idx].total += v;
        chans[idx].samples++;
    }
}

// Sum the window delta of every channel whose name contains `needle`.
static int64_t sum_matching(const char *needle) {
    int64_t t = 0;
    for (int i = 0; i < nchan; i++)
        if (strstr(chans[i].name, needle)) t += chans[i].total;
    return t;
}

static double energy_to_mw(double delta, const char *unit, double seconds) {
    if (seconds <= 0) return 0;
    double mj;
    if (!strcmp(unit, "nJ"))      mj = delta / 1e6;
    else if (!strcmp(unit, "uJ")) mj = delta / 1e3;
    else if (!strcmp(unit, "J"))  mj = delta * 1e3;
    else                          mj = delta;
    return mj / seconds;
}

int main(int argc, char **argv) {
    int interval_ms = 500;
    double duration = 5.0;
    int list_only = 0, show_all = 0;
    char *cmd = NULL;
    char **cmd_argv = NULL;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--list")) list_only = 1;
        else if (!strcmp(argv[i], "--all")) show_all = 1;
        else if (!strcmp(argv[i], "--unfiltered")) unfiltered = 1;
        else if (!strcmp(argv[i], "--interval") && i + 1 < argc) interval_ms = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--duration") && i + 1 < argc) duration = atof(argv[++i]);
        else if (!strcmp(argv[i], "--")) { if (i + 1 < argc) { cmd = argv[i + 1]; cmd_argv = &argv[i + 1]; } break; }
        else { fprintf(stderr, "unknown arg: %s\n", argv[i]); return 2; }
    }

    void *h = dlopen("/usr/lib/libIOReport.dylib", RTLD_NOW);
    if (!h) h = dlopen("libIOReport.dylib", RTLD_NOW);
    if (!h) { fprintf(stderr, "cannot dlopen libIOReport: %s\n", dlerror()); return 1; }
    p_copy_in_group  = (fn_copy_in_group) dlsym(h, "IOReportCopyChannelsInGroup");
    p_merge          = (fn_merge)         dlsym(h, "IOReportMergeChannels");
    p_create_sub     = (fn_create_sub)    dlsym(h, "IOReportCreateSubscription");
    p_create_samples = (fn_create_samples)dlsym(h, "IOReportCreateSamples");
    p_create_delta   = (fn_create_delta)  dlsym(h, "IOReportCreateSamplesDelta");
    p_simple_get     = (fn_simple_get)    dlsym(h, "IOReportSimpleGetIntegerValue");
    p_group          = (fn_str)           dlsym(h, "IOReportChannelGetGroup");
    p_subgroup       = (fn_str)           dlsym(h, "IOReportChannelGetSubGroup");
    p_name           = (fn_str)           dlsym(h, "IOReportChannelGetChannelName");
    p_unit           = (fn_str)           dlsym(h, "IOReportChannelGetUnitLabel");
    p_state_count    = (fn_state_count)   dlsym(h, "IOReportStateGetCount");
    p_state_name     = (fn_state_name)    dlsym(h, "IOReportStateGetNameForIndex");
    p_state_res      = (fn_state_res)     dlsym(h, "IOReportStateGetResidency");

    if (!p_copy_in_group || !p_create_sub || !p_create_samples || !p_create_delta ||
        !p_simple_get || !p_group || !p_name) {
        fprintf(stderr, "IOReport symbols missing\n");
        return 1;
    }

    // Merge every telemetry group into one channel set.
    CFMutableDictionaryRef merged = NULL;
    for (size_t i = 0; i < sizeof(GROUPS) / sizeof(GROUPS[0]); i++) {
        CFStringRef g = CFStringCreateWithCString(NULL, GROUPS[i], kCFStringEncodingUTF8);
        CFMutableDictionaryRef ch = p_copy_in_group(g, NULL, 0, 0, 0);
        CFRelease(g);
        if (!ch) continue;
        if (!merged) merged = ch;
        else if (p_merge) { p_merge(merged, ch, NULL); CFRelease(ch); }
        else CFRelease(ch);
    }
    if (!merged) { fprintf(stderr, "no IOReport channels available (privileged?)\n"); return 1; }

    CFMutableDictionaryRef subbed = NULL;
    CFDictionaryRef sub = p_create_sub(NULL, merged, &subbed, 0, NULL);
    if (!sub) { fprintf(stderr, "IOReportCreateSubscription failed (privileged?)\n"); return 1; }

    if (list_only) {
        CFArrayRef a = channels_of(p_create_samples(sub, subbed, NULL));
        printf("%-32s %-24s %-26s %s\n", "group", "subgroup", "channel", "unit");
        for (CFIndex i = 0; a && i < CFArrayGetCount(a); i++) {
            CFDictionaryRef c = (CFDictionaryRef) CFArrayGetValueAtIndex(a, i);
            char g[64], sg[64], nm[64], u[32];
            S(p_group(c), g, sizeof g); S(p_subgroup ? p_subgroup(c) : NULL, sg, sizeof sg);
            S(p_name(c), nm, sizeof nm); S(p_unit ? p_unit(c) : NULL, u, sizeof u);
            if (unfiltered || relevant(g, sg, nm)) printf("%-32s %-24s %-26s %s\n", g, sg, nm, u);
        }
        return 0;
    }

    pid_t child = 0;
    if (cmd) {
        child = fork();
        if (child == 0) { execvp(cmd, cmd_argv); fprintf(stderr, "exec %s: %s\n", cmd, strerror(errno)); _exit(127); }
    }

    printf("enginemon: euid=%d interval=%dms duration=%.1fs%s%s\n",
           geteuid(), interval_ms, duration, cmd ? " workload=" : "", cmd ? cmd : "");
    {   // unified identity schema — same keys as bench/identity.py
        char chip[64] = "unknown", model[64] = "unknown", build[64] = "unknown", osver[32] = "unknown";
        size_t sz;
        sz = sizeof(chip);  if (sysctlbyname("machdep.cpu.brand_string", chip, &sz, NULL, 0)) snprintf(chip, sizeof(chip), "unknown");
        sz = sizeof(model); if (sysctlbyname("hw.model", model, &sz, NULL, 0)) snprintf(model, sizeof(model), "unknown");
        sz = sizeof(osver); if (sysctlbyname("kern.osproductversion", osver, &sz, NULL, 0)) snprintf(osver, sizeof(osver), "unknown");
        sz = sizeof(build); if (sysctlbyname("kern.osversion", build, &sz, NULL, 0)) snprintf(build, sizeof(build), "unknown");
        unsigned ncpu = 0; sz = sizeof(ncpu);
        if (sysctlbyname("hw.physicalcpu", &ncpu, &sz, NULL, 0)) ncpu = 0;
        char archbuf[32] = "unknown";
        sz = sizeof(archbuf);
        if (sysctlbyname("hw.machine", archbuf, &sz, NULL, 0)) snprintf(archbuf, sizeof(archbuf), "unknown");
        printf("enginemon: identity chip=%s hw_model=%s cores=%u arch=%s os=%s os_build=%s\n\n",
               chip, model, ncpu, archbuf, osver, build);
    }

    struct timespec t0, now;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    CFDictionaryRef prev = p_create_samples(sub, subbed, NULL);
    for (;;) {
        usleep((useconds_t) interval_ms * 1000);
        CFDictionaryRef cur = p_create_samples(sub, subbed, NULL);
        if (prev && cur) {
            CFDictionaryRef d = p_create_delta(prev, cur, NULL);
            if (d) { absorb(channels_of(d)); CFRelease(d); }
            CFRelease(prev);
        }
        prev = cur;
        clock_gettime(CLOCK_MONOTONIC, &now);
        double el = (now.tv_sec - t0.tv_sec) + (now.tv_nsec - t0.tv_nsec) / 1e9;
        if (el >= duration) break;
        if (child && waitpid(child, NULL, WNOHANG) == child) { child = 0; break; }
    }
    if (child) { int st; waitpid(child, &st, 0); }
    clock_gettime(CLOCK_MONOTONIC, &now);
    double elapsed = (now.tv_sec - t0.tv_sec) + (now.tv_nsec - t0.tv_nsec) / 1e9;

    printf("%-30s %-20s %14s %10s\n", "channel", "group", "delta", "unit");
    printf("%-30s %-20s %14s %10s\n", "------------------------------", "--------------------",
           "--------------", "----------");
    for (int i = 0; i < nchan; i++) {
        if (!show_all && chans[i].total == 0) continue;
        printf("%-30s %-20s %14lld %10s\n", chans[i].name, chans[i].group,
               (long long) chans[i].total, chans[i].unit);
    }
    if (!show_all) {
        int zero = 0;
        for (int i = 0; i < nchan; i++) if (chans[i].total == 0) zero++;
        printf("\n(%d channels tracked, %d showed no movement -- use --all to list them)\n", nchan, zero);
    }

    // Energy channels are cumulative; convert their window delta to mean power.
    printf("\nSUMMARY (over %.2fs)\n", elapsed);
    for (int i = 0; i < nchan; i++) {
        if (strcmp(chans[i].unit, "mJ") && strcmp(chans[i].unit, "nJ") && strcmp(chans[i].unit, "uJ"))
            continue;
        if (strcmp(chans[i].name, "GPU Energy") && strcmp(chans[i].name, "CPU Energy") &&
            strcmp(chans[i].name, "ANE"))
            continue;
        printf("  %-14s %10.1f mW%s\n", chans[i].name,
               energy_to_mw((double) chans[i].total, chans[i].unit, elapsed),
               !strcmp(chans[i].name, "ANE") && chans[i].total == 0
                   ? "   (this channel is frozen on M4 -- use AMC/interrupt counters, not this)" : "");
    }
    printf("  %-14s %10lld B moved, %lld interrupts\n", "ANE activity",
           (long long) sum_matching("ANE DCS RD"), (long long) sum_matching("Handler Count"));
    printf("\nelapsed %.2fs\n", elapsed);
    return 0;
}
