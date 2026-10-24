# Assignment 3: Experiment Implementation (Part B, B1–B9) Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build everything the A2 report (submitted 2 Oct, `paper/sec-*.tex`) says will be run, so that the Intel arm can run unattended first and the Mac arm afterwards. Deadline for A3 (results, final report, replication package, presentation): **Fri 30 Oct 2026**.

**Architecture:**
- The JMH harness gains SEQUENTIAL, a recursive Fork/Join, VT carrier control, and the SLEEP/SOCKET workloads, with an out-of-process NIO delay server.
- One platform-neutral, standard-library Python orchestrator (`scripts/run_experiment.py`) builds the randomized schedule. It runs one JMH fork per invocation, inside batches bracketed by gated idle baselines, and it can resume.
- A pandas/SciPy analysis package implements §4.6 of the report exactly. It has unit tests on synthetic data.
- Ancillary experiments are small Java mains plus shell wrappers.

**Tech Stack:**
- Java: Temurin 25.0.4.1 (`~/.local/opt/jdk-25` on Intel; Homebrew `openjdk@25` on the Mac), JMH 1.37, Maven 3.9.16 (mise).
- Python: Python 3.14. The orchestrator uses the standard library only. Analysis uses `.venv` with pandas, scipy, scikit-posthocs, and matplotlib.

**Order:** the user first decided (24 Oct) on all Intel runs first. Later that day it was changed to **Mac first, then Intel**: the laptop is in daily use, so its campaign runs at night across two nights. See `docs/a3-handoff.md`.

---

## Ground truth (24 Oct, do not re-derive)

- **Repo state:** branch `assignment-3` is cut from `assignment-2` (`578d6c5`). Nothing of Part B existed. 35 tests ran on JDK 25: the only 2 errors are `RaplReaderTest` hardware tests, because RAPL is root-only until `sudo scripts/enable-rapl.sh` runs (once per boot).
- **Intel topology** (`scripts/topology.sh`): P = 0–5, E = 6–13, LP-E = 14–15. PMUs are `cpu_core`, `cpu_atom`, `cpu_lowpower`.
  - `perf` is **not installed** (`sudo pacman -S perf`), and `perf_event_paranoid` = 2.
  - The ephemeral port range is 32768–60999 and `somaxconn` = 4096.
  - cpufreq exposes `cpuinfo_avg_freq` (APERF/MPERF based).
- **Mac pilot idle CPU power** was 0.0296 W at the start and 0.0202 W at the end (32 % apart, both quiet). AMCC agreed within 1 %. A pure 10 % rule on `CPU_Energy` would discard every Mac batch (see A3-D9).
- **Metric keys:**
  - Intel: `rapl.intel-rapl:0:package-0.J[_per_op]`, `rapl.intel-rapl:0:0:core`, `rapl.intel-rapl:0:1:uncore`, `rapl.intel-rapl:1:psys`, `rapl.window_s`.
  - Mac: `ioreport.CPU_Energy`, `ioreport.ECPU`, `ioreport.PCPU`, `ioreport.DRAM`, `ioreport.AMCC`, `ioreport.DCS`, …, `ioreport.window_s`.
- Pass VT flags with `-jvmArgsAppend`, never `-jvmArgs`. `-jvmArgs` replaces the `@Fork` flags (A2 execution log).

## Design decisions for A3 (deviations from A2 text are marked ⚠ and must be stated in the final report)

| # | Decision | Why |
|---|---|---|
| A3-D1 | Intel campaign = Exp 1 (69 cells) + equal-count placement arm (2P/2E/2LP-E × 8 cells × 3 workloads = 72 cells), 5 forks each = 705 runs. Then the H0-1.2 confirmation stage (A3-D6). Mac = Exp 1 + Exp 2 (93 cells × 10 forks = 930 runs). | Report §4.5 |
| A3-D2 ⚠ | FJ = `RecursiveAction` halving the task list down to single tasks, in `new ForkJoinPool(p, defaultFactory, null, false, p, p, 1, pool -> true, 60 s)`. **maximumPoolSize = p and saturate → true**, so joins never spawn compensation threads. | It guarantees that p is the worker count (Table 2) and the ⌈256/p⌉×d floor. On JDK 25 the default pool did not compensate in this workload, so the cap is a safeguard (see the execution log). |
| A3-D3 | VT carriers: `-Djdk.virtualThreadScheduler.parallelism=p -Djdk.virtualThreadScheduler.maxPoolSize=p` via `-jvmArgsAppend`. The benchmark **fails at setup** if strategy = VT and the property ≠ `parallelism`, and it prints `VT carriers = p` (the B3 acceptance "run log shows the carrier count"). SEQ and PT runs pass `parallelism=1`, a placeholder that analysis ignores. | B3 |
| A3-D4 | SOCKET client: blocking `java.net.Socket` to 127.0.0.1, write 64 B, `readNBytes(64)`, then close with **SO_LINGER 0** (RST, no TIME_WAIT). Server: separate JVM `SocketDelayServer <port> <delayMs>`, single-threaded NIO selector, backlog 1024, reply 10 ms after the 64th byte, then close. The server writes `{"requests":…, "cpu_s":…}` on SIGTERM. | VT at about 12 ms/op opens about 20 k connections/s. With TIME_WAIT (60 s) the 28 k-port ephemeral range would be exhausted within seconds. |
| A3-D4b | Server lifetime = one batch: started before the batch's start idle baseline, stopped after the end baseline. Intel: `taskset -c 13`, the last E core, outside the 2E arm (6,7). Mac: default QoS. The Mac requires `kern.ipc.somaxconn ≥ 1024` (the default of 128 overflows with 256 simultaneous connects); the runner checks this. | Constant overhead, included in both idle baselines |
| A3-D5 | Intel placement: `taskset -c <cores>` wraps the JMH host JVM, and the forked benchmark JVM inherits the affinity. 2P = first two P cores, 2E = first two E cores, 2LP-E = both LP-E cores, all read from `topology.sh` at runtime. Mac BACKGROUND: `-jvm scripts/mac/bg-java.sh` (exec `taskpolicy -b java "$@"`). | Report §4.4/§5.3 |
| A3-D6 ⚠ | **Intel H0-1.2 by confirmation stage.** With 5 forks the fork-index split would give 2 vs 3 forks, and Mann-Whitney U's minimum two-sided p is then 0.2, so the test could never reject. The process: (1) `analysis.select_best --platform intel` picks, per workload, the lowest-median concurrent configuration from all Exp-1 forks; (2) the runner executes 5 fresh forks of SEQ and of that configuration (30 runs, `--campaign confirm --cells-file`); (3) H0-1.2 is tested on the fresh forks only. The Mac keeps the fork 1–5 / 6–10 split. | Selection and test stay on disjoint data, as in the report |
| A3-D7 | Frequency per iteration (Intel): `RaplProfiler` appends, at the iteration-end boundary only (no polling), the mean `cpuinfo_avg_freq` per core class (`freq.P_MHz`, `freq.E_MHz`, `freq.LPE_MHz`). Unreadable (idle) CPUs are skipped, and `scaling_cur_freq` is the fallback. Regime flag (analysis): an iteration whose primary J deviates > 10 % from its fork median. | Report §5.3 |
| A3-D8 | Layout `results/<platform>/<campaign>/`: `schedule.csv` (planned runs, seed), `progress.csv` (appended status rows), `runs/<run_id>.json` + `.log`, `batches/<batch_id>/{env-start.txt, env-end.txt, idle-start.json, idle-end.json, server.json, powermetrics.txt}`. A resumed run skips every run_id whose latest status is `ok`. | B5, B9 |
| A3-D9 ⚠ | Idle agreement: \|end − start\| ≤ max(rel × start, abs). Intel: rel 0.10, abs 0 on package. Mac: rel 0.10, **abs 0.010 W** on `CPU_Energy`, about half the quiet-Mac idle level and far below any treatment's CPU power. A failed batch is re-queued once at the end of the schedule; if it fails again it is kept and flagged `idle_mismatch`. | The pilot showed a 32 % spread on quiet Mac idle (ground truth) |
| A3-D10 | Quiet gate per run: up to 30 attempts 20 s apart (10 min). Then the campaign stops cleanly and can be resumed. Cooldown is ≥ 10 s; on the Mac it waits until the last `powermetrics` thermal line reads `Nominal` (max 120 s). | Unattended overnight runs |
| A3-D11 | Profiling is a separate campaign (`--mode profile`, 2 forks per selected cell). It uses `-prof jfr` and, on Linux when `perf` is installed, `-prof perf` for context switches, migrations, and cycles per PMU. It never runs during energy campaigns. | Report §5.4 |
| A3-D12 | SOCKET server-only overhead (the report's "server-only run"): idle baseline with vs without the server, plus server CPU seconds per request from `server.json`. | Report §4.3 |

## File structure

**Created**
- `harness/src/main/java/nl/utwente/gsd/workload/SocketDelayServer.java`: NIO delay server (main)
- `harness/src/main/java/nl/utwente/gsd/energy/CpuFreq.java`: per-class frequency snapshot (Linux)
- `harness/src/main/java/nl/utwente/gsd/tools/LoadProbe.java`: k busy threads for s seconds, energy per domain → JSON (AX3, AX4, AX6)
- `harness/src/main/java/nl/utwente/gsd/tools/LatencyCalibration.java`: sleep latency per thread kind, socket RTT (AX5)
- `harness/src/test/java/nl/utwente/gsd/workload/SocketDelayServerTest.java`, `.../energy/CpuFreqTest.java`, `.../ConcurrencyEnergyBenchmarkTest.java`, `.../tools/LatencyCalibrationTest.java`
- `scripts/run_experiment.py` (stdlib only), `scripts/test_run_experiment.py`
- `scripts/mac/bg-java.sh`
- `scripts/ancillary/{ax2-refresh-overhead.sh, ax3-readpath.sh, ax4-load-scaling.sh, ax5-latency.sh, ax6-ecore.sh, srv-overhead.sh}`
- `analysis/vtenergy/{__init__.py, load.py, stats.py, hypotheses.py, figures.py, select_best.py, ancillary.py}`, `analysis/analyse.py`, `analysis/tests/test_*.py`, `analysis/requirements.txt`
- `docs/replication.md`

**Modified**
- `ExecutionStrategy.java` (SEQUENTIAL, recursive FJ), `Workloads.java` (rename `ioBound` → `sleep`, add `socket`), `ConcurrencyEnergyBenchmark.java` (params, carrier check, SOCKET port), `EnergyProfiler.java` (`extraResults` hook), `RaplProfiler.java` (frequency), the tests, `README.md`, `.gitignore`

---

## Task 1 (B1, B2): SEQUENTIAL and recursive, bounded Fork/Join

**Files:** Modify `ExecutionStrategy.java`, `ExecutionStrategyTest.java`

- [ ] **Step 1: tests first.** In `ExecutionStrategyTest`:
  - `allFiveConstructsArePresent` (5 values, SEQUENTIAL first).
  - `sequentialRunsInCallerThread` (every task sees `Thread.currentThread()` == the caller).
  - `forkJoinUsesForkJoinTasks` (inside a task, `ForkJoinTask.inForkJoinPool()` is true and `ForkJoinTask.getPool().getParallelism() == p`).
  - `@ParameterizedTest(FIXED_POOL, FORK_JOIN) boundedPoolsRespectConcurrencyLevel`: 8 tasks of `Thread.sleep(50)` at p = 2 take ≥ 190 ms, and the observed maximum concurrency (AtomicInteger high-water mark) is ≤ 2.
  - The existing parameterized tests now cover 5 constructs.
- [ ] **Step 2:** run `mvn -q test -Dtest=ExecutionStrategyTest`. Expected: compile failure (no SEQUENTIAL).
- [ ] **Step 3: implement.**

```java
SEQUENTIAL {
    @Override
    public void execute(List<Runnable> tasks, int parallelism) {
        for (Runnable task : tasks) task.run();
    }
},
...
FORK_JOIN {
    @Override
    public void execute(List<Runnable> tasks, int parallelism) {
        if (tasks.isEmpty()) return;
        try (ForkJoinPool pool = boundedForkJoinPool(parallelism)) {
            pool.invoke(new Split(tasks, 0, tasks.size()));
        }
    }
},

/** maximumPoolSize = parallelism and saturate -> true: joins never add compensation threads (A3-D2). */
static ForkJoinPool boundedForkJoinPool(int parallelism) {
    return new ForkJoinPool(parallelism, ForkJoinPool.defaultForkJoinWorkerThreadFactory, null,
            false, parallelism, parallelism, 1, pool -> true, 60, TimeUnit.SECONDS);
}

/** Recursive halving down to single tasks, as Fork/Join is designed to be used. */
static final class Split extends RecursiveAction {
    private final List<Runnable> tasks; private final int lo, hi;
    Split(List<Runnable> tasks, int lo, int hi) { this.tasks = tasks; this.lo = lo; this.hi = hi; }
    @Override protected void compute() {
        if (hi - lo == 1) { tasks.get(lo).run(); return; }
        int mid = (lo + hi) >>> 1;
        invokeAll(new Split(tasks, lo, mid), new Split(tasks, mid, hi));
    }
}
```

- [ ] **Step 4:** run `mvn -q test -Dtest=ExecutionStrategyTest`. Expected: all pass.

## Task 2 (B4): SLEEP rename, SOCKET workload, SocketDelayServer

**Files:** Modify `Workloads.java`, `WorkloadsTest.java`; create `SocketDelayServer.java`, `SocketDelayServerTest.java`

- [ ] **Step 1: tests first.** `SocketDelayServerTest` starts the server in-process on an ephemeral port: `SocketDelayServer.start(0, 10)` returns a handle with `port()` and `close()`. It then checks:
  - `oneRoundTripTakesAtLeastTheDelay`: one `Workloads.socket(1, port)` task takes ≥ 10 ms (the B4 acceptance).
  - `replyHas64Bytes`.
  - `handles256ConcurrentClients`: `VIRTUAL_THREADS.execute(Workloads.socket(256, port), 0)` completes within 2 s, and the server's `requests()` == 256.
  - `repeatedOperationsDoNotExhaustPorts`: 20 × 256 sequential-batch connections complete, which shows the SO_LINGER 0 effect.

  `WorkloadsTest`: rename the `ioBound*` tests to `sleep*`.
- [ ] **Step 2:** the tests fail (no class).
- [ ] **Step 3: implement.**
  - `Workloads.sleep(taskCount, blockMillis)`, the renamed `ioBound`.
  - `Workloads.socket(taskCount, port)`: each task does `try (Socket s = new Socket()) { s.setSoLinger(true, 0); s.setTcpNoDelay(true); s.connect(new InetSocketAddress(InetAddress.getLoopbackAddress(), port)); s.getOutputStream().write(PAYLOAD); byte[] r = s.getInputStream().readNBytes(64); if (r.length != 64) throw new IOException("short reply"); }`. IOExceptions are wrapped in `UncheckedIOException`, so failures propagate loudly.
  - `SocketDelayServer`: a selector loop. The accept channel uses backlog 1024. Each connection keeps a 64 B `ByteBuffer` attachment, and on the 64th byte the server adds `(dueNanos, channel)` to a `PriorityQueue`. `select(timeoutToNextDue)` fires the due replies: write 64 B, close. `main(port, delayMs)` adds a shutdown hook that prints a JSON with requests and process CPU seconds (`ProcessHandle.current().info().totalCpuDuration()`) and prints `READY <port>` on stdout once bound.
- [ ] **Step 4:** run `mvn -q test -Dtest='SocketDelayServerTest,WorkloadsTest'`. Expected: pass.

## Task 3 (B3): benchmark parameters, VT carrier check, SOCKET port

**Files:** Modify `ConcurrencyEnergyBenchmark.java`; create `ConcurrencyEnergyBenchmarkTest.java`

- [ ] **Step 1: tests first.** `checkCarrierCount(VIRTUAL_THREADS, 8, "8")` passes. `(VIRTUAL_THREADS, 8, null)` and `(VIRTUAL_THREADS, 8, "4")` throw `IllegalStateException`. `(FIXED_POOL, 8, null)` passes.
- [ ] **Step 2:** the tests fail.
- [ ] **Step 3: implement.**
  - `@Param` strategy = the 5 constructs.
  - `parallelism` = {1, 2, 4, 8, 16, 64, 256}.
  - `workloadType` = {CPU, SLEEP, SOCKET}.
  - `setUp` calls `checkCarrierCount(strategy, parallelism, System.getProperty("jdk.virtualThreadScheduler.parallelism"))` and prints `VT carriers = …` for VT.
  - SOCKET reads `Integer.getInteger("vtenergy.socket.port")`; if it is missing it fails, which says that the server is not running.
  - Update the Javadoc.
- [ ] **Step 4:** run `mvn -q test` (all except the 2 RAPL hardware tests). Then run `mvn -q -DskipTests package`. Then smoke-test without energy: `java -jar target/benchmarks.jar -p strategy=VIRTUAL_THREADS -p parallelism=4 -p workloadType=SLEEP -f 1 -wi 1 -w 1s -i 1 -r 1s -jvmArgsAppend -Djdk.virtualThreadScheduler.parallelism=4` prints `VT carriers = 4`.

## Task 4 (A3-D7): frequency per iteration on Intel

**Files:** Create `CpuFreq.java`, `CpuFreqTest.java`; modify `EnergyProfiler.java` (protected `List<Result> extraResults()` returning empty, appended in `afterIteration`) and `RaplProfiler.java` (overrides it with `CpuFreq`).

- [ ] **Step 1: test first.** `CpuFreq.fromSysfs(Path root)` runs on a temp-dir fake sysfs: cpu0/cpu1 have capacity 1024 and avg_freq 4000000/2000000 kHz; cpu2 has capacity 774 with only `scaling_cur_freq` 3000000; cpu3 has capacity 312 with an unreadable or garbage value. Expected `meanMHzByClass()` = {P=3000.0, E=3000.0}; LPE is absent.
- [ ] **Step 2:** fails. **Step 3:** implement: classes by distinct capacity, descending → P, E, LPE (same rule as `topology.sh`). **Step 4:** passes.

## Task 5 (B5): orchestrator `scripts/run_experiment.py`

**Files:** Create `scripts/run_experiment.py`, `scripts/test_run_experiment.py`, `scripts/mac/bg-java.sh`

Interface: `python3 scripts/run_experiment.py --platform {intel,mac} --campaign NAME [--mode energy|profile] [--subset full|pilot|smoke] [--forks N] [--seed S] [--cells-file F] [--dry-run] [--max-runs N]`

Pure functions (unit-tested with `python3 -m unittest scripts/test_run_experiment.py`):
- `cells(platform, subset)` → a list of `Cell(construct, p, workload, restriction)`, where restriction ∈ {DEFAULT, BACKGROUND, unpinned, 2P, 2E, 2LPE}.
  - Tests: full Intel = 141 cells, full Mac = 93. Exp-1 per workload = 23. Exp 2 = SEQ, PT, {FP, FJ, VT} × {4, 16} = 8 per workload. SEQ and PT carry p = None.
- `schedule(cells, forks, seed, batch_size=40)` → a list of `Run(run_id, cell, fork_index, order, batch)`.
  - `fork_index` is 1..forks per cell and is assigned before shuffling, so it is fixed before any data exist. The order is a seeded `random.Random(seed).shuffle`.
  - Tests: 705 runs for Intel full with 5 forks; deterministic for a seed; every cell appears exactly `forks` times; batches have ≤ 40 runs.
- `jmh_command(run, platform, paths)` → argv.
  - Tests: VT adds `-jvmArgsAppend "-Djdk.virtualThreadScheduler.parallelism=8 -Djdk.virtualThreadScheduler.maxPoolSize=8"`. SOCKET adds `-Dvtenergy.socket.port=…`, merged into the same `-jvmArgsAppend` string. Intel CPU uses `-wi 12 -w 5s`, everything else `-wi 5 -w 1s`. `-i 5 -r 5s -f 1 -rf json`.
  - Intel 2E prefixes `taskset -c 6,7`. Mac BACKGROUND adds `-jvm scripts/mac/bg-java.sh`. The profiler is `RaplProfiler` or `IoReportProfiler`. Profile mode adds `-prof jfr:dir=…`, and `-prof perf` when it is available.
- `idle_agrees(start_w, end_w, rel, abs_)`: tests cover 3.65/3.70 → True, 3.65/14.99 → False, and the Mac case 0.0296/0.0202 with abs 0.010 → True.
- `estimate_seconds(runs, platform)`: Intel CPU 100 s/run, others 45 s, plus 130 s per batch. Test: Intel full ≤ 15 h, Mac full ≤ 12 h.

Side-effecting loop (`main`):
1. Preflight: RAPL readable (Intel), AC online, jar present, `somaxconn` (Mac), `powermetrics` refresher started (Mac, at 100 ms, into the batch dir).
2. Write `schedule.csv` if it does not exist. If it exists, verify the same seed and the same runs.
3. Per batch:
   1. Start the SOCKET server.
   2. Write `env-start`.
   3. Quiet gate, then a 60 s idle baseline.
   4. Run each pending run: quiet gate (A3-D10), then JMH with a timeout (20 min) and stdout/stderr to `.log`. Append a status to `progress.csv`: `ok`, `failed`, or `timeout`. Then cool down.
   5. Quiet gate, end idle baseline, `env-end`, stop the server (writes `server.json`).
   6. Apply `idle_agrees` and re-queue once on failure.
4. A `SIGINT` finishes the current run and then stops, so the campaign can be resumed.

- [ ] Steps: write the tests (fail) → implement the pure functions (pass) → implement `main` → `--dry-run` prints `705 runs, 18 batches, est. ~13 h` (Intel) and `930 runs … ≤ 12 h` (Mac) → `--subset smoke --max-runs 3` real run (needs RAPL readable) produces 3 JSONs with `rapl.*` and `freq.*` keys.

## Task 6 (B6): ancillary experiments

**Files:** Create `LoadProbe.java`, `LatencyCalibration.java` (+ test), `scripts/ancillary/*.sh`, `analysis/vtenergy/ancillary.py`

- **LoadProbe** `<threads> <seconds> <out.json>`: k threads spin the Mandelbrot kernel until the deadline. The energy reader is read at start and end; output is `{threads, seconds, watts{domain}, ops}`. It calls `checkFresh`.
- **LatencyCalibration** `<out.json> [sleeps=10000] [socketPort rtts=1000]`: `Thread.sleep(10)` latency distribution on a platform thread and on a virtual thread (sequential, `nanoTime`). Optionally the socket RTT. Output: n, mean, median, p90, p99, max in ms. Unit test: a small n (20 sleeps of 1 ms) yields median ≥ 1.
- AX2 (Mac): idle 60 s at refresh 1000/250/100 ms → `results/ancillary/mac/ax2.json`.
- AX3 (Mac): LoadProbe k ∈ {1, 4, 10}, 20 s each, with powermetrics at 100 ms. `ancillary.py ax3` compares the IOReport CPU W with the mean `CPU Power` of the powermetrics samples inside the window.
- AX4 (both): k = 0..N (Intel 16, Mac 10), 20 s, 10 s cooldown → `ax4.csv`. `ancillary.py ax4` gives the linear fit R² and the per-thread increment.
- AX5 (both): LatencyCalibration with the server. On the Mac it also runs under `taskpolicy -b`.
- AX6 (Mac): LoadProbe with 6 threads, DEFAULT vs `taskpolicy -b`, with powermetrics. `ancillary.py ax6` parses P- and E-cluster active residency and frequency.
- AX7: drift (analysis, Task 7).
- SRV (both): 60 s idle with vs without the server.

## Task 7 (B7): analysis package

**Files:** `analysis/vtenergy/*.py`, `analysis/analyse.py`, `analysis/tests/test_stats.py`, `test_load.py`, `test_hypotheses.py`, `analysis/requirements.txt`

- `load.py`: `load_campaign(dir)` → a tidy DataFrame with one row per **ok** run: run_id, platform, campaign, construct, p, workload, restriction, fork_index, order, batch, ms_op (median of the 5 iterations), `<domain>_J_op` (median of iterations) for every domain, window power W, freq columns (Intel), batch idle W per domain (start baseline; it uses end if start is missing), `<primary>_J_op_active` = J_op − idle_W × ms_op / 1000, regime_flag. The Mac adds `mem_J_op` = DRAM + AMCC + DCS and `ecpu_share` = ECPU/(ECPU+PCPU). Test: a synthetic campaign dir with 2 fake JMH JSONs.
- `stats.py` (pure functions, each with tests on synthetic data that has known answers):
  - `cliffs_delta`, `epsilon_squared(H, n)`, `holm(pvals)`, `bootstrap_ci(stat, a, b, n=10000, level, seed)`.
  - `tost_ratio(a, b, margin=0.05)` (the bootstrap 90 % CI of median(a)/median(b) lies within [0.95, 1.05]).
  - `below_detection_limit(x)` (the bootstrap CI of the median includes 0).
  - `kruskal`, `dunn` (scikit-posthocs, Holm), `mw_power(cv, n, ratio=1.10, sims=2000, seed)`.
- `hypotheses.py`: one function per family in Table 4 of the report. Each returns rows `(family, test, workload, p, comparison, statistic, p_raw, p_holm, effect, ci_lo, ci_hi, decision)`. Holm is applied within each family. The functions follow §4.6 exactly:
  - Main: p = 8 (Mac) / 16 (Intel) on CPU; p = 256 + PT on blocking workloads.
  - H0-1.2: the Mac uses the fork split. Intel uses the confirmation campaign (A3-D6), via `select_best.py`.
  - H0-2.2: IU, one-sided.
  - The memory family runs on the Mac only.
  - TOST on non-rejections. Detection limit on idle-subtracted values.
  - AX7 drift: Spearman of the within-cell residual of J/op against run order.
- `figures.py`: Λ curves (J/op against p per workload, one line per construct), energy-vs-time scatter (CPU), cluster-split bars (Mac), and Intel placement bars.
- `analyse.py --campaign results/intel/main [--confirm results/intel/confirm] [--out …]` writes `runs.csv`, `cells.csv` (median, IQR, CV per cell), `tests.csv`, `power.csv`, and `figures/*.pdf`.
- [ ] Steps: tests first per module → implement → `.venv/bin/python -m pytest analysis/tests` (or `unittest`) green → run on the A2 pilot JSON as a smoke check (through a compatibility loader for the pilot layout: one JSON, 3 forks).

## Task 8 (B8): Intel arm execution (needs the user at the machine)

1. `sudo scripts/enable-rapl.sh`. Optional: `sudo pacman -S perf` (for profiling).
2. Quiet-machine protocol: quit the Claude app, browsers, Discord; Wi-Fi off; AC on.
3. Pilot 2: `python3 scripts/run_experiment.py --platform intel --campaign pilot2 --subset pilot --forks 3` (about 1.5 h). Then `analyse.py` → `power.csv`. If the power is < 0.8 for a key comparison, raise the forks there (up to the time budget).
4. AX4, AX5, SRV, about 30 min.
5. Main: `--campaign main --subset full --forks 5`, about 13 h, overnight. Resumable.
6. Confirmation: `analysis/vtenergy/select_best.py results/intel/main > results/intel/confirm-cells.csv`, then `--campaign confirm --cells-file … --forks 5` (about 30 min).
7. Profiling: `--mode profile --campaign profile` (about 1 h).

## Task 9 (B9): replication package

- `docs/replication.md`: toolchain versions, the one-time setup per platform, the exact commands of Task 8 and of the Mac equivalents, the results layout (A3-D8), and how to regenerate every table and figure (`analyse.py`).
- `README.md`: updated layout and quick start. `analysis/requirements.txt` is pinned (`pandas==3.1.0 scipy==1.18.1 scikit-posthocs==0.17.1 matplotlib==3.11.2`).
- `.gitignore`: keep `results/<platform>/` JSON tracked. Keep JFR files and powermetrics text ignored; the gzipped ones are tracked.
- The acceptance is a fresh clone + `analyse.py` on the committed results, which reproduces `tests.csv` and the figures.

## Mac arm (after Intel; Sounic at the Mac)

`sudo sysctl kern.ipc.somaxconn=1024`, the quiet protocol, then `bash harness/native/build.sh`, `mvn package`, and `run_experiment.py --platform mac --campaign pilot2 …`, AX2–AX6, `main` (930 runs, about 11.6 h), and `profile`.

## Self-review

- **Coverage:**
  - B1 → T1, B2 → T1, B3 → T3, B4 → T2, B5 → T5, B6 → T6 (+ AX7 in T7), B7 → T7, B8 → T4 + T8, B9 → T9.
  - Report items: randomization (T5 schedule), gated idle baselines (T5), frequency logging (T4), heat-soak (T5 `jmh_command`), floor ratio and detection limit (T7), power check (T7 `mw_power`), server-only run (T6 SRV), JFR/perf (T5 profile mode).
- **Deviations to report:** A3-D2 (FJ compensation disabled), A3-D6 (Intel confirmation stage), A3-D9 (Mac absolute idle tolerance), and SO_LINGER 0 on SOCKET (A3-D4).
- **Name consistency:** strategies `SEQUENTIAL, PLATFORM_THREADS, FIXED_POOL, FORK_JOIN, VIRTUAL_THREADS`; workloads `CPU, SLEEP, SOCKET`; sysprop `vtenergy.socket.port`; restrictions `DEFAULT, BACKGROUND, unpinned, 2P, 2E, 2LPE`.

## Execution log

- **24 Oct, toolchain:** `~/.local/opt/jdk-25` was gone. It is now a symlink to mise's `temurin-25.0.4+101.0.LTS`, which is exactly `25.0.4.1+1`, the build used by the 2 Oct pilot. Maven 3.9.16 comes from mise. The analysis venv is `.venv` (pandas 3.1.0, scipy 1.18.1, scikit-posthocs 0.17.1, matplotlib 3.11.2).
- **T1 / A3-D2, checked empirically:** on JDK 25 a *default* `ForkJoinPool(p)` with recursive splitting over 256 sleeping leaves did not add compensation threads. The maximum concurrency was exactly p, the time matched ⌈256/p⌉×10 ms, and the pool size stayed p (p = 1, 2, 8). The bound (maxPoolSize = p, saturate → true) is therefore a guarantee, not a behaviour change, and it does **not** explain the A2 FJ/SLEEP anomaly. That anomaly came from the old `invokeAll` implementation, which recursive FJ replaces; the profile campaign can still check FJ.
- **T2:** the server counts a request when its 64th byte arrives, not when the reply is sent, which avoids a test race. Smoke run: VT p = 4 SOCKET took 13.0 ms/op, and the server handled 56 k connections in about 5 s at about 15 µs CPU per request, with no port exhaustion.
- **T5 bugs found by the smoke runs:**
  1. The runner looked for scripts in `scripts/intel/`. They are in `scripts/linux/`, now mapped through `SCRIPT_DIR`, and preflight checks that they exist. Before the fix the quiet gate could never have passed on Intel.
  2. JMH stops JFR through `jcmd … filename=<path>`, which splits at spaces, and this repo lives under "Green Software Development". Profile runs therefore record into a `mkdtemp` staging dir and move `<run_id>.jfr` into `profile/<run_id>/`. A profile run without a recording counts as failed.
- **T5 estimates** (the per-op time model counts the slow SEQ/p = 1 cells): Intel full 14.5 h (≤ 15 h), Mac full 14.2 h. The Mac figure is above the report's 12 h and needs a night plus part of a day.
- **T6:** AX5 on Intel (24 Oct, not quiet): `Thread.sleep(10)` takes 10.13 ms on a platform thread and 10.26 ms on a virtual thread (median), and the SOCKET round trip 10.14 ms.
- **T7 (subagent) findings for the report:**
  1. On SLEEP, idle-subtracted J/op of FP, FJ and VT is about 0 (Intel pilot FP_8 and FJ_8 are slightly *negative*: run power below the IdleBaseline JVM's idle). The power check on that measure is therefore 0.04–0.13 at n = 10, and adding forks cannot fix it. The analysis reports these cells as below the detection limit or "negative: below idle". The meaningful blocking-workload contrasts are PT vs VT, plus raw and memory-subsystem energy on the Mac.
  2. The ambiguities the subagent resolved are listed in its hand-back. The main ones:
     - The memory family tests idle-subtracted values.
     - The IU p is the max of 4 one-sided MW tests.
     - "Best" in H0-1.2 includes PT.
     - AX7 uses raw J/op.
- **T5 review (code-reviewer subagent, 24 Oct). Fixed:**
  - C1: no keep-awake. Now `caffeinate -w` on the Mac and `systemd-inhibit` (sleep, idle, lid switch) on Linux, verified with `systemd-inhibit --list`.
  - I1: helpers shared the terminal's process group, so a Ctrl-C killed the server and IdleBaseline. They now run with `process_group=0`; on Python 3.9, `preexec_fn=setpgrp`.
  - I2: a timeout or abort killed only the JMH host and orphaned the fork. JMH now runs in its own session, and the whole group is killed. Verified: no leftover JVM after SIGTERM.
  - I3/I4: the re-queue lived only in memory, and batches without an end baseline went unverified. `requeue_candidates` now derives the re-queue from the files on every start; unverified means `agree` ≠ True or no row. Each run is re-queued at most once, as `<batch>-r<n>`, and `load.py` adds `idle_unverified`.
  - I5: a single error aborted the night. The refresher and server now start inside the `try`, and `guarded_batch` stops only after two consecutive batch errors.
  - I6: retries are chunked at 40 per execution (`retryNN`).
  - I7: the cooldown reads the last 64 KB of the powermetrics log, and Mac logs are gzipped after each batch.
  - I8: fixed the empty-array crash under bash 3.2 in `ancillary/common.sh` and added caffeinate and a sudo keepalive there.
  - Suggestions:
    - S1: server start timeout 30 s; `wait` after `kill`.
    - S2: SIGTERM/SIGHUP unwind through the `finally` blocks.
    - S3: the server is restarted if it died before a SOCKET run.
    - S4: logs are kept per attempt.
    - S5: the stop flag is checked after the gate.
    - S6: port 31000, below the ephemeral range.
    - S7: `from __future__ import annotations`.
    - S9: torn CSV lines are tolerated.
  - The powermetrics start/stop scripts use `sudo -n` when not on a tty.
  - Not done: S10 (commit before campaigns) is the user's call.
- **24 Oct, Intel pilot2 (99 runs, 0 failures; the pipeline worked end to end, including the re-queue).** The data are **contaminated** and not for the report, because:
  - The machine was not quiet: Zen, Chromium and the Claude app were running, and the 95 % idle gate cannot catch one busy core on 16 CPUs.
  - The power profile was `performance` (EPP performance).
  - Idle package power was 8.5–14 W against 3.65 W on 2 Oct, and every batch's idle pair disagreed.
  - PT/SLEEP drew 26 W against 6.5 W on 2 Oct.
- **Finding (needs a correction in A3):** every concurrent CPU cell ran at exactly 25.0 W package power. The binding limit is the firmware's **MMIO RAPL PL1 = 25 W** (`intel-rapl-mmio:0`, τ ≈ 28 s), not the MSR PL1 of 65 W. This also explains the A1 "power-regime shift" (62 → 25 J per 1 s iteration after the boost window). The A2 text "the RAPL limits (PL1 65 W, PL2 115 W) were not reached" is wrong.
- **Fixes:**
  - `env-manifest.sh` now logs the MMIO limits, EPP and the power profile.
  - The quiet gate deny-lists browsers and Electron, chat and media apps.
  - The runner requires EPP = `balance_performance` (`--epp`) and rejects idle baselines above 6 W on Intel or 0.08 W on the Mac (`--idle-ceiling`); it retries 5 × 60 s, then stops.
- **24 Oct, Mac smoke test** (3/3 runs ok: IOReport profiler, SOCKET server, refresher, re-queue). Three findings:
  1. `kern.ipc.somaxconn` = 128 resets SOCKET connections above 128 concurrent (19/20 operations failed at 256). It must be 1024; the test now says so.
  2. `Future.resultNow()` hid the cause of failed tasks; fixed with `awaitAll`.
  3. Idle baselines disagreed (0.014 vs 0.069 and 0.078 vs 0.029 W) because of the animated Aerial wallpaper and screen saver (`WallpaperAerials`, `VTDecoderXPCService`), not because of the runs. Removing it gave a median idle of 99.2 %.
- **The Mac is on Wi-Fi** for SSH control, a deviation from the quiet protocol.
- **macOS is 27.2 beta (26B5091g)**, not the 27.0 of the A2 pilot.
- **Mac main campaign started 24 Oct, 23:31.**
- **Added beyond the plan:**
  - `analysis/vtenergy/profile.py` (JFR event counts per cell) and `analysis/vtenergy/ancillary.py` (AX3–AX6 and SRV summaries).
  - `.gitignore` drops JFR recordings and raw powermetrics logs.
