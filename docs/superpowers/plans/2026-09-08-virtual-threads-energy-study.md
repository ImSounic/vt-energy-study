# Virtual Threads Energy Study — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure and compare the energy consumption of four Java concurrency constructs — platform threads, fixed thread pools, Fork-Join, and JEP 444 virtual threads — across P-core, E-core and LP-E-core placements on a hybrid x86 CPU, updating Pinto/Castor/Liu (OOPSLA 2014) for hardware and abstractions that did not exist when it was written.

**Architecture:** A JMH benchmark harness runs identical workloads under four interchangeable execution strategies. A custom JMH `InternalProfiler` reads Intel RAPL energy counters once before and once after each iteration (never polling, to avoid the C-state perturbation documented by Raffin & Trystram), and emits joules-per-operation alongside JMH's native throughput metrics. Core placement is controlled externally by pinning the whole JVM with `taskset`. Analysis is non-parametric in Python.

**Tech Stack:** Java 26 (OpenJDK), JMH 1.37, Maven, Linux powercap sysfs (`intel-rapl`), `taskset`, Python 3 (pandas/scipy) for analysis, LaTeX `acmart` for the paper.

---

## Hardware Facts (measured on the target machine, 2026-09-08)

These are real values. Do not re-derive them; verify them with Task 1.1 and update only if the machine changes.

| Core class | Logical CPUs | Max freq | `cpu_capacity` |
|---|---|---|---|
| P-cores | `0-5` | 5.1 GHz | 1024 |
| E-cores | `6-13` | 4.4 GHz | 774 |
| LP-E cores | `14-15` | 2.5 GHz | 312 |

- CPU: Intel Core Ultra 7 255H (Arrow Lake-H), 16 logical CPUs, **no SMT**
- Governor: `powersave` driven by `intel_pstate` with HWP; turbo enabled (`no_turbo=0`)
- RAPL domains present: `intel-rapl:0` (package-0), `intel-rapl:0:0` (core), `intel-rapl:0:1` (uncore), `intel-rapl:1` (**psys**)
- `psys` `max_energy_range_uj` = 262143328850 (~262 kJ; ~2.4 h at 30 W — wraparound is unlikely but MUST still be handled)
- `energy_uj` files are **root-read-only** by default
- Second platform: Apple Mac Mini M4 (P+E cores, `powermetrics`) — used in Phase 3 only

**Missing tooling** (install in Task 1.0): `mvn`, `R`/analysis libs, `pdflatex`, `perf`.

---

## Phase 0 — Critical Path Summary

Assignment 1 is a **proposal**; it does not require results. But the single highest-value thing you can put in it is one real pilot number proving the measurement pipeline works. Phase 1 below produces that. Do Phase 1 before writing the report.

---

# PHASE 1 — Feasibility Spike (target: 1 week)

## Task 1.0: Install toolchain and initialise repository

**Files:**
- Create: `vt-energy/.gitignore`
- Create: `vt-energy/README.md`

- [ ] **Step 1: Install missing tools**

```bash
sudo pacman -S --needed maven texlive-latexextra texlive-bibtexextra biber perf python-pandas python-scipy python-matplotlib
```

- [ ] **Step 2: Verify JDK is 21 or newer (virtual threads must be final, not preview)**

```bash
java -version
```

Expected: `openjdk version "26.0.2"` or any version >= 21. If below 21, install with `sudo pacman -S jdk-openjdk`.

- [ ] **Step 3: Initialise the repository**

```bash
cd "/home/imsounic/University/Green Software Development/vt-energy"
git init
```

- [ ] **Step 4: Create `.gitignore`**

```gitignore
target/
*.class
results/raw/
*.aux
*.log
*.out
*.bbl
*.blg
__pycache__/
.venv/
```

- [ ] **Step 5: Create `README.md`**

```markdown
# Energy Behaviour of Java Concurrency Constructs on Hybrid CPUs

Course project for Green Software Development, University of Twente, 2026.

Replicates and extends Pinto, Castor & Liu (OOPSLA 2014) for JEP 444 virtual
threads on a three-tier hybrid CPU (P / E / LP-E cores).

## Layout
- `harness/`  — Java + JMH benchmarks and the RAPL profiler
- `scripts/`  — environment control and experiment orchestration
- `analysis/` — Python analysis of JMH JSON output
- `paper/`    — LaTeX (ACM `acmart`) report
- `results/`  — measurement output (raw output is gitignored)
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore README.md
git commit -m "chore: initialise project skeleton"
```

---

## Task 1.1: Core topology detection script

Detects P / E / LP-E CPU lists by `cpu_capacity` instead of hardcoding them, so the harness is portable and the paper can report topology automatically.

**Files:**
- Create: `scripts/topology.sh`
- Create: `scripts/test_topology.sh`

- [ ] **Step 1: Write the failing test**

```bash
#!/usr/bin/env bash
# scripts/test_topology.sh
set -euo pipefail
source "$(dirname "$0")/topology.sh"

fail=0
check() {
  if [[ "$2" == "$3" ]]; then echo "PASS: $1"; else echo "FAIL: $1 (got '$2', want '$3')"; fail=1; fi
}

check "P-cores"   "$P_CORES"   "0-5"
check "E-cores"   "$E_CORES"   "6-13"
check "LP-E cores" "$LPE_CORES" "14-15"
check "all cores" "$ALL_CORES" "0-15"
exit $fail
```

- [ ] **Step 2: Run it to verify it fails**

```bash
chmod +x scripts/test_topology.sh && ./scripts/test_topology.sh
```

Expected: FAIL — `topology.sh: No such file or directory`

- [ ] **Step 3: Write `scripts/topology.sh`**

```bash
#!/usr/bin/env bash
# Detects hybrid core classes by scheduler capacity.
# Exports P_CORES, E_CORES, LPE_CORES, ALL_CORES as taskset-compatible ranges.

_collapse() {
  # Turn "0 1 2 3 5" into "0-3,5"
  local nums=($1) out="" start prev
  [[ ${#nums[@]} -eq 0 ]] && { echo ""; return; }
  start=${nums[0]}; prev=${nums[0]}
  for n in "${nums[@]:1}"; do
    if (( n == prev + 1 )); then prev=$n; continue; fi
    if (( start == prev )); then out+="${start},"; else out+="${start}-${prev},"; fi
    start=$n; prev=$n
  done
  if (( start == prev )); then out+="${start}"; else out+="${start}-${prev}"; fi
  echo "$out"
}

declare -A _by_cap
for c in /sys/devices/system/cpu/cpu[0-9]*; do
  n=$(basename "$c" | tr -d 'cpu')
  cap=$(cat "$c/cpu_capacity" 2>/dev/null || echo 0)
  _by_cap[$cap]+="$n "
done

# Sort distinct capacities descending: highest = P, lowest = LP-E
_caps=($(printf '%s\n' "${!_by_cap[@]}" | sort -rn))

_sorted() { printf '%s\n' $1 | sort -n | tr '\n' ' '; }

P_CORES=$(_collapse "$(_sorted "${_by_cap[${_caps[0]}]}")")
if [[ ${#_caps[@]} -ge 3 ]]; then
  E_CORES=$(_collapse "$(_sorted "${_by_cap[${_caps[1]}]}")")
  LPE_CORES=$(_collapse "$(_sorted "${_by_cap[${_caps[2]}]}")")
elif [[ ${#_caps[@]} -eq 2 ]]; then
  E_CORES=$(_collapse "$(_sorted "${_by_cap[${_caps[1]}]}")")
  LPE_CORES=""
else
  E_CORES=""; LPE_CORES=""
fi
ALL_CORES="0-$(($(nproc) - 1))"

export P_CORES E_CORES LPE_CORES ALL_CORES
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
./scripts/test_topology.sh
```

Expected: four `PASS` lines, exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/topology.sh scripts/test_topology.sh
git commit -m "feat: detect hybrid core classes by scheduler capacity"
```

---

## Task 1.2: Grant RAPL read access

`energy_uj` is root-only. Running the whole JVM as root is undesirable (it changes scheduling and pollutes the environment). Use a POSIX ACL instead, reapplied each boot.

**Files:**
- Create: `scripts/enable-rapl.sh`

- [ ] **Step 1: Create the script**

```bash
#!/usr/bin/env bash
# Grants the invoking user read access to RAPL energy counters.
# Must be re-run after every reboot (sysfs is recreated).
set -euo pipefail
USER_NAME="${SUDO_USER:-$USER}"
count=0
for f in /sys/class/powercap/intel-rapl:*/energy_uj; do
  [[ -e "$f" ]] || continue
  sudo setfacl -m "u:${USER_NAME}:r" "$f" && count=$((count+1))
done
echo "Granted read access on $count RAPL domain(s) to ${USER_NAME}"
```

- [ ] **Step 2: Run it**

```bash
chmod +x scripts/enable-rapl.sh && ./scripts/enable-rapl.sh
```

Expected: `Granted read access on 4 RAPL domain(s) to imsounic`

- [ ] **Step 3: Verify a non-root read now succeeds**

```bash
cat /sys/class/powercap/intel-rapl:0/energy_uj
```

Expected: a large integer (microjoules), not `Permission denied`.

**If ACLs are rejected on sysfs** (some kernels refuse them), fall back to:
```bash
sudo chmod a+r /sys/class/powercap/intel-rapl:*/energy_uj
```
and record in the paper that measurements required relaxed sysfs permissions.

- [ ] **Step 4: Commit**

```bash
git add scripts/enable-rapl.sh
git commit -m "feat: script to grant non-root RAPL read access"
```

---

## Task 1.3: Maven project with JMH

**Files:**
- Create: `harness/pom.xml`

- [ ] **Step 1: Create `harness/pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>nl.utwente.gsd</groupId>
  <artifactId>vt-energy</artifactId>
  <version>1.0</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <jmh.version>1.37</jmh.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.openjdk.jmh</groupId>
      <artifactId>jmh-core</artifactId>
      <version>${jmh.version}</version>
    </dependency>
    <dependency>
      <groupId>org.openjdk.jmh</groupId>
      <artifactId>jmh-generator-annprocess</artifactId>
      <version>${jmh.version}</version>
      <scope>provided</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <finalName>benchmarks</finalName>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.5.1</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <finalName>benchmarks</finalName>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>org.openjdk.jmh.Main</mainClass>
                </transformer>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
              </transformers>
              <filters>
                <filter>
                  <artifact>*:*</artifact>
                  <excludes>
                    <exclude>META-INF/*.SF</exclude>
                    <exclude>META-INF/*.DSA</exclude>
                    <exclude>META-INF/*.RSA</exclude>
                  </excludes>
                </filter>
              </filters>
            </configuration>
          </execution>
        </executions>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
```

- [ ] **Step 2: Verify it builds**

```bash
cd harness && mvn -q clean package && ls -la target/benchmarks.jar
```

Expected: `target/benchmarks.jar` exists.

- [ ] **Step 3: Commit**

```bash
cd .. && git add harness/pom.xml && git commit -m "chore: add Maven project with JMH 1.37"
```

---

## Task 1.4: RAPL reader with wraparound handling

The wraparound bug is exactly the defect van Kempen et al. (ASE 2025) found in Pereira et al. Handle it explicitly and test it.

**Files:**
- Create: `harness/src/main/java/nl/utwente/gsd/energy/RaplReader.java`
- Test: `harness/src/test/java/nl/utwente/gsd/energy/RaplReaderTest.java`

- [ ] **Step 1: Write the failing test**

```java
package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class RaplReaderTest {

    @Test
    void deltaHandlesNormalIncrease() {
        assertEquals(500L, RaplReader.delta(1000L, 1500L, 262143328850L));
    }

    @Test
    void deltaHandlesWraparound() {
        // Counter wrapped: end < start
        long max = 262143328850L;
        assertEquals(300L, RaplReader.delta(max - 100L, 200L, max));
    }

    @Test
    void deltaIsZeroWhenUnchanged() {
        assertEquals(0L, RaplReader.delta(42L, 42L, 262143328850L));
    }

    @Test
    void discoversAtLeastOneDomainOnThisMachine() throws Exception {
        RaplReader reader = new RaplReader();
        Map<String, Long> readings = reader.readAll();
        assertFalse(readings.isEmpty(), "expected at least one RAPL domain");
        readings.values().forEach(v -> assertTrue(v >= 0));
    }

    @Test
    void consecutiveReadsAreMonotonicOrWrapped() throws Exception {
        RaplReader reader = new RaplReader();
        Map<String, Long> first = reader.readAll();
        // Burn some CPU so the counter definitely advances
        long sink = 0;
        for (int i = 0; i < 50_000_000; i++) sink += i;
        assertTrue(sink != Long.MIN_VALUE);
        Map<String, Long> second = reader.readAll();
        for (String domain : first.keySet()) {
            long d = reader.deltaFor(domain, first.get(domain), second.get(domain));
            assertTrue(d > 0, "expected positive energy delta for " + domain);
        }
    }
}
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd harness && mvn -q test
```

Expected: compilation failure — `cannot find symbol: class RaplReader`

- [ ] **Step 3: Write the implementation**

```java
package nl.utwente.gsd.energy;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Stream;

/**
 * Reads Intel RAPL energy counters via the Linux powercap sysfs interface.
 *
 * <p>Counters are read on demand only — never polled — because high-frequency
 * RAPL polling suppresses deep C-state residency and inflates idle power
 * (Raffin &amp; Trystram, IEEE TPDS 36(1):96-107, 2025).
 */
public final class RaplReader {

    private final Map<String, Path> domains = new LinkedHashMap<>();
    private final Map<String, Long> maxRange = new LinkedHashMap<>();

    public RaplReader() throws IOException {
        Path base = Path.of("/sys/class/powercap");
        try (Stream<Path> entries = Files.list(base)) {
            entries.filter(p -> p.getFileName().toString().startsWith("intel-rapl:"))
                   .filter(p -> Files.isReadable(p.resolve("energy_uj")))
                   .sorted()
                   .forEach(this::register);
        }
        if (domains.isEmpty()) {
            throw new IOException(
                "No readable RAPL domains found. Run scripts/enable-rapl.sh first.");
        }
    }

    private void register(Path dir) {
        try {
            String name = Files.readString(dir.resolve("name")).trim();
            String key = dir.getFileName().toString() + ":" + name;
            long max = Long.parseLong(
                Files.readString(dir.resolve("max_energy_range_uj")).trim());
            domains.put(key, dir.resolve("energy_uj"));
            maxRange.put(key, max);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** Reads every discovered domain. Values are microjoules. */
    public Map<String, Long> readAll() throws IOException {
        Map<String, Long> out = new LinkedHashMap<>();
        for (Map.Entry<String, Path> e : domains.entrySet()) {
            out.put(e.getKey(), Long.parseLong(Files.readString(e.getValue()).trim()));
        }
        return out;
    }

    /** Energy delta in microjoules for a named domain, correcting for wraparound. */
    public long deltaFor(String domain, long start, long end) {
        Long max = maxRange.get(domain);
        if (max == null) throw new IllegalArgumentException("unknown domain: " + domain);
        return delta(start, end, max);
    }

    /**
     * Energy delta in microjoules, correcting for counter wraparound.
     * Reading only start and end without this correction is the defect
     * van Kempen et al. (ASE 2025) identified in earlier RAPL tooling.
     */
    public static long delta(long start, long end, long maxRange) {
        return end >= start ? end - start : end + maxRange - start;
    }

    public Map<String, Long> maxRanges() {
        return Map.copyOf(maxRange);
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
mvn -q test
```

Expected: all 5 tests pass. If `discoversAtLeastOneDomainOnThisMachine` fails, re-run `../scripts/enable-rapl.sh`.

- [ ] **Step 5: Commit**

```bash
cd .. && git add harness/src && git commit -m "feat: RAPL reader with wraparound correction"
```

---

## Task 1.5: JMH energy profiler

Emits joules and joules-per-operation as JMH secondary results, so energy appears in the same JSON as throughput with no separate bookkeeping.

**Files:**
- Create: `harness/src/main/java/nl/utwente/gsd/energy/RaplProfiler.java`

- [ ] **Step 1: Write the implementation**

```java
package nl.utwente.gsd.energy;

import org.openjdk.jmh.infra.BenchmarkParams;
import org.openjdk.jmh.infra.IterationParams;
import org.openjdk.jmh.profile.InternalProfiler;
import org.openjdk.jmh.profile.ProfilerException;
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
 * JMH profiler that attributes RAPL energy to each measurement iteration.
 * Register with: -prof nl.utwente.gsd.energy.RaplProfiler
 */
public class RaplProfiler implements InternalProfiler {

    private final RaplReader reader;
    private Map<String, Long> start;

    public RaplProfiler() throws ProfilerException {
        try {
            this.reader = new RaplReader();
        } catch (IOException e) {
            throw new ProfilerException("Cannot initialise RAPL: " + e.getMessage());
        }
    }

    @Override
    public String getDescription() {
        return "Intel RAPL energy per iteration (powercap sysfs)";
    }

    @Override
    public void beforeIteration(BenchmarkParams bp, IterationParams ip) {
        try {
            start = reader.readAll();
        } catch (IOException e) {
            throw new IllegalStateException("RAPL read failed at iteration start", e);
        }
    }

    @Override
    public Collection<? extends Result> afterIteration(
            BenchmarkParams bp, IterationParams ip, IterationResult result) {

        Map<String, Long> end;
        try {
            end = reader.readAll();
        } catch (IOException e) {
            throw new IllegalStateException("RAPL read failed at iteration end", e);
        }

        long ops = result.getMetadata().getMeasuredOps();
        List<Result> out = new ArrayList<>();

        for (Map.Entry<String, Long> e : start.entrySet()) {
            String domain = e.getKey();
            Long endValue = end.get(domain);
            if (endValue == null) continue;

            double joules = reader.deltaFor(domain, e.getValue(), endValue) / 1_000_000.0;
            out.add(new ScalarResult("rapl." + domain + ".J",
                    joules, "J", AggregationPolicy.AVG));
            if (ops > 0) {
                out.add(new ScalarResult("rapl." + domain + ".J_per_op",
                        joules / ops, "J/op", AggregationPolicy.AVG));
            }
        }
        return out;
    }
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd harness && mvn -q clean package
```

Expected: BUILD SUCCESS, `target/benchmarks.jar` produced.

- [ ] **Step 3: Commit**

```bash
cd .. && git add harness/src && git commit -m "feat: JMH profiler reporting RAPL energy per operation"
```

---

## Task 1.6: Execution strategies

The four constructs under test, behind one interface so the benchmark body is identical across them. **This is the independent variable.**

**Files:**
- Create: `harness/src/main/java/nl/utwente/gsd/concurrency/ExecutionStrategy.java`
- Test: `harness/src/test/java/nl/utwente/gsd/concurrency/ExecutionStrategyTest.java`

- [ ] **Step 1: Write the failing test**

```java
package nl.utwente.gsd.concurrency;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.*;

class ExecutionStrategyTest {

    @ParameterizedTest
    @EnumSource(ExecutionStrategy.class)
    void runsEveryTaskExactlyOnce(ExecutionStrategy strategy) throws Exception {
        int taskCount = 1000;
        AtomicInteger counter = new AtomicInteger();
        List<Runnable> tasks = IntStream.range(0, taskCount)
                .<Runnable>mapToObj(i -> counter::incrementAndGet)
                .toList();

        strategy.execute(tasks, 4);

        assertEquals(taskCount, counter.get(),
                strategy + " did not run every task exactly once");
    }

    @ParameterizedTest
    @EnumSource(ExecutionStrategy.class)
    void propagatesNoExceptionForEmptyTaskList(ExecutionStrategy strategy) throws Exception {
        assertDoesNotThrow(() -> strategy.execute(List.of(), 4));
    }

    @Test
    void allFourConstructsArePresent() {
        assertEquals(4, ExecutionStrategy.values().length);
    }
}
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd harness && mvn -q test
```

Expected: compilation failure — `cannot find symbol: class ExecutionStrategy`

- [ ] **Step 3: Write the implementation**

```java
package nl.utwente.gsd.concurrency;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;

/**
 * The four Java thread management constructs under comparison.
 *
 * <p>The first three replicate Pinto, Castor &amp; Liu (OOPSLA 2014);
 * VIRTUAL_THREADS is the JEP 444 construct that did not exist in 2014.
 */
public enum ExecutionStrategy {

    /** One platform thread created per task, as in the 2014 "explicit thread creation" arm. */
    PLATFORM_THREADS {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            List<Thread> threads = new ArrayList<>(tasks.size());
            for (Runnable task : tasks) {
                Thread t = new Thread(task);
                threads.add(t);
                t.start();
            }
            for (Thread t : threads) t.join();
        }
    },

    /** Fixed-size platform thread pool (ExecutorService). */
    FIXED_POOL {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            try (ExecutorService pool = Executors.newFixedThreadPool(parallelism)) {
                pool.invokeAll(toCallables(tasks));
            }
        }
    },

    /** Work-stealing Fork-Join pool. */
    FORK_JOIN {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            ForkJoinPool pool = new ForkJoinPool(parallelism);
            try {
                pool.invokeAll(toCallables(tasks));
            } finally {
                pool.shutdown();
            }
        }
    },

    /**
     * JEP 444 virtual threads: one virtual thread per task, multiplexed over a
     * carrier ForkJoinPool. The {@code parallelism} argument is deliberately
     * ignored — carrier count is set by the JVM and controlled in experiments
     * via the system property {@code jdk.virtualThreadScheduler.parallelism}.
     */
    VIRTUAL_THREADS {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
                pool.invokeAll(toCallables(tasks));
            }
        }
    };

    public abstract void execute(List<Runnable> tasks, int parallelism) throws InterruptedException;

    static List<Callable<Void>> toCallables(List<Runnable> tasks) {
        List<Callable<Void>> callables = new ArrayList<>(tasks.size());
        for (Runnable task : tasks) {
            callables.add(() -> { task.run(); return null; });
        }
        return callables;
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
mvn -q test
```

Expected: 9 tests pass (4 strategies × 2 parameterized tests + 1 count test).

- [ ] **Step 5: Commit**

```bash
cd .. && git add harness/src && git commit -m "feat: four concurrency execution strategies"
```

---

## Task 1.7: Workloads (CPU-bound and I/O-bound)

**This is the design decision that decides whether the study is fair.** Virtual threads are designed for blocking work; measuring only CPU-bound workloads would misrepresent them and a reviewer would say so immediately.

**Files:**
- Create: `harness/src/main/java/nl/utwente/gsd/workload/Workloads.java`
- Test: `harness/src/test/java/nl/utwente/gsd/workload/WorkloadsTest.java`

- [ ] **Step 1: Write the failing test**

```java
package nl.utwente.gsd.workload;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class WorkloadsTest {

    @Test
    void cpuBoundProducesRequestedTaskCount() {
        List<Runnable> tasks = Workloads.cpuBound(50, 1000);
        assertEquals(50, tasks.size());
    }

    @Test
    void cpuBoundTasksAreDeterministic() {
        // Same seed and size must produce the same result, so energy differences
        // cannot be attributed to differing amounts of work.
        assertEquals(Workloads.mandelbrotEscapes(64, 0),
                     Workloads.mandelbrotEscapes(64, 0));
    }

    @Test
    void cpuBoundTasksActuallyComputeSomething() {
        assertTrue(Workloads.mandelbrotEscapes(64, 0) > 0);
    }

    @Test
    void ioBoundProducesRequestedTaskCount() {
        List<Runnable> tasks = Workloads.ioBound(30, 1);
        assertEquals(30, tasks.size());
    }

    @Test
    void ioBoundTasksBlockForApproximatelyTheRequestedTime() {
        List<Runnable> tasks = Workloads.ioBound(1, 50);
        long startNanos = System.nanoTime();
        tasks.get(0).run();
        long elapsedMillis = (System.nanoTime() - startNanos) / 1_000_000;
        assertTrue(elapsedMillis >= 45, "expected >=45ms block, got " + elapsedMillis);
    }
}
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd harness && mvn -q test
```

Expected: compilation failure — `cannot find symbol: class Workloads`

- [ ] **Step 3: Write the implementation**

```java
package nl.utwente.gsd.workload;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Deterministic workloads for the concurrency energy study.
 *
 * <p>Two classes are provided because the constructs under test have different
 * design intents: virtual threads target blocking (I/O-bound) work, while
 * Fork-Join targets compute-bound divide-and-conquer work. Measuring only one
 * class would bias the comparison.
 */
public final class Workloads {

    private Workloads() {}

    /**
     * CPU-bound task: counts Mandelbrot escape iterations over a fixed grid.
     * Chosen because it is deterministic, allocation-free, and was part of the
     * benchmark set used by Pinto, Castor &amp; Liu (OOPSLA 2014).
     */
    public static long mandelbrotEscapes(int resolution, int offset) {
        final int maxIter = 500;
        long escapes = 0;
        for (int py = 0; py < resolution; py++) {
            double y0 = (py + offset) * 2.0 / resolution - 1.0;
            for (int px = 0; px < resolution; px++) {
                double x0 = px * 3.0 / resolution - 2.0;
                double x = 0.0, y = 0.0;
                int iter = 0;
                while (x * x + y * y <= 4.0 && iter < maxIter) {
                    double xt = x * x - y * y + x0;
                    y = 2.0 * x * y + y0;
                    x = xt;
                    iter++;
                }
                escapes += iter;
            }
        }
        return escapes;
    }

    /** Builds {@code taskCount} identical CPU-bound tasks of the given grid resolution. */
    public static List<Runnable> cpuBound(int taskCount, int resolution) {
        List<Runnable> tasks = new ArrayList<>(taskCount);
        for (int i = 0; i < taskCount; i++) {
            final int offset = i;
            tasks.add(() -> {
                long result = mandelbrotEscapes(resolution, offset);
                if (result == Long.MIN_VALUE) throw new AssertionError("unreachable");
            });
        }
        return tasks;
    }

    /**
     * I/O-bound task: blocks for a fixed duration.
     *
     * <p>{@link Thread#sleep} is a genuine blocking operation that causes a
     * virtual thread to unmount from its carrier, which is precisely the
     * mechanism under study, and it makes latency an exactly controlled
     * independent variable. Task 3.2 adds a real-socket variant to address the
     * external-validity threat this introduces.
     */
    public static List<Runnable> ioBound(int taskCount, int blockMillis) {
        List<Runnable> tasks = new ArrayList<>(taskCount);
        for (int i = 0; i < taskCount; i++) {
            tasks.add(() -> {
                try {
                    Thread.sleep(blockMillis);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
        }
        return tasks;
    }

    /** Mixed workload: a fraction of tasks block, the remainder compute. */
    public static List<Runnable> mixed(int taskCount, int resolution, int blockMillis, double blockingFraction) {
        List<Runnable> tasks = new ArrayList<>(taskCount);
        for (int i = 0; i < taskCount; i++) {
            final int offset = i;
            final boolean blocking = (i / (double) taskCount) < blockingFraction;
            tasks.add(() -> {
                if (blocking) {
                    try { Thread.sleep(blockMillis); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                } else {
                    long r = mandelbrotEscapes(resolution, offset);
                    if (r == Long.MIN_VALUE) throw new AssertionError("unreachable");
                }
            });
        }
        return tasks;
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
mvn -q test
```

Expected: 5 workload tests pass, plus the earlier 14.

- [ ] **Step 5: Commit**

```bash
cd .. && git add harness/src && git commit -m "feat: CPU-bound, I/O-bound and mixed workloads"
```

---

## Task 1.8: The JMH benchmark

**Files:**
- Create: `harness/src/main/java/nl/utwente/gsd/ConcurrencyEnergyBenchmark.java`

- [ ] **Step 1: Write the benchmark**

```java
package nl.utwente.gsd;

import nl.utwente.gsd.concurrency.ExecutionStrategy;
import nl.utwente.gsd.workload.Workloads;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

import java.util.List;
import java.util.concurrent.TimeUnit;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@State(Scope.Benchmark)
@Fork(value = 5, jvmArgs = {"-Xms2g", "-Xmx2g"})
@Warmup(iterations = 10, time = 1)
@Measurement(iterations = 20, time = 1)
public class ConcurrencyEnergyBenchmark {

    @Param({"PLATFORM_THREADS", "FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"})
    public ExecutionStrategy strategy;

    /** Concurrency level; sweeps the "Lambda curve" from the 2014 baseline. */
    @Param({"1", "2", "4", "8", "16", "32", "64", "128"})
    public int parallelism;

    @Param({"CPU", "IO"})
    public String workloadType;

    private List<Runnable> tasks;

    @Setup(Level.Trial)
    public void setUp() {
        // Task count is held constant so total work is identical across all
        // levels of `parallelism`; only the degree of concurrency varies.
        tasks = switch (workloadType) {
            case "CPU" -> Workloads.cpuBound(256, 128);
            case "IO"  -> Workloads.ioBound(256, 10);
            default -> throw new IllegalArgumentException("unknown workload: " + workloadType);
        };
    }

    @Benchmark
    public void execute(Blackhole bh) throws InterruptedException {
        strategy.execute(tasks, parallelism);
        bh.consume(tasks.size());
    }
}
```

### ⚠️ Known design issue — resolve before the full experiment

`parallelism` does **not** mean the same thing for all four arms, and the code above quietly hides that:

| Strategy | What `parallelism` controls | Meaningful in the sweep? |
|---|---|---|
| `FIXED_POOL` | pool size | ✅ yes |
| `FORK_JOIN` | pool parallelism | ✅ yes |
| `VIRTUAL_THREADS` | **nothing** — one vthread per task; carrier count comes from `-Djdk.virtualThreadScheduler.parallelism` | ⚠️ only via JVM flag |
| `PLATFORM_THREADS` | **nothing** — one thread per task, always 256 threads | ❌ no-op |

Sweeping `parallelism` against `PLATFORM_THREADS` therefore re-runs an identical configuration eight times. Two defensible fixes:

- **(a) Natural-usage design** (recommended): keep one-thread-per-task for `PLATFORM_THREADS` as the naive baseline, exclude it from the parallelism sweep, and control virtual-thread carriers via the JVM flag in a separate `@Fork` arm. Matches how each construct is actually used.
- **(b) Chunked design**: split the work into exactly `parallelism` chunks for all four arms. Closer to the 2014 paper's thread-count sweep, but it defeats the point of virtual threads, whose design intent is many more threads than cores.

Pick one in Task 3.1 and **state the choice and its rationale in the paper** — a reviewer will ask. Run the pilot with (a).

- [ ] **Step 2: Build**

```bash
cd harness && mvn -q clean package
```

Expected: BUILD SUCCESS.

- [ ] **Step 3: Smoke-test a single configuration with the energy profiler**

```bash
java -jar target/benchmarks.jar \
  -prof nl.utwente.gsd.energy.RaplProfiler \
  -p strategy=VIRTUAL_THREADS -p parallelism=8 -p workloadType=IO \
  -f 1 -wi 2 -i 3 -foe true
```

Expected output includes secondary result lines such as:
```
rapl.intel-rapl:0:package-0.J        ≈ some positive number
rapl.intel-rapl:0:package-0.J_per_op ≈ some positive number
rapl.intel-rapl:1:psys.J             ≈ some positive number
```

**If energy values are 0.0:** RAPL access was lost — re-run `../scripts/enable-rapl.sh`.

- [ ] **Step 4: Commit**

```bash
cd .. && git add harness/src && git commit -m "feat: JMH benchmark sweeping strategy x parallelism x workload"
```

---

## Task 1.9: Pilot run — the number that goes in the proposal

**Files:**
- Create: `scripts/pilot.sh`
- Create: `results/pilot/` (gitignored contents, directory tracked)

- [ ] **Step 1: Write the pilot script**

```bash
#!/usr/bin/env bash
# Small pilot: 4 strategies x 2 workloads at fixed parallelism, unpinned.
# Purpose: prove the pipeline works and produce a feasibility number for the
# Assignment 1 proposal. NOT the full experiment.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results/pilot

./scripts/enable-rapl.sh

java -jar harness/target/benchmarks.jar \
  -prof nl.utwente.gsd.energy.RaplProfiler \
  -p parallelism=8 \
  -f 2 -wi 5 -i 10 \
  -rf json -rff results/pilot/pilot.json \
  -foe true

echo "Pilot complete: results/pilot/pilot.json"
```

- [ ] **Step 2: Run the pilot**

```bash
chmod +x scripts/pilot.sh && ./scripts/pilot.sh
```

Expected: runtime roughly 20–40 minutes; produces `results/pilot/pilot.json`.

- [ ] **Step 3: Extract the headline numbers**

```bash
python3 - <<'PY'
import json
rows = json.load(open("results/pilot/pilot.json"))
print(f"{'strategy':<18}{'workload':<10}{'ms/op':>10}{'J/op (pkg)':>14}")
for r in rows:
    p = r["params"]
    ms = r["primaryMetric"]["score"]
    sec = r["secondaryMetrics"]
    key = next((k for k in sec if "package-0.J_per_op" in k), None)
    j = sec[key]["score"] if key else float("nan")
    print(f"{p['strategy']:<18}{p['workloadType']:<10}{ms:>10.3f}{j:>14.6f}")
PY
```

Expected: eight rows (4 strategies × 2 workloads) with non-zero energy values.

- [ ] **Step 4: Commit the pilot result**

```bash
git add scripts/pilot.sh
git add -f results/pilot/pilot.json
git commit -m "feat: pilot run demonstrating end-to-end energy measurement"
```

**Phase 1 exit criterion:** you can state one sentence in the proposal such as *"A pilot measurement on the target platform recorded X J/op for virtual threads versus Y J/op for a fixed thread pool on an I/O-bound workload, confirming the measurement pipeline is operational."* Almost no group does this. It converts a plausible proposal into a de-risked one.

---

# PHASE 2 — Assignment 1 Report (target: 1.5 weeks)

## Task 2.1: Related work matrix

**Files:**
- Create: `paper/related-work.md`

- [ ] **Step 1: Build the matrix**

Create a table with one row per paper and columns: *Constructs covered · JDK · Hardware · Instrumentation · Energy measured? · Hybrid cores? · Limitation we exploit*.

Seed it with these **verified** entries (re-verify every DOI before citing — these came from automated search):

| Paper | Key fact | Limitation to exploit |
|---|---|---|
| Pinto, Castor & Liu, **OOPSLA 2014**, DOI `10.1145/2714064.2660235` | 3 constructs, JDK 1.7, 2×16-core AMD Opteron, external NI DAQ meters, `ondemand` governor | No virtual threads; homogeneous cores; no RAPL; DVFS-confounded |
| Shimchenko, Österlund & Wrigstad, **Programming Journal 8(3):10, 2024**, DOI `10.22152/programming-journal.org/2024/8/10` | ZGC worker placement on Alder Lake 8P+8E, RAPL, ~3% savings | GC runtime threads only; **zero** mentions of virtual threads/Fork-Join/pools; two core tiers, not three |
| van Kempen, Kwon, Nguyen & Berger, **ASE 2025**, DOI `10.1109/ASE63991.2025.00131` | Language implementation has no energy effect beyond execution time; corrects real RAPL bugs in Pereira et al. | Explicitly excludes *"architectures mixing energy-saving and high-performance cores"* — **quote this as the gap** |
| Kim, Imes & Hoffmann, **CPSNA 2015**, IEEE Xplore `7272689` | Race-to-idle costs up to 3.34× optimal energy; worst on the *lowest* idle-power platform | DVFS under deadlines, not language constructs |
| Aragon-Jurado et al., **Sustainable Computing 47:101166, 2025**, DOI `10.1016/j.suscom.2025.101166` | 9% faster, **34% more energy** — peer-reviewed "faster ≠ greener" | iOS/Swift compiler flags, not concurrency |
| Raffin & Trystram, **IEEE TPDS 36(1):96–107, 2025** | High-frequency RAPL polling suppresses C-states; +48.6 W at 1 kHz | Methodological control we adopt |
| S. Kumar et al., **Scientific Reports**, DOI `10.1038/s41598-026-40112-6` | Only paper measuring virtual-thread energy | 2 arms only; microcontroller; **cite as unreplicated, do NOT cite its 42% figure** — claims OpenJDK 21 + ZGC in 192 KB SRAM, which is not possible |

- [ ] **Step 2: Verify every citation resolves**

For each DOI, confirm it resolves to the stated title and authors. Delete anything that does not. A fabricated citation is an academic-integrity problem, not a typo.

- [ ] **Step 3: Commit**

```bash
git add paper/related-work.md && git commit -m "docs: related work matrix with verified citations"
```

---

## Task 2.2: GQM tree

**Files:**
- Create: `paper/gqm.md`

- [ ] **Step 1: Write the general goal in the required template**

```
Analyze        Java thread management constructs (platform threads, fixed thread
               pools, Fork-Join, and virtual threads)
For the purpose of  characterising
With respect to     their energy consumption and its relationship to execution time
From the point of view of  Java developers
In the context of   hybrid processors combining performance, efficiency and
                    low-power-efficiency cores.
```

- [ ] **Step 2: Write the three specific goals, each with questions and metrics**

**G1 — Re-establish the baseline.** *Analyze the relationship between concurrency level and energy … for the purpose of evaluating whether the 2014 "Lambda curve" persists …*
- **Q1.1** Does energy still rise then fall with thread count on hybrid cores under `intel_pstate`/HWP?
- **Q1.2** Is sequential execution still the lowest-energy option for most workloads?
- **M:** package energy (J), core energy (J), psys energy (J), execution time (s), J/op, energy-delay product

**G2 — Position the new construct.** *Analyze virtual threads against the three 2014 constructs … with respect to energy … *
- **Q2.1** How does virtual-thread energy compare per workload class (CPU-bound vs I/O-bound)?
- **Q2.2** At what concurrency level, if any, do virtual threads become the lowest-energy construct?
- **M:** J/op per (strategy × parallelism × workload), throughput (ops/s), Cliff's delta vs the fixed-pool baseline

**G3 — Expose the scheduler's asymmetry blindness.** *Analyze carrier-thread core placement … from the point of view of runtime implementers …*
- **Q3.1** Does pinning to P / E / LP-E cores significantly change energy per unit of work?
- **Q3.2** How much energy does the JVM's asymmetry-unaware scheduler leave on the table versus the best fixed placement?
- **M:** J/op per core class, time-to-completion penalty (%), energy saving of best placement vs unpinned (%)

- [ ] **Step 2b: Draw the tree as a figure** (goal → questions → metrics). Very few groups do this; it reads as rigour.

- [ ] **Step 3: Commit**

```bash
git add paper/gqm.md && git commit -m "docs: GQM tree with general and specific goals"
```

---

## Task 2.3: ACM paper skeleton

**Files:**
- Create: `paper/main.tex`
- Create: `paper/refs.bib`
- Create: `paper/Makefile`

- [ ] **Step 1: Create `paper/main.tex`**

```latex
\documentclass[sigconf,nonacm]{acmart}

\begin{document}

\title{Energy Behaviour of Java Thread Management Constructs on Hybrid Processors}

\author{Sounic Raj Akkaraju}
\affiliation{\institution{University of Twente}\country{The Netherlands}}
% Add co-authors here.
\thanks{Author contributions: ...}   % REQUIRED by the assignment brief.

\begin{abstract}
% 150-200 words: problem, gap, what we will measure, why it matters.
\end{abstract}

\maketitle

\section{Introduction}
% Topic, problem, gap in one bold sentence, how an experiment addresses it,
% document roadmap.

\section{Context}
% Technical: JVM concurrency constructs; hybrid P/E/LP-E architectures; RAPL.
% Societal: five-dimension model (Becker et al., Karlskrona Manifesto).
% Name at least one TENSION between dimensions -- this is the single clearest
% signal of a top-grade report.

\section{Related Work}
% 5-10 studies. Each gets a stated LIMITATION. Include the comparison table.

\section{Methodology}
% GQM tree, general + specific goals, questions, preliminary metrics,
% expected results and impact.

\section{Concluding Remarks}
% Wrap-up and next steps.

\bibliographystyle{ACM-Reference-Format}
\bibliography{refs}

\end{document}
```

- [ ] **Step 2: Create `paper/Makefile`**

```makefile
main.pdf: main.tex refs.bib
	pdflatex main
	bibtex main
	pdflatex main
	pdflatex main

clean:
	rm -f *.aux *.bbl *.blg *.log *.out main.pdf

.PHONY: clean
```

- [ ] **Step 3: Verify it builds**

```bash
cd paper && make
```

Expected: `main.pdf` is produced. If `acmart.cls` is missing: `sudo pacman -S texlive-publishers`.

- [ ] **Step 4: Commit**

```bash
cd .. && git add paper/ && git commit -m "docs: ACM paper skeleton"
```

---

## Task 2.4: Write the report

- [ ] **Step 1: Introduction** — lead with the gap as one bold, falsifiable sentence: *"No study has measured the energy consumption of JEP 444 virtual threads against platform thread pools, Fork-Join, or reactive frameworks, and none has done so on a processor combining performance and efficiency cores."*
- [ ] **Step 2: Context** — walk all five sustainability dimensions and name a tension. Suggested: virtual threads improve *individual* sustainability (developer productivity: simple blocking code scales) and *technical* sustainability (maintainability vs callback-heavy async), but may worsen *environmental* sustainability if cheap threads encourage over-parallelism that raises active core count and package power.
- [ ] **Step 3: Related Work** — the matrix from Task 2.1, prose plus table, every entry ending in a limitation.
- [ ] **Step 4: Methodology** — GQM tree from Task 2.2, plus the pilot number from Task 1.9 as a feasibility demonstration.
- [ ] **Step 5: Concluding remarks** — next steps mapping to Assignments 2 and 3.
- [ ] **Step 6: Check the page limit** — 3–4 pages of content plus 1 page of references. Do not exceed.
- [ ] **Step 7: Add the author-contribution footnote** — explicitly required by the brief and easy to forget.
- [ ] **Step 8: Commit**

```bash
git add paper/main.tex paper/refs.bib && git commit -m "docs: complete Assignment 1 report"
```

---

## Task 2.5: Presentation (20% of the Assignment 1 grade)

- [ ] **Step 1** — Build ~8 slides: problem · gap (one sentence) · why now (virtual threads 2023 + hybrid cores 2021) · the 2014 baseline and what changed · design · GQM · pilot number · expected impact.
- [ ] **Step 2** — Lead with the strongest line: *"Java's scheduler doesn't know your CPU has three different kinds of core."*
- [ ] **Step 3** — Rehearse against the time limit once slots are announced on Canvas.
- [ ] **Step 4: Commit**

```bash
git add paper/slides/ && git commit -m "docs: Assignment 1 presentation"
```

---

# PHASE 3 — Assignment 2: Experiment Plan (outline)

Full detail to be expanded once Assignment 1 is submitted.

- [ ] **Task 3.1** — Formal variable specification: independent (strategy, parallelism, workload class, core placement), dependent (J, s, W, J/op, EDP, ops/s), controlled (governor, turbo, thermal state, JDK version, background load).
- [ ] **Task 3.2** — Add a real-socket I/O workload to address the `Thread.sleep` external-validity threat from Task 1.7.
- [ ] **Task 3.3** — Add core-pinning arms via `taskset -c "$P_CORES"` / `"$E_CORES"` / `"$LPE_CORES"` / `"$ALL_CORES"`, plus a carrier-parallelism arm using `-Djdk.virtualThreadScheduler.parallelism=N`.
- [ ] **Task 3.4** — Idle-baseline protocol: measure RAPL over a 60 s no-load window before each batch; report both raw and idle-subtracted energy.
- [ ] **Task 3.5** — Power analysis from pilot variance to justify repetition count.
- [ ] **Task 3.6** — Threats to validity: internal (thermal drift, HWP non-determinism, JIT), external (one workload family, two machines), construct (`Thread.sleep` as I/O proxy; RAPL excludes network/disk), conclusion (non-normal data → non-parametric tests).
- [ ] **Task 3.7** — Pre-register hypotheses. Prevents the HARKing trap that produced the race-to-idle artifact in the NPU literature.

---

# PHASE 4 — Assignment 3: Execute and Analyse (outline)

- [ ] **Task 4.1** — Full matrix overnight: 4 strategies × 8 parallelism levels × 2 workloads × 4 placements. Estimate runtime from the pilot; split into batches with cooldowns.
- [ ] **Task 4.2** — Replicate key conditions on the Mac Mini M4 via `powermetrics` (cross-ISA arm).
- [ ] **Task 4.3** — Analysis in `analysis/analyse.py`: Kruskal–Wallis + Dunn post-hoc, Cliff's delta effect sizes, **TOST equivalence testing** if differences are null.
- [ ] **Task 4.4** — Figures: Lambda curves per strategy; J/op heatmap over strategy × placement; energy-vs-time scatter testing "faster = greener".
- [ ] **Task 4.5** — Replication package: code, raw JSON, analysis scripts, environment manifest (kernel, JDK, governor, microcode).
- [ ] **Task 4.6** — Final report and presentation.

---

## Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| RAPL ACL lost on reboot | High | `scripts/enable-rapl.sh` re-run at the top of every experiment script |
| HWP causes non-deterministic frequencies | Medium | Report governor; consider pinning `min_perf_pct`/`max_perf_pct`; run a fixed-frequency sensitivity arm |
| Thermal throttling across long batches | Medium | Cooldown between batches; log `coretemp`; discard runs exceeding a temperature threshold |
| `Thread.sleep` criticised as unrepresentative I/O | High | Task 3.2 adds a real-socket workload; declare it as a construct-validity threat regardless |
| Someone publishes this first | Low | Re-run the arXiv/DBLP sweep before submission |
| `psys` unavailable after a firmware update | Low | Fall back to package + core + uncore; report the change |

## Self-Review Notes

- **Spec coverage:** every section the brief requires (Introduction, Context, Related Work, Methodology, Concluding remarks, contribution footnote, presentation) has a task in Phase 2.
- **Naming consistency:** `RaplReader.deltaFor(domain, start, end)` is the instance method; `RaplReader.delta(start, end, maxRange)` is the static one — both are used as defined in Tasks 1.4 and 1.5.
- **Known gap:** the Assignment 1 deadline is not in any local file. Confirm on Canvas (`canvas.utwente.nl/courses/17443`) and back-plan Phases 1–2 from it.
