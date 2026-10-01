// Smoke test for ioreport_shim.c: channels discovered, all readable,
// "CPU Energy" present. Exit code 0 on success.
#include <stdint.h>
#include <stdio.h>
#include <string.h>

int ior_open(void);
int ior_name(int i, char *buf, int len);
int ior_read(int64_t *out, int n);

int main(void) {
    int n = ior_open();
    if (n <= 0) { fprintf(stderr, "FAIL: ior_open returned %d\n", n); return 1; }
    int64_t v[64];
    char name[64];
    int found = 0;
    if (ior_read(v, 64) != n) { fprintf(stderr, "FAIL: ior_read\n"); return 1; }
    for (int i = 0; i < n; i++) {
        if (ior_name(i, name, sizeof name) != 0) { fprintf(stderr, "FAIL: ior_name %d\n", i); return 1; }
        if (v[i] < 0) { fprintf(stderr, "FAIL: channel %s missing\n", name); return 1; }
        if (strcmp(name, "CPU Energy") == 0) found = 1;
        printf("%-12s %lld uJ\n", name, (long long) v[i]);
    }
    if (!found) { fprintf(stderr, "FAIL: no 'CPU Energy' channel\n"); return 1; }
    printf("PASS: %d channels\n", n);
    return 0;
}
