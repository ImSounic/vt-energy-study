# A2 report fact sheet (single source of truth for all section writers)

Every number in the report must come from this sheet or from a file it names. Do not invent numbers, citations or results. If a needed fact is missing, write `\todo{...}` (the macro renders in red) and report it.

## 1. What the A2 brief requires

The report is an "experiment plan" that refines the A1 report, in two-column ACM `acmart` format (`\documentclass[sigconf,nonacm]{acmart}`). It has **5–7 pages of content plus 1 page of references**, a title, the authors and an abstract.

**Section order (exactly):**
1. Introduction
2. Context. Changes since A1 are shown **in blue**.
3. Related Work. Changes since A1 are shown **in blue**, and it must include additional related work.
4. Experiment Planning. Follow Jedlitschka et al. [`jedlitschka2008reporting`]. It must contain:
   - reviewed goals and RQs;
   - **a null hypothesis (H0) and an alternative (H1) for each RQ, plus a main pair**;
   - experimental units, why they were chosen, and any randomisation;
   - independent and dependent variables, each with its levels;
   - workloads and why they were chosen;
   - the design;
   - the analysis procedure for each hypothesis.
5. Measurement Tools, Environment, and Procedure. Follow the Castor primer [`castor2024primer`]. It must cover:
   - the platform and every hardware/software element that can affect results (frequencies, RAM, compilers/runtimes, non-default configuration);
   - the measurement approach, why it was chosen, and why it is precise enough;
   - how execution is synchronised with measurement;
   - how many executions per trial, and why;
   - the workload;
   - the sampling rate;
   - precautions against measurement overhead;
   - a section showing **familiarity with the measurement infrastructure and how typical pitfalls are addressed**;
   - a **profiler**, chosen and tried out.
6. Threats to Validity. Cover construct, internal, external and conclusion validity. Give **each threat a mitigation**, an ancillary experiment, or a statement of how it affects the results.
7. Schedule. Cover the next steps: running the experiment, analysis, the final report and the presentation. The experiment should take **under 40 h**.
8. Concluding Remarks.

**Other requirements:**
- A page-1 footnote on the authors saying how each author contributed. The authors write this; leave the existing `\thanks{...}` placeholder.
- Reuse the A1 text (related work, context, parts of the methodology), updated.

## 2. Style rules (from the A1 history)

- Formal academic register, American spelling ("behavior"), as in A1.
- **No prose dashes** (no em/en dashes used as punctuation; A1 removed them deliberately). Use commas, colons, parentheses or separate sentences.
- No marketing tone, no rhetorical questions.
- Define abbreviations once in §4 and then use them: SEQ (sequential), PT (one platform thread per task), FP (fixed thread pool), FJ (Fork/Join), VT (virtual threads), QoS (quality of service).
- Construct names in prose: "fixed thread pool (FP)" on first use, then "FP".
- Use these fixed labels so cross-references work:
  - Sections: `sec:intro`, `sec:context`, `sec:related`, `sec:planning`, `sec:measurement`, `sec:threats`, `sec:schedule`, `sec:conclusion`.
  - Tables and figures: `tab:related`, `tab:hypotheses`, `tab:variables`, `tab:env`, `tab:refresh`, `tab:pilot`, `fig:regime`, `tab:schedule`.
- Ids that must match across sections:
  - Hypotheses: H0/H1 (main), H0-1.1 … H0-3.2.
  - Ancillary experiments: AX1–AX7.
  - Design decisions are internal only; don't print "D1" etc.
- Tables: use `table` (one column) where it fits and `table*` (both columns) only for genuinely wide tables. Use `\small` or `\footnotesize` and `booktabs` rules (`\toprule`, `\midrule`, `\bottomrule`), as in A1.

## 3. Platform and toolchain (ground truth, measured 1 Oct 2026)

**Primary platform: Apple Mac mini M4 (`Mac16,10`).**
- 10 cores: 4 performance (P) + 6 efficiency (E).
- Maximum frequencies observed by `powermetrics`: P cluster 4464 MHz, E cluster 2892 MHz. The P-cluster all-core frequency under the CPU-bound pilot was mostly 3936 MHz.
- 16 GB unified memory, macOS 27.0 (build 26A428), mains (AC) power, Low Power Mode off.
- Frequency is governed by Apple's closed-loop performance controller; it cannot be set by the user.
- macOS offers **no CPU-affinity API** (thread affinity requests are ignored on Apple Silicon). The only lever a developer has is the **QoS class**: `taskpolicy -b` (background) confines a process to E cores.

**Secondary platform (conditional): Intel Core Ultra 7 255H.**
- Three tiers, no SMT: 6 P-cores (up to 5.1 GHz, Linux capacity 1024), 8 E-cores (4.4 GHz, 774), 2 LP-E cores (2.5 GHz, 312).
- CachyOS Linux, `intel_pstate`/HWP, turbo on.
- RAPL domains: package, core, uncore, psys.
- The laptop is currently broken. Its arm runs only if it is repaired by **16 Oct 2026** (go/no-go). Intel results will be reported later, in A3.

**Software:**
- JDK 25.0.4.1 (Homebrew OpenJDK build) on both platforms. The A1 pilot used JDK 26.0.2. JDK 25 is the current long-term-support release, which is what developers deploy.
- JVM flags: `-Xms2g -Xmx2g -XX:+UseG1GC --enable-native-access=ALL-UNNAMED`.
- JMH 1.37, Maven 3.9.16, Apple clang 21 (for the native shim).
- Paper built with tectonic.

## 4. Measurement instrument (Mac)

- **Source:** Apple IOReport "Energy Model" counters, which are cumulative energy counters (mJ/µJ/nJ) maintained by the SoC's energy model.
- **Channels used:**
  - `CPU_Energy` = `ECPU` + `PCPU` (CPU clusters), plus per-core ECPU0–5 and PCPU0–3.
  - `DRAM`, `AMCC` (memory controller), `DCS`, `GPU`, `ANE`, `ISP`, `DISP`/`DISPEXT` (display), `SOC_AON` and others.
  - Hierarchy verified on cumulative values: CPU_Energy = ECPU + PCPU exactly; ECPU = ΣECPU0–5 + ECPM; PCPU = ΣPCPU0–3 + PCPM.
  - Resolution is 1 mJ.
- **How it is read:**
  - A small C shim over IOReport is called from Java through the Foreign Function & Memory (FFM) API. No sudo is needed to read it.
  - A custom JMH profiler reads all counters **once before and once after each iteration** (no polling inside the measured region) and reports J and J/op per channel, plus the window length.
  - The same profiler class reads RAPL on Linux, so both platforms share one measurement path.
- **Pitfall found (macOS 27): counters are frozen unless `powermetrics` runs.**
  - Without a privileged sampler, the CPU counters return identical values on every read.
  - With `sudo powermetrics` running, they are published only at each `powermetrics` sample, so any read is stale by **at most one sampling interval**.
  - Evidence: a 1 s burn read without proper refresh gave 1100 mJ. That matches the *previous* `powermetrics` sample (1077 mW × 1.01 s), not the burn itself (8149 mW).
  - Design response: `powermetrics` runs as root at **100 ms** purely as a refresher (it also logs cluster residency, frequency and thermal pressure).
  - Worst-case staleness is 100 ms per boundary, i.e. **≤ 2% of a 5 s measurement window**.
  - The profiler **fails loudly** if `CPU_Energy` does not advance over a window of 0.5 s or more, so frozen counters can never silently produce 0 J.
- **AX1 (done 1 Oct): refresh cadence vs `powermetrics` interval** (6 s windows, Mac idle). This is `tab:refresh`:

  | powermetrics interval | counter updates in 6 s | max gap between updates |
  |---|---|---|
  | off | 0 | n/a |
  | 1000 ms | 13 | 1005.6 ms |
  | 250 ms | 47 | 256.8 ms |
  | 100 ms | 111 | 106.0 ms |
  | 50 ms | 208 | 55.9 ms |

- **Accuracy:**
  - RAPL has been validated against physical meters [`khan2018rapl`].
  - Apple's counters are model estimates with no published validation against a meter. Hübner et al. [`hubner2025apple`] state that `powermetrics` values are software estimates that Apple advises against comparing across devices.
  - **No wall power meter is available.** Cross-checks: AX3 (IOReport vs `powermetrics` "CPU Power" over the same windows) and AX4 (load scaling, 0–10 busy threads).
- **Measurement scope:** CPU clusters, memory subsystem and SoC blocks. It excludes the PSU, SSD, fans and network.

## 5. Intel pilot (A1, 10 Sep 2026, JDK 26.0.2, RAPL)

Settings: parallelism 8, unpinned, 2 forks × 10 × 1 s.

**PLATFORM_THREADS / CPU, package energy per 1 s iteration (`fig:regime`):**
- Fork 1: 62.0, 62.8, 62.5, 57.7, 63.1, 54.2, 35.8, 25.4, 25.0, 24.9 J, while ms/op rose from 89 to 128.
- Fork 2: 25.3, 27.6, 25.0, 25.1, 26.1, 25.0, 24.9, 25.8, 25.8, 26.5 J.

**VIRTUAL_THREADS / CPU:** fork 1 at about 41 W, fork 2 at about 25 W.

**Reading:** this is a power-limit or thermal regime shift. It is consistent with PL2→PL1, but that is not confirmed. The A1 CPU J/op figures (3.38 vs 5.13) averaged across both regimes; A2 says so honestly. Treatment was identical; only the power state differed. JMH runs cells in a fixed order, so run order is confounded with power state.

## 6. Mac feasibility pilot (1 Oct 2026, 15:27–15:43)

**Settings:**
- p = 8; 4 constructs (PT, FP, FJ, VT); 2 workloads (CPU = Mandelbrot, SLEEP = `Thread.sleep(10 ms)`, called "IO" in the pilot code).
- 3 forks × (5 × 1 s warmup + 5 × 5 s measured iterations); default QoS.
- Quiet-machine protocol passed (CPU ≥ 95% idle); `powermetrics` at 100 ms.
- Output: `results/pilot-mac/`.

**Primary metric: CPU_Energy** (median of per-fork medians). This is `tab:pilot`:

| Construct | Workload | ms/op | J/op | mean W | CV of per-fork J/op |
|---|---|---|---|---|---|
| PT | CPU | 156.8 | 1.771 | 11.27 | 0.6% |
| FP | CPU | 182.2 | 1.987 | 10.88 | 0.9% |
| FJ | CPU | 182.2 | 1.974 | 10.84 | 0.7% |
| VT | CPU | 154.8 | 1.767 | 11.40 | 0.9% |
| PT | SLEEP | 16.61 | 0.0251 | 1.53 | 4.8% |
| FP | SLEEP | 458.6 | 0.0174 | 0.052 | 48.6% |
| FJ | SLEEP | 397.5 | 0.0080 | 0.057 | 116% |
| VT | SLEEP | 12.61 | 0.00035 | 0.027 | 2.1% |

**Facts to use:**
- **CPU-bound runs are highly repeatable:** fork-to-fork CV 0.6–0.9%.
- **Thermal pressure was "Nominal" in all 8094 `powermetrics` samples.** There was **no** power regime shift, unlike the Intel pilot.
- **CPU energy under sleep-bound workloads is at the noise floor:**
  - CPU energy per 5 s window was 0.12–0.7 J (FP, FJ, VT).
  - Idle-subtracted J/op came out slightly negative for FJ and VT. That means the difference is within idle noise, not that the energy was negative.
  - Design response: for blocking workloads, also report memory-subsystem energy (DRAM + AMCC + DCS) and SoC-level energy; use 10 forks and bootstrap CIs; report values whose CI includes zero as "below detection limit".
- **The `powermetrics` refresher's own overhead (AX2, preliminary)** is idle CPU power with the refresher at 1000 ms vs 100 ms:
  - 0.017 W at 1000 ms vs 0.030 W and 0.020 W at 100 ms (start and end of the pilot), i.e. **≤ 13 mW**.
  - That is negligible against CPU-bound power (about 11 W, ≈ 0.1%) but comparable to sleep-bound CPU power (0.03–0.06 W).
  - Because it is constant across treatments, it cancels in comparisons and is included in the idle baseline.
- **Background load matters:**
  - Idle CPU power was 0.020 W on the quiet machine, against 0.184 W with everyday apps open (browser, chat, Claude desktop; measured the same day with the same tool): about 9× higher.
  - With those apps open the machine was only 68–94% idle.
- **macOS `Thread.sleep` overshoot (motivates AX5):**
  - Nominal floor for FP/SLEEP is 256/8 × 10 ms = 320 ms. Measured: 458.6 ms on the quiet machine (≈ 14.3 ms per sleep wave), against 387 ms (≈ 12.1 ms per wave) in a smoke run on a busy machine the same day.
  - VT/SLEEP took 12.6 ms for 256 concurrent 10 ms sleeps.
  - So sleep latency on macOS depends on system activity (timer coalescing), and the "controlled latency" must be measured, not assumed.
- **Unexplained observation, to investigate in A3:** FJ/SLEEP (397.5 ms) was faster than FP/SLEEP (458.6 ms) with the same 8 workers, and much more variable (CV 116%). One hypothesis to check with JFR is that the external caller helps execute tasks in `ForkJoinPool.invokeAll`. A3 replaces the flat FJ submission with recursive splitting anyway (see §7).

## 7. Design decisions (the plan; §4 and §5 describe these)

- **D1 Platforms:** the Mac is primary. Intel is a conditional second arm with go/no-go on 16 Oct.
- **D2 JDK:** 25.0.4.1 on both.
- **D3 Constructs (5):**
  - SEQ (new; tasks run in the caller thread).
  - PT (one platform thread per task, 256 threads).
  - FP (`Executors.newFixedThreadPool(p)`).
  - FJ: a `ForkJoinPool(p)` with **recursive divide-and-conquer splitting** of the task list (new, replaces the flat `invokeAll` used in the pilot).
  - VT (`newVirtualThreadPerTaskExecutor`, one virtual thread per task).
- **D4 Concurrency level p ∈ {1, 2, 4, 8, 16, 64, 256}:**
  - It means the pool size for FP, the parallelism for FJ, and the **carrier count for VT** (set per JVM run with `-Djdk.virtualThreadScheduler.parallelism=p`).
  - SEQ and PT have no p (one cell each).
  - This removes the duplicate cells the A1 harness would have produced.
  - **p = 256 equals the task count.** It is the level at which a pool overlaps all 256 waits, as VT and PT do. It was added so that the blocking-workload sweep ends where pools can catch up.
- **D4b Fair comparison for blocking workloads (SLEEP, SOCKET). This must be stated in the report:**
  - For a bounded pool, the elapsed time per op has an analytic floor of ⌈256/p⌉ × d, where d is the measured per-task wait (≈ 10 ms nominal; macOS overshoot measured by AX5).
  - So for p < 256, "FP/FJ are slower than VT" is **known by construction, not a finding**. A1 already said this of its 27× result.
  - The **primary G2 comparison on blocking workloads is therefore VT vs PT**. Both overlap all 256 waits, so concurrency is equal and only OS threads vs virtual threads differ. Pilot: PT 16.6 ms vs VT 12.6 ms. JFR: 189,191 vs 19 OS thread starts; 54 vs 1 GCs.
  - VT is also compared against FP_256 and FJ_256, the pools sized to the task count.
  - FP/FJ results at p < 256 are **reported relative to their predicted floor** (overhead beyond the floor). The sweep shows how quickly pools close the gap as p grows.
  - **Energy caveat:** while threads sleep, CPU clusters are nearly idle (≈ 0.02 W on the M4). A pool that takes many times longer therefore barely registers in CPU-cluster energy. The real energy cost of waiting longer is platform static power (memory, SoC, and parts the counters do not see: PSU, fans, SSD).
  - This is why blocking workloads also report memory-subsystem (DRAM + AMCC + DCS) and SoC-level energy. The partial visibility of static power is a construct threat.
- **D5 Workloads (= experimental units), each 256 independent tasks per operation, so total work is identical across p:**
  - **CPU:** Mandelbrot 128×128, at most 500 iterations per point. It comes from the 2014 benchmark set and is deterministic and allocation-free.
  - **SLEEP:** `Thread.sleep(10 ms)` per task. This isolates the unmount-on-block mechanism with a nominally controlled latency.
  - **SOCKET (new):** each task opens a loopback TCP connection to an out-of-process server, sends 64 B, and receives a 64 B reply that the server delays by 10 ms without blocking. One connection per task keeps the I/O pattern identical across constructs. The server's energy is constant per task and is reported as a construct threat.
- **D6 Core restriction:**
  - Mac: DEFAULT vs BACKGROUND QoS (`taskpolicy -b`, E cores only), applied to the forked benchmark JVM through a wrapper passed to JMH's `-jvm` option.
  - Intel: unpinned vs **equal-count** 2P / 2E / 2LP-E pinning via `taskset`. Equal counts separate core type from core count. On Linux `taskset` also changes `availableProcessors`, and with it the carrier, GC and JIT thread counts.
- **D7 Replication unit:**
  - One fork (one fresh JVM run) is one trial; its value is the median of its 5 measured iterations [`georges2007rigorous`].
  - n = 10 forks per cell, confirmed by a power analysis on pilot variance.
  - The CPU-bound pilot CV of under 1% means 10 forks detect differences far below 10%. The sleep-bound cells have CV up to 116% on CPU energy, which is why they get the memory/SoC metrics and bootstrap CIs.
- **D8 JMH timing:** 5 × 1 s warmup and 5 × 5 s measured iterations; `powermetrics` refresh every 100 ms; `-rf json`.
- **D9 Run order and environment control:**
  - Run order is randomised at fork level with a seeded shuffle, recorded in a schedule CSV.
  - Before each run, a quiet-machine gate requires CPU ≥ 95% idle over 3 s.
  - After each run, a cooldown of at least 10 s that also waits until thermal pressure is "Nominal".
  - A 60 s idle baseline per batch of about 40 runs.
  - An environment manifest per batch.
  - Quiet-machine protocol: quit all apps, Do Not Disturb, Wi-Fi off, Spotlight indexing paused, display asleep, `caffeinate` holds the system awake.
- **D10 Analysis:**
  - All tests non-parametric: Kruskal–Wallis + Dunn with Holm correction; Mann–Whitney U; Spearman ρ.
  - Effect sizes: Cliff's δ and ε², with bootstrap CIs.
  - TOST equivalence test with a ±5% margin (at least twice the instrument's worst-case boundary error) for null results.
  - α = 0.05, with Holm correction within each hypothesis family.
- **D11 Profilers:**
  - JFR (`settings=profile`) for Java-level causes: thread starts, park/sleep, GC, hot methods.
  - `powermetrics --samplers tasks,cpu_power` for OS-level wakeups and per-cluster residency.
  - On Intel, `perf stat` (context switches, CPU migrations, cycles per core type).
  - All profiling runs are separate passes (2 forks per selected cell), never during energy runs.

**JFR familiarity evidence** (same benchmark, SLEEP workload, p = 8, one recording of about 14 s each):
- **VT:** 19 OS thread starts, 241,664 sleep events, 1 GC.
- **PT:** 189,191 OS thread starts and 189,189 thread ends, 54 GCs, and 3.3× more allocation samples (2,252 vs 686).
- The mechanism (thread creation and its allocation and GC pressure) is visible to the profiler.
- Caveat: JFR's `jdk.VirtualThreadStart` events are disabled by default in the profile settings and must be enabled explicitly.

## 8. GQM, RQs, hypotheses (§4 uses these verbatim)

**General goal:** Analyze Java thread management constructs (sequential baseline, platform threads, fixed thread pools, Fork/Join, virtual threads) for the purpose of characterizing with respect to energy consumption and its relationship to execution time from the point of view of Java developers in the context of heterogeneous (P/E) multicore processors.

**G1:** Analyze the concurrency level of these constructs for the purpose of evaluating whether the 2014 energy–concurrency relationship still holds with respect to energy per operation and execution time from the point of view of Java developers in the context of DVFS-managed hybrid processors.
- RQ1.1 How does energy/op vary with the concurrency level, per construct and workload?
- RQ1.2 Is sequential execution the lowest-energy option?
- RQ1.3 Is lower execution time associated with lower energy/op across configurations ("faster = greener")?

**G2:** Analyze virtual threads for the purpose of comparison with platform-thread-based constructs with respect to energy per operation, execution time and power from the point of view of Java developers in the context of CPU-bound, blocking and network-I/O workloads.
- RQ2.1 How does VT energy/op compare with each other construct, per workload?
- RQ2.2 At which concurrency levels, if any, does VT have the lowest energy/op?

**G3:** Analyze the restriction of execution to efficiency cores for the purpose of evaluating the energy cost of asymmetry-unaware scheduling with respect to energy per operation and its split across core clusters from the point of view of Java developers and runtime implementers in the context of P/E hybrid processors.
- RQ3.1 Does restricting execution to E cores change energy/op, and at what time cost?
- RQ3.2 How is CPU energy split between P and E clusters under default scheduling, and does the split differ between constructs?

**Hypotheses** (H1 is the negation of H0):

| Id | H0 |
|---|---|
| H0 (main) | The thread management construct has no effect on energy per operation for any workload |
| H0-1.1 | For a given construct and workload, energy/op does not differ across concurrency levels |
| H0-1.2 | Energy/op of sequential execution does not differ from that of the lowest-energy concurrent configuration |
| H0-1.3 | Across configurations, time/op and energy/op are not monotonically associated (Spearman ρ = 0) |
| H0-2.1 | For a given workload and concurrency level, VT energy/op does not differ from that of each other construct |
| H0-2.2 | At concurrency level p, VT energy/op is not lower than that of every alternative (FP_p, FJ_p, PT, SEQ) |
| H0-3.1 | Energy/op under E-core restriction does not differ from energy/op under default scheduling |
| H0-3.2 | The E-cluster share of CPU energy does not differ between constructs |

**Analysis per hypothesis:**
- **Per-run value:** the median of the 5 measured iterations.
- **Descriptive:** medians, IQR and CV; Λ curves (energy vs p); energy-vs-time scatter; cluster-split bars.
- **Normality:** Shapiro–Wilk, expected to fail, so everything is non-parametric. α = 0.05, Holm correction within each family.
- **Tests:**
  - **H1.1:** Kruskal–Wallis across p within construct × workload (FP, FJ, VT × 3 workloads = 9 tests); Dunn post-hoc with Holm correction; ε².
  - **H1.2:** split-sample. Forks 1–5 select the lowest-median concurrent configuration per workload; forks 6–10 are used for Mann–Whitney U of SEQ vs that configuration; Cliff's δ.
  - **H1.3:** Spearman ρ between cell-median time/op and energy/op per workload (23 cells per workload).
  - **H2.1:** per workload × p, Kruskal–Wallis across FP, FJ, VT; Dunn tests of VT vs each; Cliff's δ.
  - **H2.2:** an intersection–union test. VT_p must be significantly lower than every alternative (one-sided Mann–Whitney U) to reject. Report the smallest such p, with δ.
  - **Blocking workloads (SLEEP, SOCKET):**
    - The decisive H2.1 contrasts are VT vs PT and VT vs FP_256 / FJ_256.
    - FP/FJ at p < 256 are additionally expressed as the ratio of measured time/op to the analytic floor ⌈256/p⌉ × d, and as energy/op beyond the floor duration.
    - VT's time advantage at p < 256 is reported as expected by construction, not as evidence for H1-2.x.
  - **H3.1:** Mann–Whitney U, DEFAULT vs BACKGROUND, per cell; Cliff's δ; time penalty (%) with bootstrap 95% CI.
  - **H3.2:** Kruskal–Wallis of the E-share across constructs.
  - **Main H0:** rejected if, for any workload, Kruskal–Wallis across constructs at p = 8 (plus SEQ and PT) rejects after Holm correction.
- **Null results:** TOST via a bootstrap 90% CI of the ratio of medians within [0.95, 1.05].
- **Sample size:** use the pilot fork-to-fork CV to compute the n needed to detect a 10% difference with power 0.8 (Mann–Whitney U, ARE 0.955); if n > 10, add forks to the key comparisons.

## 9. Design size and schedule (§4.5 and §7)

**Experiment 1** (RQ1.x, RQ2.x): a full factorial of construct × p × workload under DEFAULT QoS.
- Per workload: SEQ 1 + PT 1 + FP 7 + FJ 7 + VT 7 = 23 cells.
- 3 workloads, so 69 cells.

**Experiment 2** (RQ3.x): BACKGROUND QoS with p ∈ {4, 16}.
- Per workload: SEQ, PT, FP×2, FJ×2, VT×2 = 8 cells.
- 3 workloads, so 24 cells. The DEFAULT counterparts come from Experiment 1.

**Runs:**
- 10 forks per cell gives (69 + 24) × 10 = **930 runs**, in one randomised schedule, in batches of about 40 with a 60 s idle baseline each.
- Each run takes about 31 s of JMH (5×1 s + 5×5 s + JVM start), up to 15 s more for slow cells (e.g. FP/SLEEP at p=1, where one op takes about 3.1 s), plus a 10 s cooldown: about 45 s on average.
- 930 × 45 s ≈ **11.6 h**.

**Machine time:** Mac ≈ 16.5 h in total (main runs 11.6 h, idle baselines, ancillaries AX2–AX7 ≈ 1.5 h, profiling passes ≈ 1.5 h, a second pilot with sample-size check ≈ 1 h). Intel ≤ 15 h, if it is available. Total ≈ 32 h, **under 40 h**, leaving about 8 h for re-runs.

**Schedule** (`tab:schedule`; assumes the A3 deadline is the end of week 9, Fri 30 Oct, to be confirmed on Canvas):

| Dates | Activity | Machine time |
|---|---|---|
| 3–7 Oct | Implement SEQ, recursive FJ, VT carrier control, SOCKET workload, run orchestrator, ancillary scripts, analysis scripts | – |
| 8 Oct | Ancillary AX2–AX7, pilot 2, sample-size check | 3 h |
| 9–11 Oct | Mac Experiments 1 + 2 (3 overnight batches) | 12 h |
| 12 Oct | Profiling passes | 1.5 h |
| 13–16 Oct | Mac analysis; 16 Oct Intel go/no-go | – |
| 17–20 Oct | Intel arm (if available) | ≤ 15 h |
| 19–26 Oct | Final report | – |
| 27–30 Oct | Replication package, presentation | – |

**Ancillary experiments:**
- AX1: refresh cadence (done; `tab:refresh`).
- AX2: refresher overhead (preliminary in the pilot; A3 repeats it with 3×60 s interleaved runs per interval).
- AX3: IOReport vs `powermetrics` CPU Power consistency.
- AX4: load scaling, 0–10 busy threads.
- AX5: sleep calibration, 10⁴ sleeps per thread kind on each platform.
- AX6: BACKGROUND confinement check (P-cluster residency ≈ 0, plus the frequency effect).
- AX7: run-order and thermal drift check (correlation of per-run energy with run index; thermal and power-limit logs).

## 10. References available (`paper/refs.bib`, all verified)

**From A1:** `pinto2014energy`, `shimchenko2024scheduling`, `vankempen2025green`, `kim2015racing`, `aragonjurado2025faster`, `raffin2025dissecting`, `shanjaikumar2026virtualthreads`, `basili1994gqm`, `becker2015karlskrona`, `jep444`, `pereira2017energy`, `iea2025energyai`.

**New in A2:**
- **Methodology:**
  - `jedlitschka2008reporting`: reporting guidelines.
  - `castor2024primer`: energy-estimation primer.
  - `khan2018rapl`: RAPL validated against physical measurement.
  - `mytkowicz2009wrong`: measurement bias from innocuous setup changes. Motivates randomisation.
  - `georges2007rigorous`: statistically rigorous Java performance evaluation; multiple VM invocations. Motivates fork = unit.
- **Related work** (each needs a stated limitation):
  - `stocker2026energyupgrades` (JSS 2026):
    - Finding: in a Spring PetClinic REST benchmark on Xeon, Ryzen and Apple M1, newer JVMs and enabling virtual threads (Java 21/23) saved substantial energy without code changes.
    - Limitation: one I/O-bound CRUD workload, per-process software energy estimation (JoularJX), no comparison against thread pools or Fork/Join, no hybrid-core placement, JDK 21/23.
  - `sirotic2025virtual` (MIPRO 2025):
    - Finding: on a CPU-bound prime-counting task, Java 21 virtual threads were slightly slower than an executor with platform threads; it also covers Fork/Join and parallel streams.
    - Limitation: runtime only, no energy, a single toy workload, no hybrid cores.
  - `hubner2025apple` (IPDPSW 2025):
    - Finding: characterises M1–M4 performance and power for HPC kernels using `powermetrics`.
    - Limitation: HPC dense linear algebra, not Java or concurrency constructs. It never validates `powermetrics` against an external meter, and it states that `powermetrics` values are software estimates.

## 11. LaTeX environment

- Preamble additions in `main.tex`: `pifont`, `pgfplots` (`compat=1.18`), `\yes` = `\ding{51}`, `\changed{...}` = blue text, `\todo{...}` = red bold text.
- Build: `cd paper && tectonic -X compile main.tex`.
- Section files are `\input` from `main.tex`: `sec-planning.tex`, `sec-measurement.tex`, `sec-threats.tex` (holds §6, §7 and §8).
- To test-compile a section file alone, use a scratch wrapper. Copy `paper/{acmart.cls,ACM-Reference-Format.bst,refs.bib}` plus this file into a temp dir:

```latex
\documentclass[sigconf,nonacm]{acmart}
\usepackage{pifont}\usepackage{pgfplots}\pgfplotsset{compat=1.18}
\newcommand{\yes}{\ding{51}}\newcommand{\changed}[1]{\textcolor{blue}{#1}}
\newcommand{\todo}[1]{\textcolor{red}{\textbf{[#1]}}}
\begin{document}\title{t}\maketitle
\input{sec-XXX}
\bibliographystyle{ACM-Reference-Format}\bibliography{refs}
\end{document}
```
