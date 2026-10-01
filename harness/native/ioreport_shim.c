// Flat C ABI over Apple's private IOReport API for the JMH energy profiler.
//
// Exposes the "Energy Model" channel group as cumulative counters in
// microjoules, without blocks or CoreFoundation types, so Java's FFM API can
// call it directly. On macOS 27 the counters only advance while a privileged
// sampler (powermetrics) is running; see IoReportReader.
#include <CoreFoundation/CoreFoundation.h>
#include <stdint.h>
#include <string.h>

typedef struct IOReportSubscription *IOReportSubscriptionRef;
extern CFMutableDictionaryRef IOReportCopyChannelsInGroup(CFStringRef, CFStringRef, uint64_t, uint64_t, uint64_t);
extern IOReportSubscriptionRef IOReportCreateSubscription(void *, CFMutableDictionaryRef, CFMutableDictionaryRef *, uint64_t, CFTypeRef);
extern CFDictionaryRef IOReportCreateSamples(IOReportSubscriptionRef, CFMutableDictionaryRef, CFTypeRef);
extern CFStringRef IOReportChannelGetChannelName(CFDictionaryRef);
extern CFStringRef IOReportChannelGetUnitLabel(CFDictionaryRef);
extern int64_t IOReportSimpleGetIntegerValue(CFDictionaryRef, int32_t);
extern void IOReportIterate(CFDictionaryRef, int (^)(CFDictionaryRef));

#define MAX_CH 64
#define NAME_LEN 64

static IOReportSubscriptionRef sub;
static CFMutableDictionaryRef subbed;
static char names[MAX_CH][NAME_LEN];
static int64_t scale_num[MAX_CH], scale_den[MAX_CH];  // raw * num / den = microjoules
static int count = -1;

// Per-DVFS-state (DTL), SRAM and PCIe sub-channels duplicate the cluster and
// core totals and would bloat the JMH output, so they are not exposed.
static int keep(const char *name) {
    return strstr(name, "DTL") == NULL && strstr(name, "SRAM") == NULL
        && strstr(name, "PCIe") == NULL && strstr(name, "apciec") == NULL;
}

static int unit_scale(const char *unit, int64_t *num, int64_t *den) {
    if (strcmp(unit, "mJ") == 0) { *num = 1000; *den = 1;    return 0; }
    if (strcmp(unit, "uJ") == 0) { *num = 1;    *den = 1;    return 0; }
    if (strcmp(unit, "nJ") == 0) { *num = 1;    *den = 1000; return 0; }
    return -1;
}

static void cstr(CFStringRef s, char *buf, int len) {
    buf[0] = '\0';
    if (s) CFStringGetCString(s, buf, len, kCFStringEncodingUTF8);
}

int ior_open(void) {
    if (count >= 0) return count;
    CFMutableDictionaryRef chans = IOReportCopyChannelsInGroup(CFSTR("Energy Model"), NULL, 0, 0, 0);
    if (!chans) return -1;
    sub = IOReportCreateSubscription(NULL, chans, &subbed, 0, NULL);
    if (!sub) return -2;
    CFDictionaryRef s = IOReportCreateSamples(sub, subbed, NULL);
    if (!s) return -3;
    __block int n = 0;
    IOReportIterate(s, ^int(CFDictionaryRef ch) {
        char name[NAME_LEN], unit[16];
        cstr(IOReportChannelGetChannelName(ch), name, NAME_LEN);
        cstr(IOReportChannelGetUnitLabel(ch), unit, sizeof unit);
        if (n < MAX_CH && keep(name) && unit_scale(unit, &scale_num[n], &scale_den[n]) == 0) {
            strncpy(names[n], name, NAME_LEN - 1);
            names[n][NAME_LEN - 1] = '\0';
            n++;
        }
        return 0;
    });
    CFRelease(s);
    count = n;
    return count;
}

int ior_name(int i, char *buf, int len) {
    if (i < 0 || i >= count || len <= 0) return -1;
    strncpy(buf, names[i], (size_t) len - 1);
    buf[len - 1] = '\0';
    return 0;
}

// Fills out[0..count) with cumulative microjoules; a channel absent from the
// sample is reported as -1. Returns count, or -1 on error.
int ior_read(int64_t *out, int n) {
    if (count < 0 || n < count) return -1;
    CFDictionaryRef s = IOReportCreateSamples(sub, subbed, NULL);
    if (!s) return -1;
    for (int i = 0; i < count; i++) out[i] = -1;
    IOReportIterate(s, ^int(CFDictionaryRef ch) {
        char name[NAME_LEN];
        cstr(IOReportChannelGetChannelName(ch), name, NAME_LEN);
        for (int i = 0; i < count; i++) {
            if (out[i] < 0 && strcmp(names[i], name) == 0) {
                out[i] = IOReportSimpleGetIntegerValue(ch, 0) * scale_num[i] / scale_den[i];
                break;
            }
        }
        return 0;
    });
    CFRelease(s);
    return count;
}
