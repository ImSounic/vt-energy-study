# Assignment 2: Experiment Plan (Mac-primary) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** By **Fri 2 Oct 2026, 23:59**, submit the Assignment 2 report: a 5–7 page ACM experiment plan that refines the A1 proposal. It must be backed by a working energy-measurement pipeline on the Mac mini M4 and a short Mac feasibility pilot. The Intel arm is to be reported later.

**Architecture:** The Intel laptop is broken, so the Mac mini M4 becomes the primary platform and the Intel Core Ultra 7 255H becomes a conditional second arm. The JMH harness gains a platform-neutral `EnergyProfiler`. It reads cumulative energy counters at iteration boundaries: RAPL via sysfs on Linux, and Apple IOReport via a C shim called through the FFM API on macOS. On macOS 27, the IOReport counters are only published while a root `powermetrics` process samples. The scripts therefore keep `powermetrics` running at 100 ms purely as a refresher, which bounds each read's staleness to 100 ms. The report is the existing `paper/main.tex`, restructured to the A2 brief and built with tectonic.

**Tech Stack:**
- Java 25 (Homebrew `openjdk@25` 25.0.4.1), JMH 1.37, Maven 3.9.16.
- C (Apple clang 21) for the IOReport shim; `powermetrics`.
- Python 3.14, standard library only for the pilot summary.
- LaTeX `acmart`, built with `tectonic` (XeTeX).

---

## Ground truth established on 1 Oct 2026 (do not re-derive)

- **Mac:** Mac mini M4 (`Mac16,10`), 4 P + 6 E cores, 16 GB, on AC power, macOS 27.0 (26A428).
  - Maximum frequencies observed by `powermetrics`: P cluster 4464 MHz, E cluster 2892 MHz.
- **Toolchain:**
  - `JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home`. Maven also pulled in openjdk 27, so **always export this JAVA_HOME**.
  - `tectonic` builds the paper (A1 builds to 4 pages). XeTeX's Libertine has no `✓` glyph, so the related-work table needs `\ding{51}`.
- **IOReport ("Energy Model" group, no sudo needed to read):**
  - Channels are cumulative counters in mJ, uJ or nJ.
  - Available channels: `ECPU`, `PCPU`, `CPU Energy` (= ECPU + PCPU), `ECPU0–5`, `PCPU0–3`, `ECPM`, `PCPM`, `GPU`, `GPU Energy`, `ANE`, `ISP`, `AVE`, `MSR`, `AMCC`, `DCS`, `DRAM`, `DISP`, `DISPEXT`, `VDEC`, `SOC_AON` and `SOC_REST`.
  - There are also per-DVFS-state `*DTL*` and `*SRAM*` sub-channels.
- **The counters are frozen unless `powermetrics` runs.** Measured with `refresh.sh` on 1 Oct:

  | `powermetrics -i` | Updates in 6 s | Max gap between updates |
  |---|---|---|
  | off | 0 | — |
  | 1000 ms | 13 | 1005.6 ms |
  | 250 ms | 47 | 256.8 ms |
  | 100 ms | 111 | 106.0 ms |
  | 50 ms | 208 | 55.9 ms |

  Evidence that a read lags real time: a probe's "1 s burn" delta was 1100 mJ, which matches the *previous* `powermetrics` sample (1077 mW × 1.01 s), not the burn itself (8149 mW).
- **The Intel pilot (10 Sep, `results/pilot/pilot.json`) shows a power regime shift.**
  - Package energy per iteration for PLATFORM_THREADS/CPU, fork 1: 62.0, 62.8, 62.5, 57.7, 63.1, 54.2, 35.8, 25.4, 25.0, 24.9 J.
  - The same configuration, fork 2: 25.3, 27.6, 25.0, 25.1, 26.1, 25.0, 24.9, 25.8, 25.8, 26.5 J. ms/op rose from 89 to 128.
  - VIRTUAL_THREADS/CPU: fork 1 at about 41 W, fork 2 at about 25 W.
  - So the A1 CPU J/op numbers average over two power regimes.
- **Mac quirk:** `Thread.sleep(10)` takes about 12.1 ms on macOS. A FIXED_POOL/IO smoke run took 387 ms against the 320 ms floor.
- **Mac quirk:** JMH text output uses decimal commas (Dutch locale). Always use `-rf json`, and format numbers with `Locale.ROOT`.
- **No wall power meter is available.**

## Design decisions (locked unless Sounic/Vasil override by Thu 1 Oct 20:00)

| # | Decision | Why |
|---|---|---|
| D1 | Mac mini M4 is the primary platform; Intel 255H is a conditional second arm with go/no-go on **16 Oct** | The laptop is broken and A3 needs guaranteed data |
| D2 | JDK 25.0.4.1 on both platforms (the Intel pilot used 26.0.2) | 25 is the current long-term-support release, the version developers deploy |
| D3 | Five constructs: SEQUENTIAL (new), PLATFORM_THREADS (thread-per-task), FIXED_POOL, FORK_JOIN (recursive splitting, new), VIRTUAL_THREADS | Q1.2 needs a sequential arm; Fork/Join should be used as designed |
| D4 | Concurrency level p ∈ {1, 2, 4, 8, 16, 64, 256} (256 = task count, added 1 Oct at the user's request). It means pool size for FIXED_POOL, parallelism for FORK_JOIN and the carrier count for VT (`-Djdk.virtualThreadScheduler.parallelism=p`). SEQUENTIAL and PLATFORM_THREADS take no p | This gives VT a real curve and removes the duplicate cells. On blocking workloads a pool's time has an analytic floor ⌈256/p⌉×d, so the primary VT comparison there is against PT and FP/FJ at p=256 (fact sheet D4b) |
| D5 | Three workloads (experimental units): CPU (Mandelbrot), SLEEP (`Thread.sleep(10)`), SOCKET (loopback TCP, 10 ms server-side delay) | SOCKET addresses the "sleep is not I/O" threat |
| D6 | G3 on the Mac uses the QoS class as its lever: DEFAULT vs BACKGROUND (`taskpolicy -b`, restricted to E cores). On Intel: unpinned vs equal-count 2P/2E/2LP-E | macOS has no CPU affinity; equal counts separate core type from core count |
| D7 | Replication unit = one fork (one fresh JVM run). n = 10 forks per cell, confirmed by the pilot. The value per fork is the median of its 5 measured iterations | Avoids treating iterations as independent samples (Georges et al. 2007) |
| D8 | JMH: 5 × 1 s warmup, 5 × 5 s measurement; `powermetrics` refresh at 100 ms | Worst-case boundary staleness is 100 ms, ≤ 2 % of a 5 s window |
| D9 | Randomised run order at fork level (seeded), a quiet-machine gate before each run, a cooldown of at least 10 s that also waits for nominal thermal pressure, and a 60 s idle baseline per batch | The Intel regime shift shows that order and thermal state confound results |
| D10 | Analysis: non-parametric (Kruskal–Wallis + Dunn/Holm, Mann–Whitney U, Spearman), Cliff's δ, bootstrap CIs, TOST (equivalence test) with a ±5 % margin | Data is non-normal, comparisons are many, and null results need equivalence tests |
| D11 | Profilers: JFR (Java level), `powermetrics` tasks/cpu_power samplers (OS level), `perf stat` (Intel only). All run as passes separate from the energy runs | The brief requires a profiler; profiling must not perturb the energy runs |

## Timeline to the deadline (now: Thu 1 Oct 14:00)

| When | Who | What |
|---|---|---|
| Thu 14:30–17:30 | Claude | Tasks 1–7 (harness + scripts, all tests green) |
| Thu ~17:30 | Sounic | Task 8: quiet the Mac, run the Mac pilot (≈ 20 min) and JFR smoke (≈ 5 min) |
| Thu 18:00–23:00 | Claude | Tasks 9–13: bibliography check and a full report draft |
| Fri 09:00–13:00 | Sounic + Vasil | Review the draft and the decisions; Claude revises |
| **Fri 13:00** | — | **Cutoff:** if Mac pilot numbers are missing or implausible, §5.5 uses the probe/refresh evidence only |
| Fri 13:00–18:00 | Claude + Sounic | Figures/tables final, page fit (5–7 + 1 pages) |
| Fri 18:00 | Sounic + Vasil | Write the contribution footnote; final read |
| Fri 20:00 | Sounic | Submit the PDF on Canvas (about 4 h buffer) |

## Quiet-machine protocol (answers "do open apps matter?")

Yes, they do. IOReport, like RAPL, measures **whole clusters**, not the JVM process, so every other app's CPU work lands in the benchmark's joules. Busy apps also raise the shared cluster frequency and the temperature. On 1 Oct at 14:05 the Mac was 68 % idle (WindowServer 34 %, Vivaldi about 21 %, Discord 13 %, a video decoder). Before **any** energy run:
1. Quit every app except Terminal: browsers, Discord, Claude desktop, Docker, music and video players.
2. Turn on Do Not Disturb. Turn Wi-Fi off; the SOCKET workload uses loopback only.
3. Pause Spotlight indexing: `sudo mdutil -a -i off`. Re-enable it afterwards with `sudo mdutil -a -i on`.
4. Let the display sleep (`pmset displaysleepnow`). The scripts hold the system awake with `caffeinate -i -s`.
5. `scripts/mac/quiet-check.sh 95` must pass (CPU at least 95 % idle over 3 s).

---

## File structure

**Created**
- `harness/native/ioreport_shim.c`: flat C ABI over IOReport, exposing cumulative µJ counters
- `harness/native/shim_smoke.c`: C smoke test for the shim
- `harness/native/build.sh`: builds `libioreport_shim.dylib` and runs the smoke test
- `harness/src/main/java/nl/utwente/gsd/energy/EnergyReader.java`: counter interface plus OS factory
- `harness/src/main/java/nl/utwente/gsd/energy/IoReportReader.java`: FFM binding to the shim
- `harness/src/main/java/nl/utwente/gsd/energy/EnergyProfiler.java`: shared JMH profiler logic
- `harness/src/main/java/nl/utwente/gsd/energy/IoReportProfiler.java`: `-prof` entry point on the Mac
- `harness/src/main/java/nl/utwente/gsd/energy/IdleBaseline.java`: idle power per domain, written as JSON
- `harness/src/test/java/nl/utwente/gsd/energy/{IoReportReaderTest,EnergyProfilerTest,IdleBaselineTest}.java`
- `scripts/mac/{env-manifest,quiet-check,powermetrics-start,powermetrics-stop,pilot-mac}.sh`
- `analysis/summarize_pilot.py`, `analysis/test_summarize_pilot.py`
- `results/pilot-mac/`: pilot output (committed like the Intel pilot)

**Modified**
- `harness/pom.xml`: release 25; native access for tests
- `harness/src/main/java/nl/utwente/gsd/energy/RaplReader.java`: `implements EnergyReader`
- `harness/src/main/java/nl/utwente/gsd/energy/RaplProfiler.java`: becomes a thin `EnergyProfiler` subclass
- `harness/src/main/java/nl/utwente/gsd/ConcurrencyEnergyBenchmark.java`: `--enable-native-access` in `@Fork`
- `harness/src/test/java/nl/utwente/gsd/energy/RaplReaderTest.java`: hardware tests become Linux-only
- `.gitignore`: dylib, smoke binary, `.DS_Store`
- `paper/main.tex`, `paper/refs.bib`: the A2 report

---

# PART A: Before the deadline

### Task 1: Repository hygiene, Java 25 target, Linux-only RAPL tests

**Files:**
- Modify: `vt-energy/.gitignore`
- Modify: `harness/pom.xml` (properties, surefire plugin)
- Modify: `harness/src/test/java/nl/utwente/gsd/energy/RaplReaderTest.java`

- [ ] **Step 1: Stop the Mac copy's permission bits showing as changes, and branch**

```bash
cd "/Users/imsounic/Green Software Development/vt-energy"
git config core.fileMode false
git checkout -b assignment-2
git status --short
```
Expected: only `?? .DS_Store` and `?? docs/` remain (every ` M` disappears).

- [ ] **Step 2: Extend `.gitignore`.** Append:

```gitignore
.DS_Store
harness/native/*.dylib
harness/native/shim_smoke
results/pilot-mac/*.jfr
```

- [ ] **Step 3: Raise the compile target and let tests use FFM.** In `harness/pom.xml`, change `<maven.compiler.release>21</maven.compiler.release>` to `25`, and replace the surefire plugin block with:

```xml
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
        <configuration>
          <argLine>--enable-native-access=ALL-UNNAMED</argLine>
        </configuration>
      </plugin>
```

- [ ] **Step 4: Make the two sysfs tests Linux-only.** In `RaplReaderTest.java`, add these imports:

```java
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;
```
and annotate both hardware tests:

```java
    @Test
    @EnabledOnOs(OS.LINUX)
    void discoversAtLeastOneDomainOnThisMachine() throws Exception {
```
```java
    @Test
    @EnabledOnOs(OS.LINUX)
    void consecutiveReadsAreMonotonicOrWrapped() throws Exception {
```

- [ ] **Step 5: Build and test**

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home
cd harness && mvn -q -B clean package && grep -h "Tests run" target/surefire-reports/*.txt
```
Expected: BUILD SUCCESS. RaplReaderTest shows `Tests run: 6, Failures: 0, Errors: 0, Skipped: 2`.

- [ ] **Step 6: Commit**

```bash
cd .. && git add .gitignore harness/pom.xml harness/src/test/java/nl/utwente/gsd/energy/RaplReaderTest.java docs/superpowers/plans
git commit -m "chore: target Java 25, Linux-only RAPL hardware tests, A2 plan"
```

---

### Task 2: IOReport C shim

**Files:**
- Create: `harness/native/shim_smoke.c`
- Create: `harness/native/ioreport_shim.c`
- Create: `harness/native/build.sh`

- [ ] **Step 1: Write the smoke test first** (`harness/native/shim_smoke.c`)

```c
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
```

- [ ] **Step 2: Write `harness/native/build.sh`**

```bash
#!/usr/bin/env bash
# Builds the IOReport shim used by IoReportReader (macOS only) and runs its
# smoke test. Output: harness/native/libioreport_shim.dylib
set -euo pipefail
cd "$(dirname "$0")"
clang -O2 -Wall -dynamiclib -o libioreport_shim.dylib ioreport_shim.c \
  -framework CoreFoundation -lIOReport
clang -O2 -Wall -o shim_smoke shim_smoke.c ioreport_shim.c \
  -framework CoreFoundation -lIOReport
./shim_smoke
```

- [ ] **Step 3: Run it to verify it fails**

```bash
chmod +x harness/native/build.sh && harness/native/build.sh
```
Expected: clang error `no such file or directory: 'ioreport_shim.c'`.

- [ ] **Step 4: Write `harness/native/ioreport_shim.c`**

```c
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
```

- [ ] **Step 5: Build and run the smoke test**

```bash
harness/native/build.sh
```
Expected: one line per channel (including `CPU Energy`, `ECPU`, `PCPU`, `DRAM`, `GPU Energy`), then `PASS: <n> channels` with n of about 30 and exit code 0.

- [ ] **Step 6: Commit**

```bash
git add harness/native/ioreport_shim.c harness/native/shim_smoke.c harness/native/build.sh
git commit -m "feat: IOReport C shim exposing Apple energy counters in microjoules"
```

---

### Task 3: `EnergyReader` interface and `IoReportReader` (FFM)

**Files:**
- Create: `harness/src/main/java/nl/utwente/gsd/energy/EnergyReader.java`
- Modify: `harness/src/main/java/nl/utwente/gsd/energy/RaplReader.java:18`
- Create: `harness/src/main/java/nl/utwente/gsd/energy/IoReportReader.java`
- Test: `harness/src/test/java/nl/utwente/gsd/energy/IoReportReaderTest.java`

- [ ] **Step 1: Write the failing test** (`IoReportReaderTest.java`)

```java
package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class IoReportReaderTest {

    @Test
    void deltaIsDifferenceOfCumulativeValues() {
        assertEquals(1_100_000L, IoReportReader.delta(17_262_809_000L, 17_263_909_000L));
    }

    @Test
    void deltaRejectsCounterGoingBackwards() {
        assertThrows(IllegalStateException.class, () -> IoReportReader.delta(10L, 5L));
    }

    @Test
    @EnabledOnOs(OS.MAC)
    void discoversCpuClusterChannels() throws Exception {
        Map<String, Long> readings = new IoReportReader().readAll();
        assertTrue(readings.containsKey("CPU_Energy"), "channels: " + readings.keySet());
        assertTrue(readings.containsKey("ECPU"));
        assertTrue(readings.containsKey("PCPU"));
        readings.values().forEach(v -> assertTrue(v >= 0));
    }

    @Test
    @EnabledOnOs(OS.MAC)
    void cpuEnergyAdvancesWhilePowermetricsRefreshes() throws Exception {
        assumeTrue(powermetricsRunning(),
                "needs 'sudo powermetrics' running; counters are frozen otherwise");
        IoReportReader reader = new IoReportReader();
        long before = reader.readAll().get("CPU_Energy");
        long sink = 0;
        long until = System.nanoTime() + 1_500_000_000L;
        while (System.nanoTime() < until) sink += sink * 31 + 7;
        assertTrue(sink != 42);
        long after = reader.readAll().get("CPU_Energy");
        assertTrue(reader.deltaFor("CPU_Energy", before, after) > 0);
    }

    private static boolean powermetricsRunning() throws Exception {
        return new ProcessBuilder("pgrep", "-x", "powermetrics").start().waitFor() == 0;
    }
}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd harness && mvn -q -B test -Dtest=IoReportReaderTest
```
Expected: compilation failure, `cannot find symbol: class IoReportReader`.

- [ ] **Step 3: Create `EnergyReader.java`**

```java
package nl.utwente.gsd.energy;

import java.io.IOException;
import java.util.Map;

/** Cumulative energy counters, read on demand. All values are microjoules. */
public interface EnergyReader {

    /** Reads every discovered counter. */
    Map<String, Long> readAll() throws IOException;

    /** Energy consumed between two readings of one counter, in microjoules. */
    long deltaFor(String domain, long start, long end);

    /** RAPL on Linux, IOReport on macOS. */
    static EnergyReader forThisMachine() throws IOException {
        String os = System.getProperty("os.name").toLowerCase();
        if (os.contains("mac")) return new IoReportReader();
        if (os.contains("linux")) return new RaplReader();
        throw new IOException("no energy reader for OS: " + os);
    }
}
```

- [ ] **Step 4: Make `RaplReader` implement it.** In `RaplReader.java`, change line 18 from `public final class RaplReader {` to:

```java
public final class RaplReader implements EnergyReader {
```
(The `readAll()` and `deltaFor(String, long, long)` signatures already match.)

- [ ] **Step 5: Create `IoReportReader.java`**

```java
package nl.utwente.gsd.energy;

import java.io.IOException;
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Reads Apple Silicon energy counters (IOReport "Energy Model" group) through
 * the native shim in harness/native, called via the FFM API.
 *
 * <p>Counters are read on demand only, at iteration boundaries. On macOS 27
 * they are published only while a privileged sampler (powermetrics) runs, so
 * each reading lags real time by at most one powermetrics interval; the
 * experiment scripts keep powermetrics running at 100 ms.
 */
public final class IoReportReader implements EnergyReader {

    static final String LIB_PROPERTY = "vt.ioreport.lib";
    private static final String LIB_FILE = "libioreport_shim.dylib";

    private final MethodHandle read;
    private final List<String> names = new ArrayList<>();
    private final MemorySegment buffer;

    public IoReportReader() throws IOException {
        Path lib = locateLibrary();
        Linker linker = Linker.nativeLinker();
        SymbolLookup symbols = SymbolLookup.libraryLookup(lib, Arena.global());
        MethodHandle open = linker.downcallHandle(symbols.find("ior_open").orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT));
        MethodHandle name = linker.downcallHandle(symbols.find("ior_name").orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT, ValueLayout.ADDRESS, ValueLayout.JAVA_INT));
        this.read = linker.downcallHandle(symbols.find("ior_read").orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS, ValueLayout.JAVA_INT));
        try {
            int n = (int) open.invokeExact();
            if (n <= 0) throw new IOException("IOReport shim found no energy channels (code " + n + ")");
            try (Arena arena = Arena.ofConfined()) {
                MemorySegment buf = arena.allocate(64);
                for (int i = 0; i < n; i++) {
                    int rc = (int) name.invokeExact(i, buf, 64);
                    if (rc != 0) throw new IOException("ior_name failed for channel " + i);
                    names.add(uniqueKey(buf.getString(0).replace(' ', '_')));
                }
            }
        } catch (IOException e) {
            throw e;
        } catch (Throwable t) {
            throw new IOException("IOReport shim call failed", t);
        }
        this.buffer = Arena.global().allocate(ValueLayout.JAVA_LONG, names.size());
    }

    private String uniqueKey(String base) {
        String key = base;
        for (int i = 2; names.contains(key); i++) key = base + "#" + i;
        return key;
    }

    @Override
    public Map<String, Long> readAll() throws IOException {
        int got;
        try {
            got = (int) read.invokeExact(buffer, names.size());
        } catch (Throwable t) {
            throw new IOException("ior_read failed", t);
        }
        if (got != names.size()) throw new IOException("ior_read returned " + got);
        Map<String, Long> out = new LinkedHashMap<>();
        for (int i = 0; i < names.size(); i++) {
            long v = buffer.getAtIndex(ValueLayout.JAVA_LONG, i);
            if (v < 0) throw new IOException("channel missing from sample: " + names.get(i));
            out.put(names.get(i), v);
        }
        return out;
    }

    @Override
    public long deltaFor(String domain, long start, long end) {
        if (!names.contains(domain)) throw new IllegalArgumentException("unknown channel: " + domain);
        return delta(start, end);
    }

    /** 64-bit cumulative counters do not wrap in practice; a decrease means a reset. */
    static long delta(long start, long end) {
        if (end < start) {
            throw new IllegalStateException("IOReport counter went backwards: " + start + " -> " + end);
        }
        return end - start;
    }

    /** -Dvt.ioreport.lib if set, else the nearest native/ dir above the jar or classes dir. */
    static Path locateLibrary() throws IOException {
        String explicit = System.getProperty(LIB_PROPERTY);
        if (explicit != null) {
            Path p = Path.of(explicit);
            if (!Files.isRegularFile(p)) throw new IOException("not a file: " + p);
            return p;
        }
        try {
            Path here = Path.of(IoReportReader.class.getProtectionDomain().getCodeSource().getLocation().toURI());
            for (Path dir = here; dir != null; dir = dir.getParent()) {
                Path candidate = dir.resolve("native").resolve(LIB_FILE);
                if (Files.isRegularFile(candidate)) return candidate;
            }
        } catch (URISyntaxException | SecurityException e) {
            // fall through to the error below
        }
        throw new IOException(LIB_FILE + " not found; run harness/native/build.sh or set -D" + LIB_PROPERTY);
    }
}
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
mvn -q -B test -Dtest=IoReportReaderTest
```
Expected: 4 tests run. `cpuEnergyAdvancesWhilePowermetricsRefreshes` is **skipped** (assumption), unless `sudo powermetrics` is running in another terminal; then all 4 pass.

- [ ] **Step 7: Commit**

```bash
cd .. && git add harness/src
git commit -m "feat: IoReportReader reading Apple energy counters via FFM"
```

---

### Task 4: Shared `EnergyProfiler`; `RaplProfiler` and `IoReportProfiler` become thin subclasses

**Files:**
- Create: `harness/src/main/java/nl/utwente/gsd/energy/EnergyProfiler.java`
- Modify (replace whole file): `harness/src/main/java/nl/utwente/gsd/energy/RaplProfiler.java`
- Create: `harness/src/main/java/nl/utwente/gsd/energy/IoReportProfiler.java`
- Modify: `harness/src/main/java/nl/utwente/gsd/ConcurrencyEnergyBenchmark.java:23`
- Test: `harness/src/test/java/nl/utwente/gsd/energy/EnergyProfilerTest.java`

- [ ] **Step 1: Write the failing test** (`EnergyProfilerTest.java`)

```java
package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;
import org.openjdk.jmh.results.Result;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class EnergyProfilerTest {

    /** Fake reader: deltas are plain differences. */
    private static final EnergyReader FAKE = new EnergyReader() {
        @Override public Map<String, Long> readAll() { return Map.of(); }
        @Override public long deltaFor(String domain, long start, long end) { return end - start; }
    };

    private static double score(List<Result> results, String label) {
        return results.stream().filter(r -> r.getLabel().equals(label)).findFirst()
                .orElseThrow(() -> new AssertionError("missing " + label)).getScore();
    }

    @Test
    void reportsJoulesJoulesPerOpAndWindow() {
        Map<String, Long> start = new LinkedHashMap<>(Map.of("CPU_Energy", 1_000_000L));
        Map<String, Long> end = Map.of("CPU_Energy", 9_000_000L);
        List<Result> r = EnergyProfiler.results("ioreport", FAKE, start, end, 4, 5.0);
        assertEquals(8.0, score(r, "ioreport.CPU_Energy.J"), 1e-9);
        assertEquals(2.0, score(r, "ioreport.CPU_Energy.J_per_op"), 1e-9);
        assertEquals(5.0, score(r, "ioreport.window_s"), 1e-9);
    }

    @Test
    void omitsPerOpMetricWhenNoOpsCompleted() {
        List<Result> r = EnergyProfiler.results("rapl", FAKE,
                Map.of("pkg", 0L), Map.of("pkg", 5_000_000L), 0, 1.0);
        assertTrue(r.stream().noneMatch(x -> x.getLabel().endsWith("J_per_op")));
    }
}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd harness && mvn -q -B test -Dtest=EnergyProfilerTest
```
Expected: compilation failure, `cannot find symbol: class EnergyProfiler`.

- [ ] **Step 3: Create `EnergyProfiler.java`**

```java
package nl.utwente.gsd.energy;

import org.openjdk.jmh.infra.BenchmarkParams;
import org.openjdk.jmh.infra.IterationParams;
import org.openjdk.jmh.profile.InternalProfiler;
import org.openjdk.jmh.results.AggregationPolicy;
import org.openjdk.jmh.results.IterationResult;
import org.openjdk.jmh.results.Result;
import org.openjdk.jmh.results.ScalarResult;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;

/**
 * JMH profiler that attributes energy to each iteration by reading cumulative
 * counters once before and once after it. Counters are never polled during the
 * measured region: high-frequency polling suppresses C-states and inflates
 * idle power (Raffin &amp; Trystram, IEEE TPDS 2025).
 */
public abstract class EnergyProfiler implements InternalProfiler {

    private final EnergyReader reader;
    private final String prefix;
    private Map<String, Long> start;
    private long startNanos;

    protected EnergyProfiler(EnergyReader reader, String prefix) {
        this.reader = reader;
        this.prefix = prefix;
    }

    @Override
    public void beforeIteration(BenchmarkParams bp, IterationParams ip) {
        try {
            start = reader.readAll();
        } catch (IOException e) {
            throw new IllegalStateException("energy read failed at iteration start", e);
        }
        startNanos = System.nanoTime();
    }

    @Override
    public Collection<? extends Result> afterIteration(
            BenchmarkParams bp, IterationParams ip, IterationResult result) {
        long endNanos = System.nanoTime();
        Map<String, Long> end;
        try {
            end = reader.readAll();
        } catch (IOException e) {
            throw new IllegalStateException("energy read failed at iteration end", e);
        }
        return results(prefix, reader, start, end,
                result.getMetadata().getMeasuredOps(), (endNanos - startNanos) / 1e9);
    }

    /** Per-domain J and J/op, plus the length of the energy window in seconds. */
    static List<Result> results(String prefix, EnergyReader reader, Map<String, Long> start,
                                Map<String, Long> end, long ops, double windowSeconds) {
        List<Result> out = new ArrayList<>();
        out.add(new ScalarResult(prefix + ".window_s", windowSeconds, "s", AggregationPolicy.AVG));
        for (Map.Entry<String, Long> e : start.entrySet()) {
            String domain = e.getKey();
            double joules = reader.deltaFor(domain, e.getValue(), end.get(domain)) / 1_000_000.0;
            out.add(new ScalarResult(prefix + "." + domain + ".J", joules, "J", AggregationPolicy.AVG));
            if (ops > 0) {
                out.add(new ScalarResult(prefix + "." + domain + ".J_per_op",
                        joules / ops, "J/op", AggregationPolicy.AVG));
            }
        }
        return out;
    }
}
```

- [ ] **Step 4: Replace `RaplProfiler.java` entirely**

```java
package nl.utwente.gsd.energy;

import org.openjdk.jmh.profile.ProfilerException;

import java.io.IOException;

/**
 * Intel RAPL energy per iteration (Linux powercap sysfs).
 * Register with: -prof nl.utwente.gsd.energy.RaplProfiler
 */
public class RaplProfiler extends EnergyProfiler {

    public RaplProfiler() throws ProfilerException {
        super(open(), "rapl");
    }

    private static RaplReader open() throws ProfilerException {
        try {
            return new RaplReader();
        } catch (IOException e) {
            throw new ProfilerException(
                "Cannot initialise RAPL: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    @Override
    public String getDescription() {
        return "Intel RAPL energy per iteration (powercap sysfs)";
    }
}
```

- [ ] **Step 5: Create `IoReportProfiler.java`**

```java
package nl.utwente.gsd.energy;

import org.openjdk.jmh.profile.ProfilerException;

import java.io.IOException;

/**
 * Apple IOReport energy per iteration. Requires powermetrics running as root:
 * on macOS 27 it is what refreshes the counters.
 * Register with: -prof nl.utwente.gsd.energy.IoReportProfiler
 */
public class IoReportProfiler extends EnergyProfiler {

    public IoReportProfiler() throws ProfilerException {
        super(open(), "ioreport");
    }

    private static IoReportReader open() throws ProfilerException {
        try {
            return new IoReportReader();
        } catch (IOException e) {
            throw new ProfilerException(
                "Cannot initialise IOReport: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    @Override
    public String getDescription() {
        return "Apple IOReport energy per iteration (refreshed by powermetrics)";
    }
}
```

- [ ] **Step 6: Allow native access in benchmark forks.** In `ConcurrencyEnergyBenchmark.java` line 23, change to:

```java
@Fork(value = 5, jvmArgs = {"-Xms2g", "-Xmx2g", "-XX:+UseG1GC", "--enable-native-access=ALL-UNNAMED"})
```

- [ ] **Step 7: Run all tests and build**

```bash
mvn -q -B clean package && grep -h "Tests run" target/surefire-reports/*.txt
```
Expected: BUILD SUCCESS; EnergyProfilerTest 2/2 pass; no failures anywhere.

- [ ] **Step 8: Commit**

```bash
cd .. && git add harness/src
git commit -m "refactor: platform-neutral EnergyProfiler with RAPL and IOReport front ends"
```

---

### Task 5: `IdleBaseline` tool

**Files:**
- Create: `harness/src/main/java/nl/utwente/gsd/energy/IdleBaseline.java`
- Test: `harness/src/test/java/nl/utwente/gsd/energy/IdleBaselineTest.java`

- [ ] **Step 1: Write the failing test**

```java
package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;

import java.util.Locale;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class IdleBaselineTest {

    private static final EnergyReader FAKE = new EnergyReader() {
        @Override public Map<String, Long> readAll() { return Map.of(); }
        @Override public long deltaFor(String domain, long start, long end) { return end - start; }
    };

    @Test
    void wattsAreJoulesOverSeconds() {
        Map<String, Double> w = IdleBaseline.watts(FAKE,
                Map.of("CPU_Energy", 0L), Map.of("CPU_Energy", 30_000_000L), 60.0);
        assertEquals(0.5, w.get("CPU_Energy"), 1e-9);
    }

    @Test
    void jsonUsesDotDecimalsRegardlessOfLocale() {
        Locale previous = Locale.getDefault();
        Locale.setDefault(Locale.forLanguageTag("nl-NL"));
        try {
            String json = IdleBaseline.toJson(60.0, Map.of("CPU_Energy", 0.5));
            assertTrue(json.contains("\"seconds\": 60.000"), json);
            assertTrue(json.contains("\"CPU_Energy\": 0.500000"), json);
        } finally {
            Locale.setDefault(previous);
        }
    }
}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd harness && mvn -q -B test -Dtest=IdleBaselineTest
```
Expected: compilation failure, `cannot find symbol: class IdleBaseline`.

- [ ] **Step 3: Create `IdleBaseline.java`**

```java
package nl.utwente.gsd.energy;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Measures idle power per energy domain over a fixed window, for idle-baseline
 * subtraction. Usage:
 * java -cp benchmarks.jar nl.utwente.gsd.energy.IdleBaseline &lt;seconds&gt; &lt;out.json&gt;
 */
public final class IdleBaseline {

    private IdleBaseline() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: IdleBaseline <seconds> <out.json>");
            System.exit(2);
        }
        double seconds = Double.parseDouble(args[0]);
        EnergyReader reader = EnergyReader.forThisMachine();
        Map<String, Long> start = reader.readAll();
        long t0 = System.nanoTime();
        Thread.sleep((long) (seconds * 1000));
        long t1 = System.nanoTime();
        Map<String, Long> end = reader.readAll();
        double window = (t1 - t0) / 1e9;
        String json = toJson(window, watts(reader, start, end, window));
        Files.writeString(Path.of(args[1]), json);
        System.out.print(json);
    }

    static Map<String, Double> watts(EnergyReader reader, Map<String, Long> start,
                                     Map<String, Long> end, double seconds) {
        Map<String, Double> out = new LinkedHashMap<>();
        for (Map.Entry<String, Long> e : start.entrySet()) {
            long uj = reader.deltaFor(e.getKey(), e.getValue(), end.get(e.getKey()));
            out.put(e.getKey(), uj / 1e6 / seconds);
        }
        return out;
    }

    static String toJson(double seconds, Map<String, Double> watts) {
        String body = watts.entrySet().stream()
                .map(e -> String.format(Locale.ROOT, "\"%s\": %.6f", e.getKey(), e.getValue()))
                .collect(Collectors.joining(", "));
        return String.format(Locale.ROOT, "{\"seconds\": %.3f, \"watts\": {%s}}%n", seconds, body);
    }
}
```

- [ ] **Step 4: Run tests and rebuild the jar**

```bash
mvn -q -B clean package && grep -h "Tests run" target/surefire-reports/*.txt
```
Expected: BUILD SUCCESS; IdleBaselineTest 2/2 pass.

- [ ] **Step 5: Commit**

```bash
cd .. && git add harness/src
git commit -m "feat: IdleBaseline tool for idle-power subtraction"
```

---

### Task 6: Mac measurement scripts

**Files:**
- Create: `scripts/mac/env-manifest.sh`
- Create: `scripts/mac/quiet-check.sh`
- Create: `scripts/mac/powermetrics-start.sh`
- Create: `scripts/mac/powermetrics-stop.sh`
- Create: `scripts/mac/pilot-mac.sh`

- [ ] **Step 1: `scripts/mac/env-manifest.sh`**

```bash
#!/usr/bin/env bash
# Records the hardware/software environment of a measurement batch.
# Usage: scripts/mac/env-manifest.sh <out-file>
set -euo pipefail
out="$1"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home}"
{
  echo "# date (UTC)";   date -u +%Y-%m-%dT%H:%M:%SZ
  echo "# git";          git -C "$repo" rev-parse HEAD; git -C "$repo" status --short | head -20
  echo "# os";           sw_vers; uname -a
  echo "# hardware";     sysctl hw.model machdep.cpu.brand_string hw.memsize hw.ncpu \
                           hw.perflevel0.physicalcpu hw.perflevel1.physicalcpu
  echo "# power";        pmset -g; pmset -g batt | head -1; pmset -g therm
  echo "# java";         "$JAVA_HOME/bin/java" -version 2>&1
  echo "# uptime/load";  uptime
  echo "# top processes by cpu"; ps -Ao pcpu,comm -r | head -11
} > "$out" 2>&1
echo "wrote $out"
```

- [ ] **Step 2: `scripts/mac/quiet-check.sh`**

```bash
#!/usr/bin/env bash
# Fails unless the machine is quiet enough to measure: overall CPU idle over a
# 3 s window must be at least MIN_IDLE percent (default 95).
# Usage: scripts/mac/quiet-check.sh [min_idle_percent]
set -euo pipefail
min="${1:-95}"
idle=$(top -l 2 -s 3 -n 0 | awk '/CPU usage/ {v=$7} END {sub("%","",v); sub(",",".",v); print v}')
echo "CPU idle over 3 s: ${idle}% (need >= ${min}%)"
ps -Ao pcpu,comm -r | head -6
awk -v i="$idle" -v m="$min" 'BEGIN { exit !(i >= m) }'
```

- [ ] **Step 3: `scripts/mac/powermetrics-start.sh` and `powermetrics-stop.sh`**

```bash
#!/usr/bin/env bash
# Starts powermetrics as root in the background. On macOS 27 it is what
# refreshes the IOReport energy counters (frozen otherwise); it also logs
# cluster residency/frequency and thermal pressure.
# Usage: scripts/mac/powermetrics-start.sh <interval_ms> <log-file>
set -euo pipefail
interval="$1"; log="$2"
sudo -v
sudo powermetrics --samplers cpu_power,thermal -i "$interval" -o "$log" >/dev/null 2>&1 &
sleep 2
pgrep -x powermetrics >/dev/null || { echo "error: powermetrics did not start" >&2; exit 1; }
echo "powermetrics running at ${interval} ms -> $log"
```

```bash
#!/usr/bin/env bash
# Stops any running powermetrics started by powermetrics-start.sh.
sudo pkill -x powermetrics || true
sleep 1
```

- [ ] **Step 4: `scripts/mac/pilot-mac.sh`**

```bash
#!/usr/bin/env bash
# Mac feasibility pilot for Assignment 2 (~20 min). Follow the quiet-machine
# protocol in the A2 plan first (quit all apps, Wi-Fi off, Spotlight paused).
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="results/pilot-mac"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home}"
JAVA=("$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED)
JAR="harness/target/benchmarks.jar"
mkdir -p "$OUT"

scripts/mac/quiet-check.sh 95 || { echo "machine not quiet; quit apps and retry" >&2; exit 1; }
scripts/mac/env-manifest.sh "$OUT/env.txt"
caffeinate -i -s -w $$ &
sudo -v
while true; do sudo -n true; sleep 60; done 2>/dev/null &   # keep sudo alive for the final stop
KEEPALIVE=$!
trap 'scripts/mac/powermetrics-stop.sh; kill $KEEPALIVE 2>/dev/null' EXIT

# Idle power with the refresher at 1000 ms (reference for powermetrics' own overhead)
scripts/mac/powermetrics-start.sh 1000 "$OUT/powermetrics-1000ms.txt"
"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline 60 "$OUT/idle-1000ms.json"
scripts/mac/powermetrics-stop.sh

# Experiment refresh rate: 100 ms
scripts/mac/powermetrics-start.sh 100 "$OUT/powermetrics-100ms.txt"
"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline 60 "$OUT/idle-start.json"
"${JAVA[@]}" -jar "$JAR" \
  -prof nl.utwente.gsd.energy.IoReportProfiler \
  -p strategy=PLATFORM_THREADS,FIXED_POOL,FORK_JOIN,VIRTUAL_THREADS \
  -p parallelism=8 -p workloadType=CPU,IO \
  -f 3 -wi 5 -w 1s -i 5 -r 5s \
  -rf json -rff "$OUT/pilot.json" -foe true
"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline 60 "$OUT/idle-end.json"
echo "Mac pilot complete: $OUT"
```

- [ ] **Step 5: Make the scripts executable, syntax-check them, and dry-run the gate**

```bash
chmod +x scripts/mac/*.sh && for f in scripts/mac/*.sh; do bash -n "$f" && echo "ok $f"; done
scripts/mac/quiet-check.sh 95; echo "exit=$?"
```
Expected: `ok` for all five scripts. While apps are open, quiet-check prints an idle below 95 % and `exit=1`. That's correct: it proves the gate works.

- [ ] **Step 6: Short functional check of the profiler with the refresher running (Sounic, needs sudo; ~1 min)**

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home
scripts/mac/powermetrics-start.sh 100 /tmp/pm-check.txt
"$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED -jar harness/target/benchmarks.jar \
  -prof nl.utwente.gsd.energy.IoReportProfiler -p strategy=VIRTUAL_THREADS -p parallelism=8 \
  -p workloadType=CPU -f 1 -wi 1 -i 2 -r 5s 2>&1 | grep -E "ioreport\.(CPU_Energy|window_s)"
scripts/mac/powermetrics-stop.sh
```
Expected:
- `ioreport.CPU_Energy.J` is positive, around 30–60 J for a 5 s CPU-bound window.
- `ioreport.CPU_Energy.J_per_op` is positive.
- `ioreport.window_s` is about 5.
- Values of exactly 0 mean the refresher wasn't running.

- [ ] **Step 7: Commit**

```bash
git add scripts/mac
git commit -m "feat: Mac measurement scripts (quiet gate, env manifest, powermetrics refresher, pilot)"
```

---

### Task 7: Pilot summary script (standard library only)

**Files:**
- Create: `analysis/summarize_pilot.py`
- Test: `analysis/test_summarize_pilot.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from summarize_pilot import summarise


def row(strategy, ms, jop, joules, window):
    return {
        "params": {"strategy": strategy, "workloadType": "IO", "parallelism": "8"},
        "primaryMetric": {"rawData": ms},
        "secondaryMetrics": {
            "ioreport.CPU_Energy.J_per_op": {"rawData": jop},
            "ioreport.CPU_Energy.J": {"rawData": joules},
            "ioreport.window_s": {"rawData": window},
        },
    }


class SummariseTest(unittest.TestCase):
    def test_fork_medians_power_and_idle_subtraction(self):
        r = row("VIRTUAL_THREADS",
                ms=[[10.0, 12.0, 11.0], [11.0, 11.0, 11.0]],
                jop=[[0.2, 0.2, 0.2], [0.4, 0.4, 0.4]],
                joules=[[5.0, 5.0, 5.0], [5.0, 5.0, 5.0]],
                window=[[5.0, 5.0, 5.0], [5.0, 5.0, 5.0]])
        (out,) = summarise([r], idle_watts=1.0)
        self.assertAlmostEqual(out["ms_per_op"], 11.0)
        self.assertAlmostEqual(out["J_per_op"], 0.3)
        self.assertAlmostEqual(out["W"], 1.0)
        self.assertAlmostEqual(out["J_per_op_active"], 0.3 - 1.0 * 0.011)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd analysis && python3 -m unittest test_summarize_pilot -v
```
Expected: `ModuleNotFoundError: No module named 'summarize_pilot'`.

- [ ] **Step 3: Write `analysis/summarize_pilot.py`**

```python
#!/usr/bin/env python3
"""Summarise a JMH JSON file produced with an energy profiler.

Usage: analysis/summarize_pilot.py <pilot.json> [idle.json]

One Markdown row per (strategy, workload): median ms/op and J/op for the
primary energy domain (medians of per-fork medians), mean power, coefficient
of variation of per-fork J/op, and idle-subtracted J/op when idle.json is given.
"""
import json
import statistics
import sys

PRIMARY = {"ioreport": "CPU_Energy", "rapl": "intel-rapl:0:package-0"}


def primary_domain(secondary):
    for prefix, domain in PRIMARY.items():
        if f"{prefix}.{domain}.J_per_op" in secondary:
            return prefix, domain
    raise KeyError("no known energy domain in secondaryMetrics")


def fork_medians(raw):
    return [statistics.median(fork) for fork in raw]


def summarise(rows, idle_watts=None):
    out = []
    for r in rows:
        sec = r["secondaryMetrics"]
        prefix, domain = primary_domain(sec)
        ms = fork_medians(r["primaryMetric"]["rawData"])
        jop = fork_medians(sec[f"{prefix}.{domain}.J_per_op"]["rawData"])
        joules = fork_medians(sec[f"{prefix}.{domain}.J"]["rawData"])
        window = fork_medians(sec[f"{prefix}.window_s"]["rawData"])
        ms_med = statistics.median(ms)
        jop_med = statistics.median(jop)
        row = {
            "strategy": r["params"]["strategy"],
            "workload": r["params"]["workloadType"],
            "ms_per_op": ms_med,
            "J_per_op": jop_med,
            "W": statistics.mean(j / w for j, w in zip(joules, window)),
            "cv_J_per_op": (statistics.stdev(jop) / statistics.mean(jop)) if len(jop) > 1 else float("nan"),
        }
        if idle_watts is not None:
            row["J_per_op_active"] = jop_med - idle_watts * ms_med / 1000.0
        out.append(row)
    return out


def main(argv):
    with open(argv[1]) as f:
        rows = json.load(f)
    idle = None
    if len(argv) > 2:
        with open(argv[2]) as f:
            idle = json.load(f)["watts"][primary_domain(rows[0]["secondaryMetrics"])[1]]
    cols = ["strategy", "workload", "ms_per_op", "J_per_op", "W", "cv_J_per_op"]
    if idle is not None:
        cols.append("J_per_op_active")
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for row in summarise(rows, idle):
        cells = [f"{row[c]:.4g}" if isinstance(row[c], float) else str(row[c]) for c in cols]
        print("| " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main(sys.argv)
```

- [ ] **Step 4: Run the test, then the script on the Intel pilot as a real-data check**

```bash
python3 -m unittest test_summarize_pilot -v
```
Expected: `OK` (1 test). The existing Intel pilot has no `rapl.window_s` metric (it predates Task 4), so it is **not** a valid input; Task 8 provides the first real input.

- [ ] **Step 5: Commit**

```bash
cd .. && git add analysis
git commit -m "feat: stdlib-only pilot summary (fork medians, power, idle subtraction)"
```

---

### Task 8: Run the Mac pilot and JFR smoke (Sounic at the Mac, ≈ 25 min)

**Files:**
- Create (by running): `results/pilot-mac/{env.txt,pilot.json,idle-1000ms.json,idle-start.json,idle-end.json,powermetrics-*.txt}`

- [ ] **Step 1: Apply the quiet-machine protocol** (top of this plan). Quitting Claude desktop is fine, because the plan and code are on disk; reopen it afterwards.

- [ ] **Step 2: Run the pilot**

```bash
cd "/Users/imsounic/Green Software Development/vt-energy" && scripts/mac/pilot-mac.sh
```
Expected:
- A sudo prompt once; quiet-check passes.
- About 20 min later: `Mac pilot complete: results/pilot-mac`.
- `results/pilot-mac/pilot.json` has 8 entries.

- [ ] **Step 3: Summarise**

```bash
python3 analysis/summarize_pilot.py results/pilot-mac/pilot.json results/pilot-mac/idle-start.json | tee results/pilot-mac/summary.md
cat results/pilot-mac/idle-*.json
```
Expected:
- 8 rows, all `J_per_op > 0`.
- VIRTUAL_THREADS/IO ms_per_op about 12; FIXED_POOL/IO about 387.
- `idle-1000ms` vs `idle-start` (100 ms) `CPU_Energy` watts: their difference is the refresher's overhead estimate.

- [ ] **Step 4: JFR smoke (machine need not be quiet)**

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home
for s in VIRTUAL_THREADS PLATFORM_THREADS; do
  "$JAVA_HOME/bin/java" -jar harness/target/benchmarks.jar -p strategy=$s -p parallelism=8 -p workloadType=IO \
    -f 1 -wi 2 -i 2 -r 5s \
    -jvmArgsAppend "-XX:StartFlightRecording=filename=results/pilot-mac/$s-io.jfr,settings=profile" >/dev/null
  "$JAVA_HOME/bin/jfr" summary results/pilot-mac/$s-io.jfr | tee results/pilot-mac/$s-io.jfr-summary.txt | head -40
done
```
Expected: two event-count tables, including thread, GC and execution-sample event types. Use 1–2 contrasting counts in the report's §5.4 (for example, thread-start or park/sleep event counts for VT vs platform threads).

- [ ] **Step 5: Commit the pilot output**

```bash
git add -f results/pilot-mac/*.json results/pilot-mac/*.txt results/pilot-mac/summary.md
git commit -m "feat: Mac feasibility pilot (IOReport, powermetrics refresh at 100 ms)"
```

---

### Task 9: Bibliography additions (verified before citing)

**Files:**
- Modify: `paper/refs.bib`

Rule from `refs.bib`: **no entry without checking that the DOI resolves to the stated title and authors** (Crossref: `curl -s https://api.crossref.org/works/<DOI> | python3 -c "import json,sys;m=json.load(sys.stdin)['message'];print(m['title'],[a['family'] for a in m['author']])"`).

- [ ] **Step 1: Verify and add the methodology references named by the brief and lectures**

| Key | Candidate | DOI / id to verify |
|---|---|---|
| `jedlitschka2008reporting` | Jedlitschka, Ciolkowski, Pfahl, "Reporting Experiments in Software Engineering", *Guide to Advanced Empirical Software Engineering*, Springer 2008 | 10.1007/978-1-84800-044-5_8 |
| `castor2024primer` | Castor, "Estimating the energy footprint of software systems: a primer", arXiv 2024 | arXiv:2407.11611 |
| `khan2018rapl` | Khan, Hirki, Niemi, Nurminen, Ou, "RAPL in Action", ACM TOMPECS 3(2):9, 2018 | 10.1145/3177754 |
| `mytkowicz2009wrong` | Mytkowicz, Diwan, Hauswirth, Sweeney, "Producing wrong data without doing anything obviously wrong!", ASPLOS 2009 | 10.1145/1508244.1508275 |
| `georges2007rigorous` | Georges, Buytaert, Eeckhout, "Statistically rigorous Java performance evaluation", OOPSLA 2007 | 10.1145/1297027.1297033 |

- [ ] **Step 2: Search for 2–3 additional *related work* entries, add only if verified**
  - Empirical performance evaluations of Java virtual threads (2023–2026).
  - Energy or power measurement on Apple Silicon (`powermetrics`/IOReport accuracy).

  For each one, record title, venue, DOI, its one-line finding and the **limitation** we exploit, matching A1's related-work style. If nothing verifiable turns up within 45 min, add Khan et al. and Georges et al. to Related Work instead (accuracy of the instrument; JVM measurement methodology).

- [ ] **Step 3: Commit**

```bash
git add paper/refs.bib && git commit -m "docs: verified A2 references"
```

---

### Task 10: Restructure `main.tex` for A2

**Files:**
- Modify: `paper/main.tex`

- [ ] **Step 1: Preamble additions** (after `\emergencystretch=1.2em`)

```latex
\usepackage{pifont}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\newcommand{\yes}{\ding{51}}
% Text new or changed since Assignment 1 (required in Context and Related Work).
\newcommand{\changed}[1]{\textcolor{blue}{#1}}
```
Replace every `\checkmark` in the related-work table with `\yes`.

- [ ] **Step 2: Section skeleton and page budget** (content 5–7 pages, references on page 8 at most)

| § | Title | Budget | Source |
|---|---|---|---|
| — | Abstract | 170 words | rewrite |
| 1 | Introduction | 0.6 p | A1 §1, updated |
| 2 | Context | 0.7 p | A1 §2; **changes in blue** |
| 3 | Related Work | 0.8 p | A1 §3 + Task 9; **changes in blue** |
| 4 | Experiment Planning | 1.8 p | new (Task 11) |
| 5 | Measurement Tools, Environment, and Procedure | 1.4 p | new (Task 12) |
| 6 | Threats to Validity | 0.8 p | new (Task 13) |
| 7 | Schedule | 0.3 p | new (Task 13) |
| 8 | Concluding Remarks | 0.2 p | rewrite |

- [ ] **Step 3: Put a colour notice in the first footnote**, next to the contribution statement: "Text added or changed since Assignment 1 in Sections 2–3 is shown in blue."

- [ ] **Step 4: Build**

```bash
cd paper && tectonic -X compile main.tex && pdfinfo main.pdf | grep Pages
```
Expected: builds without errors (Libertine glyph warnings for `✓` are gone).

- [ ] **Step 5: Commit**

```bash
git add paper/main.tex && git commit -m "docs: A2 report skeleton, change-colour macro"
```

---

### Task 11: Draft §1–4 (Introduction, Context, Related Work, Experiment Planning)

**Files:**
- Modify: `paper/main.tex`

Content requirements per subsection follow. The numbers and wording below are the source of truth.

- [ ] **Step 1: §1 Introduction.** Keep A1's gap statement (bold). Change the platform sentence: the Mac mini M4 (P/E hybrid) is primary, and the three-tier Intel CPU is a second arm. Update the roadmap sentence to the new sections.

- [ ] **Step 2: §2 Context (blue for changes).**
  - Technical: the five constructs (add sequential), naming JDK 25.
  - Platform paragraph:
    - M4: 4 P + 6 E cores, P up to 4.46 GHz and E up to 2.89 GHz, 16 GB unified memory, macOS 27.
    - Intel: unchanged, but conditional.
    - CPU affinity cannot be set on macOS, and quality-of-service classes are the developer-visible lever.
  - Measurement paragraph:
    - IOReport energy counters (CPU clusters, DRAM, memory controller, GPU) on the Mac; RAPL on Intel.
  - Societal text unchanged (black).

- [ ] **Step 3: §3 Related Work (blue for additions).** Add the Task 9 entries, each with a stated limitation. Add rows to the table.

- [ ] **Step 4: §4.1 Goals and research questions.** Write the general goal plus G1–G3, all in the Basili template:
  - General: Analyze Java thread management constructs (sequential baseline, platform threads, fixed thread pools, Fork/Join, virtual threads) for the purpose of characterizing, with respect to energy consumption and its relationship to execution time, from the point of view of Java developers, in the context of heterogeneous (P/E) multicore processors.
  - G1: Analyze the concurrency level of these constructs for the purpose of evaluating whether the 2014 energy–concurrency relationship still holds with respect to energy per operation and execution time, from the point of view of Java developers, in the context of DVFS-managed hybrid processors.
  - G2: Analyze virtual threads for the purpose of comparison with platform-thread-based constructs with respect to energy per operation, execution time and power, from the point of view of Java developers, in the context of CPU-bound, blocking and network-I/O workloads.
  - G3: Analyze restriction of execution to efficiency cores for the purpose of evaluating the energy cost of asymmetry-unaware scheduling with respect to energy per operation and its split across core clusters, from the point of view of Java developers and runtime implementers, in the context of P/E hybrid processors.
  - RQ1.1: How does energy/op vary with the concurrency level, per construct and workload?
  - RQ1.2: Is sequential execution the lowest-energy option?
  - RQ1.3: Is lower execution time associated with lower energy/op across configurations ("faster = greener")?
  - RQ2.1: How does VT energy/op compare with each other construct, per workload?
  - RQ2.2: At which concurrency levels, if any, does VT have the lowest energy/op?
  - RQ3.1: Does restricting execution to E cores change energy/op, and at what time cost?
  - RQ3.2: How is CPU energy split between P and E clusters under default scheduling, and does the split differ between constructs?

- [ ] **Step 5: §4.2 Hypotheses table** (one main pair and one pair per RQ; H1 is the negation of H0):

| Id | H0 (null) |
|---|---|
| H0 (main) | The thread management construct has no effect on energy per operation for any workload |
| H0-1.1 | For a given construct and workload, energy/op does not differ across concurrency levels |
| H0-1.2 | Energy/op of sequential execution does not differ from that of the lowest-energy concurrent configuration |
| H0-1.3 | Across configurations, time/op and energy/op are not monotonically associated (Spearman ρ = 0) |
| H0-2.1 | For a given workload and concurrency level, VT energy/op does not differ from that of each other construct |
| H0-2.2 | At concurrency level p, VT energy/op is not lower than that of every alternative (FIXED_POOL_p, FORK_JOIN_p, PLATFORM_THREADS, SEQUENTIAL) |
| H0-3.1 | Energy/op under E-core restriction does not differ from energy/op under default scheduling |
| H0-3.2 | The E-cluster share of CPU energy does not differ between constructs |

- [ ] **Step 6: §4.3 Experimental units and workloads.** The units are three benchmark kernels. Each executes 256 independent tasks per operation, so total work is identical across concurrency levels.
  - **CPU:** Mandelbrot 128×128, maximum 500 iterations per point. Chosen because it is in the 2014 benchmark set, deterministic and allocation-free.
  - **SLEEP:** `Thread.sleep(10 ms)` per task. Isolates the unmount-on-block mechanism with controlled latency; the macOS sleep overshoot is measured (AX5).
  - **SOCKET:** each task opens a loopback TCP connection to an out-of-process server, sends 64 B, and gets a 64 B reply that the server delays by 10 ms without blocking. One connection per task keeps the I/O pattern identical across constructs; the server's energy is constant per task and is reported as a construct threat.
  - **Randomisation:** units are fixed, not sampled. The order of all (unit × treatment × replicate) runs is randomised with a recorded seed.

- [ ] **Step 7: §4.4 Variables (table).**
  - **Independent variables:**
    - Construct: 5 levels.
    - Concurrency level p ∈ {1, 2, 4, 8, 16, 64, 256}, with per-construct meaning as in D4.
    - Workload: 3 levels.
    - Core restriction (Mac): DEFAULT, BACKGROUND. On Intel: unpinned, 2P, 2E, 2LP-E.
  - **Dependent variables:**
    - Energy/op (J), per channel: CPU (= ECPU + PCPU) on the Mac and package on Intel are primary; DRAM + AMCC + DCS (memory), ECPU and PCPU are secondary; on Intel also core, uncore and psys.
    - Time/op (ms).
    - Average power (W).
    - Energy-delay product (J·s).
    - E-cluster share of CPU energy.
    - Idle-subtracted energy/op.
  - **Explanatory profiler metrics:** wakeups and CPU time per task (`powermetrics` tasks), cluster residency and frequency, and JFR events (thread starts, park/sleep, GC).
  - **Controlled variables:** 256 tasks per op; JDK 25.0.4.1; `-Xms2g -Xmx2g -XX:+UseG1GC`; JMH 1.37; same machine; AC power; Low Power Mode off; quiet-machine protocol.

- [ ] **Step 8: §4.5 Design.**
  - Within-subjects design: every unit receives every treatment.
  - **Experiment 1** (RQ1.x, RQ2.x) is a full factorial of construct × p × workload under DEFAULT QoS. Per workload: SEQ 1 + PT 1 + FP 6 + FJ 6 + VT 6 = 20 cells, so 60 cells in total.
  - **Experiment 2** (RQ3.x) is a fractional arm under BACKGROUND QoS with p ∈ {4, 16}. Per workload: SEQ, PT, FP×2, FJ×2, VT×2 = 8 cells, so 24 cells. Its DEFAULT counterparts come from Experiment 1.
  - **Runs:** 10 forks per cell gives 930 runs (69 + 24 cells after adding p = 256), interleaved in one randomised schedule. A batch is about 40 runs, with a 60 s idle baseline at the start of each batch.

- [ ] **Step 9: §4.6 Analysis procedure.**
  - **Basics:**
    - Per-run value: median of the 5 measured iterations.
    - Descriptive statistics: medians, IQR and CV.
    - Plots: Λ curves, energy-vs-time scatter, cluster-split bars.
    - Shapiro–Wilk normality checks, expected to fail, so all tests are non-parametric. α = 0.05, with Holm correction within each hypothesis family.
  - **Test per hypothesis:**
    - H1.1: Kruskal–Wallis across p within construct × workload (FP, FJ, VT × 3 workloads = 9 tests), then Dunn post-hoc tests with Holm correction, and ε² as the effect size.
    - H1.2: split-sample. Forks 1–5 select the lowest-median concurrent configuration per workload; forks 6–10 are used for a Mann–Whitney U test of SEQ vs that configuration, with Cliff's δ.
    - H1.3: Spearman ρ between cell-median time/op and energy/op per workload (n = 20 cells).
    - H2.1: per workload × p, Kruskal–Wallis across FP, FJ, VT, then Dunn tests of VT vs each.
    - H2.2: an intersection–union test. VT_p must be significantly lower than every alternative (one-sided Mann–Whitney U tests) to reject. Report the smallest such p, with Cliff's δ.
    - H3.1: Mann–Whitney U tests of DEFAULT vs BACKGROUND per cell, with Cliff's δ and the time penalty (%) with bootstrap 95 % CIs.
    - H3.2: Kruskal–Wallis of E-share across constructs.
    - Main H0: rejected if, for any workload, Kruskal–Wallis across constructs at p = 8 (plus SEQ and PT) rejects after Holm correction.
  - **Null results:** TOST equivalence via a bootstrap 90 % CI of the ratio of medians within [0.95, 1.05]. The ±5 % margin is at least twice the instrument's worst-case boundary error.
  - **Sample size:** fork-to-fork CV from the Mac pilot gives the n needed to detect a 10 % difference with power 0.8 (Mann–Whitney U, ARE 0.955). If n > 10, the key comparisons get more forks from the reserve budget.

- [ ] **Step 10: Build, check pages, commit**

```bash
cd paper && tectonic -X compile main.tex && pdfinfo main.pdf | grep Pages && cd ..
git add paper/main.tex && git commit -m "docs: A2 sections 1-4"
```

---

### Task 12: Draft §5 Measurement Tools, Environment, and Procedure

**Files:**
- Modify: `paper/main.tex`

- [ ] **Step 1: §5.1 Environment table.**
  - Two columns: Mac (primary) and Intel (conditional).
  - Rows: CPU and cores, maximum frequencies, memory, OS and kernel, JDK, JVM flags, JMH, energy interface, frequency governance (Apple's own performance controller vs `intel_pstate`/HWP with turbo), power source, and core-restriction mechanism (`taskpolicy -b` vs `taskset`).
  - Values: from Ground truth above, plus `results/pilot-mac/env.txt` and A1's Intel facts.

- [ ] **Step 2: §5.2 Energy measurement.**
  - **Mac:**
    - IOReport "Energy Model" counters are read in-process through an FFM-bound C shim, once before and once after each JMH iteration.
    - On macOS 27 these counters are published only while `powermetrics` samples, so it runs as root at 100 ms purely as a refresher. It also logs residency, frequency and thermal pressure.
    - Worst-case staleness per boundary is 100 ms, i.e. ≤ 2 % of a 5 s window.
    - Sampling rate: 2 counter reads per iteration; refresher at 10 Hz.
  - **Intel:** RAPL powercap, boundary-only reads, wraparound correction.
  - **Why boundary reads:** they avoid polling-induced C-state suppression [Raffin & Trystram].
  - **Accuracy:** RAPL has been validated against physical meters [Khan et al.]. Apple's counters are model-based and unvalidated, so the cross-checks AX3 and AX4 are used.

- [ ] **Step 3: §5.3 Procedure.**
  - Per batch: env manifest, quiet gate, refresher start, then a 60 s idle baseline.
  - Per run:
    1. Quiet gate (≥ 95 % idle).
    2. `java -jar benchmarks.jar` with `-f 1 -wi 5 -w 1s -i 5 -r 5s` and the cell's parameters. VT runs add `-jvmArgsAppend -Djdk.virtualThreadScheduler.parallelism=p`. BACKGROUND runs pass the fork JVM through a `taskpolicy -b` wrapper via JMH `-jvm`.
    3. JSON output.
    4. Cooldown of at least 10 s, until thermal pressure is "Nominal".
  - Why 5 + 5 iterations:
    - Warmup: JIT steady state was reached within the first iterations in the Intel pilot.
    - Measurement: 5 s windows keep refresher staleness ≤ 2 %.
    - 10 forks: replication unit (D7).
  - Data: one JSON per run, plus a schedule CSV (seed, order, timestamps), the `powermetrics` log and idle JSONs.

- [ ] **Step 4: §5.4 Profiling.**
  - JFR (`settings=profile`) for Java-level causes: thread starts, park/sleep, GC, hot methods.
  - `powermetrics --samplers tasks,cpu_power` for wakeups per second and cluster residency.
  - On Intel: `perf stat -e context-switches,cpu-migrations,cycles` split by core type.
  - All run in separate passes (2 forks per selected cell), never during energy runs.
  - Cite the 1–2 contrasting counts from Task 8 Step 4 as familiarity evidence.

- [ ] **Step 5: §5.5 Familiarity with the infrastructure and pitfalls.** Four pitfalls, each with how the design handles it:
  1. **Intel power regime shift.** Figure: per-iteration package energy, PLATFORM_THREADS/CPU, fork 1 vs fork 2. Use the pgfplots code below. The A1 CPU numbers averaged over both regimes. Handled by: randomisation, cooldown, regime logging.
  2. **Frozen and stale IOReport counters.** A table of refresh cadence vs `powermetrics` interval (the Ground-truth table), plus the 1100 mJ vs 8149 mW example. Handled by: a 100 ms refresher plus 5 s windows.
  3. **macOS `Thread.sleep` overshoot** (12.1 vs 10 ms). Handled by: calibration (AX5) and reporting measured, not nominal, latency.
  4. **Background load.** 68 % idle with everyday apps open. Handled by: the quiet-machine protocol plus the gate.
  - Then the **Mac pilot table** from `results/pilot-mac/summary.md`: 8 rows with ms/op, J/op, W and CV. Also the refresher overhead from `idle-1000ms.json` vs `idle-start.json`.
  - Fallback after the Fri 13:00 cutoff: drop the pilot table and keep pitfalls 1–4.

```latex
\begin{figure}
\begin{tikzpicture}
\begin{axis}[width=\columnwidth, height=3.6cm, xlabel={Measured iteration (1\,s)},
  ylabel={Package energy (J)}, ymin=0, xtick={1,...,10},
  legend style={font=\scriptsize, at={(0.98,0.97)}, anchor=north east},
  tick label style={font=\scriptsize}, label style={font=\scriptsize}]
\addplot+[mark=*] coordinates {(1,62.0)(2,62.8)(3,62.5)(4,57.7)(5,63.1)(6,54.2)(7,35.8)(8,25.4)(9,25.0)(10,24.9)};
\addplot+[mark=square*] coordinates {(1,25.3)(2,27.6)(3,25.0)(4,25.1)(5,26.1)(6,25.0)(7,24.9)(8,25.8)(9,25.8)(10,26.5)};
\legend{Fork 1, Fork 2}
\end{axis}
\end{tikzpicture}
\caption{Intel pilot, platform threads on the CPU-bound workload: package energy per 1\,s iteration falls from about 62\,J to 25\,J within fork~1 while time per operation rises from 89 to 128\,ms, and fork~2 starts in the low regime. Identical treatment, different power state.}
\label{fig:regime}
\end{figure}
```

- [ ] **Step 6: Build, check pages, commit**

```bash
cd paper && tectonic -X compile main.tex && pdfinfo main.pdf | grep Pages && cd ..
git add paper/main.tex && git commit -m "docs: A2 section 5 measurement, environment, procedure"
```

---

### Task 13: Draft §6 Threats, §7 Schedule, §8 Concluding remarks, abstract

**Files:**
- Modify: `paper/main.tex`

- [ ] **Step 1: §6 Threats to validity.** Use four subsections, each threat followed by its mitigation. Ancillary experiments: AX1 refresh cadence (done), AX2 refresher overhead, AX3 IOReport vs `powermetrics` CPU Power consistency, AX4 load-scaling sanity (0–10 busy threads), AX5 sleep calibration (10⁴ sleeps per thread kind), AX6 BACKGROUND confinement (P-cluster residency ≈ 0), AX7 run-order/thermal drift check.

  **Construct validity:**

  | Threat | Mitigation |
  |---|---|
  | The counters are model estimates; there's no wall meter | Khan et al. for RAPL; AX3/AX4 for Apple; state it |
  | Scope: CPU/SoC only (no PSU, SSD, network, fan) | Report what each channel covers |
  | Sleep as an I/O proxy | SOCKET workload; AX5 |
  | Boundary staleness | ≤ 2 % bound; AX1 |
  | Energy/op includes pool creation/teardown by definition | State it |
  | Construct implementations differ from 2014 (per-task platform threads, recursive Fork/Join) | State and justify |

  **Internal validity:**

  | Threat | Mitigation |
  |---|---|
  | Background load | Quiet protocol, gate, idle baseline |
  | Order and thermal effects | Randomisation, cooldown, AX7, regime logging |
  | Measurement overhead | Boundary reads; refresher overhead AX2, included in idle baseline |
  | JIT/GC | JMH warmup, fixed heap, JFR |
  | Uncontrollable DVFS | Recorded via residency logs |
  | BACKGROUND QoS also lowers frequency and I/O priority | AX6; interpret G3 on the Mac as "QoS class", not pure placement |
  | On Intel, `taskset` changes `availableProcessors` (carriers, GC/JIT threads) | Equal-count arms; state it |
  | The socket server shares the machine | Constant per task; state it |

  **External validity:**

  | Threat | Mitigation |
  |---|---|
  | One primary machine; Intel conditional | M4 is a mainstream hybrid design |
  | Three kernels vs nine in 2014 | Chosen to span CPU / blocking / I/O |
  | Synthetic workloads, fixed 256 tasks | State it |
  | One JDK (25) and one OS each | LTS = what developers deploy |

  **Conclusion validity:**

  | Threat | Mitigation |
  |---|---|
  | Non-normal data | Non-parametric tests |
  | Multiple comparisons | Holm |
  | Effect sizes | Cliff's δ, ε², bootstrap CIs |
  | Null results | TOST |
  | Pseudo-replication | Fork = unit [Georges et al.] |
  | Selection bias in H1.2 | Split-sample |
  | Sample size | Pilot-based power analysis |

- [ ] **Step 2: §7 Schedule (table).** Assumes the A3 deadline is the end of week 9 (Fri 30 Oct); confirm on Canvas.

| Dates | Activity | Machine time |
|---|---|---|
| 3–7 Oct | Implement Part B tasks B1–B7 | — |
| 8 Oct | Ancillary AX2–AX7, pilot 2, sample size | 3 h |
| 9–11 Oct | Mac Experiments 1 + 2 (3 overnight batches) | 11 h |
| 12 Oct | Profiling passes | 1.5 h |
| 13–16 Oct | Mac analysis; **16 Oct Intel go/no-go** | — |
| 17–20 Oct | Intel arm, if available | ≤ 15 h |
| 19–26 Oct | Final report | — |
| 27–30 Oct | Replication package, presentation | — |

  Total machine time ≈ 16.5 h (Mac) + ≤ 15 h (Intel) ≈ 32 h, under the 40 h guideline, leaving about 8 h for re-runs.

  Per-run estimate: about 31 s of JMH (5×1 s + 5×5 s + JVM start), plus up to 15 s for slow cells (FP/FJ SLEEP p=1, op ≈ 3.1 s), plus a 10 s cooldown, so about 45 s on average. 930 runs × 45 s ≈ 11.6 h.

- [ ] **Step 3: §8 Concluding remarks.** Wrap up in one paragraph: what changed since A1 (Mac primary, five constructs, hypotheses, the pitfalls found) and what A3 delivers.

- [ ] **Step 4: Abstract.** Rewrite to about 170 words: gap, design (5 constructs × 6 levels × 3 workloads, QoS arm), instrument and pitfalls, and that the plan is under 40 h.

- [ ] **Step 5: Build, check pages, commit**

```bash
cd paper && tectonic -X compile main.tex && pdfinfo main.pdf | grep Pages && cd ..
git add paper/main.tex && git commit -m "docs: A2 sections 6-8 and abstract"
```

---

### Task 14: Final checks and submission (Fri)

**Files:**
- Modify: `paper/main.tex` (footnote, fixes)

- [ ] **Step 1: Contribution footnote.** Sounic and Vasil write the real split for A2 into `\thanks{...}`: who did the harness, the Mac instrument work, which report sections, and the review. This must be their own statement.

- [ ] **Step 2: Page check**

```bash
cd paper && tectonic -X compile main.tex && pdfinfo main.pdf | grep Pages
pdftotext -layout main.pdf - | grep -n "REFERENCES"
```
Expected: 7 or 8 pages in total, with the REFERENCES heading on page 7 or later and no content after the references.

- [ ] **Step 3: Brief compliance checklist**

- [ ] Title, authors, abstract present
- [ ] Sections in the brief's order: Intro, Context, Related Work, Experiment planning, Measurement tools/environment/procedure, Threats, Schedule, Concluding remarks
- [ ] Context and Related Work changes in blue, with a notice in the footnote
- [ ] H0/H1 for every RQ plus a main pair
- [ ] Units + rationale + randomisation; variables with levels; workloads + why; design; analysis per hypothesis
- [ ] Environment details; instrument + rationale + precision; synchronisation; executions per trial + why; sampling rate; overhead precautions
- [ ] Profiler selected, with familiarity evidence
- [ ] Threats in 4 categories, each with a mitigation
- [ ] Schedule < 40 h
- [ ] Contribution footnote filled
- [ ] Every citation verified (Task 9)

- [ ] **Step 4: Commit and submit**

```bash
git add paper && git commit -m "docs: Assignment 2 report final"
```
Sounic uploads `paper/main.pdf` to Canvas before 23:59.

---

# PART B: After submission (A3 implementation roadmap)

This part becomes its own detailed plan after the A2 submission (scope check: it is a separate subsystem from the report). The tasks and acceptance criteria are fixed here so that §4–§7 of the report describe exactly what will be built.

| Id | Task | Acceptance |
|---|---|---|
| B1 | `SEQUENTIAL` strategy (runs tasks in the caller thread) | `ExecutionStrategyTest` covers 5 constructs |
| B2 | `FORK_JOIN` via a `RecursiveAction` splitting the task list down to single tasks | Same tests pass; JFR shows fork/join tasks |
| B3 | VT carrier count from the `-Djdk.virtualThreadScheduler.parallelism` system property set per run; `parallelism` parameter becomes a no-op for VT in-process | A run log shows the carrier count used |
| B4 | Rename workload `IO` → `SLEEP`; add `SOCKET` workload + `SocketDelayServer` (NIO, 10 ms scheduled reply) | A unit test shows the round trip ≥ 10 ms |
| B5 | Orchestrator `scripts/mac/run-experiment.py`: builds the cell list (D3–D6), seeded shuffle, quiet gate, refresher, idle baseline per batch, per-run JMH invocation (VT flag, `taskpolicy` wrapper via `-jvm`), cooldown until thermal pressure is Nominal, schedule CSV | A dry run prints 930 runs and a time estimate ≤ 12 h |
| B6 | Ancillary scripts AX2–AX7 | Each writes a JSON/CSV under `results/ancillary/` |
| B7 | Analysis (`analysis/analyse.py`, venv with pandas, scipy, scikit-posthocs) implementing §4.6 exactly | Unit tests on synthetic data for every test function |
| B8 | Intel arm: same orchestrator with `RaplProfiler`, `taskset` equal-count arms, power-limit logging | Go/no-go 16 Oct |
| B9 | Replication package: code, raw JSON, env manifests, analysis notebooks, README | Fresh clone reproduces all figures |

## Self-review notes

- **Brief coverage:** each brief element maps to a step.
  - Hypotheses → T11.5; units/rationale/randomisation → T11.6; variables → T11.7; workloads → T11.6; design → T11.8; analysis → T11.9.
  - Environment/instrument/procedure/sampling/overhead → T12.1–T12.3; profiler → T8.4 + T12.4; familiarity/pitfalls → T8 + T12.5.
  - Threats → T13.1; schedule < 40 h → T13.2; colour changes → T10.1/T10.3; footnote → T14.1; page limits → T14.2.
- **Name consistency:**
  - `EnergyReader.readAll()/deltaFor()` is used identically by `RaplReader`, `IoReportReader`, `EnergyProfiler.results(...)` and `IdleBaseline.watts(...)`.
  - Metric keys `ioreport.CPU_Energy.J_per_op`, `ioreport.window_s` and `rapl.intel-rapl:0:package-0.J_per_op` match `summarize_pilot.PRIMARY`.
  - The shim exports `ior_open/ior_name/ior_read` and matches the FFM descriptors.
- **Known risk:** if the shim's channel names differ on another macOS build, `discoversCpuClusterChannels` fails loudly; it does not silently report zeros.

## Execution log (deviations from the task text above)

- **Task 6:** `ps … | head` and `git status … | head` now end in `|| true`. Under `set -o pipefail`, `head` closing the pipe made the scripts exit 141 (SIGPIPE), so the quiet gate could never pass. Commit 6cb4002.
- **Code review of Tasks 2–5:** "approve with fixes". The fixes are in commit 14f7cf5:
  - `EnergyReader.checkFresh` (a no-op by default). `IoReportReader` overrides it and throws when `CPU_Energy` doesn't advance over a window of 0.5 s or more, which means `powermetrics` isn't refreshing the counters. `EnergyProfiler.afterIteration` and `IdleBaseline` call it. Before this fix, frozen counters silently gave 0 J.
  - `IdleBaseline` waits 2 s after JVM start before measuring and writes a `"frozen": [...]` list of domains that recorded no energy. That matters because `--samplers cpu_power,thermal` may not refresh the DRAM/AMCC/SoC channels; check `idle-start.json` after the pilot.
  - `ConcurrencyEnergyBenchmark` annotation defaults now match D7/D8: `@Fork(10)`, `@Warmup(5×1 s)`, `@Measurement(5×5 s)`.
  - J/op divides by `getAllOps()`, so the ops count covers the whole energy window.
  - A unit-scaling test checks that `CPU_Energy` = `ECPU` + `PCPU`, and the powermetrics test bounds the burn to 0.05–30 J.
  - Lookup errors in `IoReportReader` are now wrapped as `IOException`; `Locale.ROOT` is used in `forThisMachine`; the channel hierarchy is documented.
- **Part B note (B3/B5):** pass VT carrier counts with `-jvmArgsAppend`, never `-jvmArgs`. `-jvmArgs` replaces the `@Fork` jvmArgs, which would drop `--enable-native-access` and the heap/GC flags.
- **Deferred minor review items:** shim edge cases (matching by channel ordinal, a `MAX_CH` overflow error, skipping negative raw values) and keeping the exception cause in `ProfilerException`. Channel names are unique on this hardware.
