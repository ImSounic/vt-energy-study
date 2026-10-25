# Mac arm: results summary (main campaign, 25 Oct 2026)

- **Source:** `results/mac/main/` (930 runs = 93 cells × 10 forks, 0 failures, 24 batches whose idle pairs all agree at 0.009–0.020 W). The analysis is `results/mac/analysis/` (`cells.csv`, `tests.csv`, `power.csv`, `figures/`), produced by `analysis/analyse.py --sleep-d-ms 15.03 --socket-d-ms 12.34`.
- **Platform:** Mac mini M4, macOS 27.2 (26B118), JDK 25.0.4.1, on Wi-Fi. Energy is `CPU_Energy` (IOReport) unless stated.

## Ancillaries (`results/ancillary/mac/`)

| AX | Result |
|---|---|
| AX2 refresher overhead | Idle 0.050 / 0.064 / 0.030 W at 1000 / 250 / 100 ms: not monotonic, so noise dominates and the overhead is **not resolvable** (< ~0.03 W) |
| AX3 read path | IOReport / powermetrics CPU power = 1.05, 1.07, 1.05 at 1, 4, 10 threads: **consistent** |
| AX4 load scaling | 0.008, 3.9, 7.6, 7.4, 9.6, then 10.1 to 11.2 W for 0 to 10 threads (linear fit R² = 0.73). **Not linear**, because of per-cluster DVFS (P cluster first, then E). Throughput is near-linear (~248 ops/s per P core, ~135 per E core) |
| AX5 sleep and RTT | `Thread.sleep(10)` median **15.03 ms** (platform) and 15.04 ms (virtual), so d = 15.03. BACKGROUND QoS: median **177 ms** / 170 ms, p90 210 ms (timer coalescing). SOCKET round trip 12.34 ms, the same under BACKGROUND |
| AX6 E-core confinement | BACKGROUND: PCPU 0.0001 W, P residency 0 %, E cluster at **1090 MHz** (DEFAULT: 2752 MHz E / 3756 MHz P). 0.25 W vs 10.0 W, 305 vs 1157 ops/s, so **≈ 0.83 vs 8.7 mJ per op** |
| SRV server overhead | Idle without / with / without the server: 0.0107 / 0.0092 / 0.0111 W, so **not measurable** |

## Experiment 1 (DEFAULT QoS)

**CPU (Mandelbrot)**
- SEQ, and every pool at p = 1, run at ≈ 1030 ms and 4.05 J/op (one P core at 3.9 W).
- J/op falls monotonically with p down to **≈ 1.70 J/op at p ≥ 16** (≈ 154 ms, 11 W). That is **2.4× less energy than SEQ**: the opposite of Pinto et al. 2014.
- H0-1.3: **faster = greener** (Spearman ρ = 0.987 over 23 cells).
- At equal p the constructs are within 3 % of each other (PT 1.731, VT_256 1.704, FP_256 1.745). VT_256 is lowest (H0-2.2 IU rejected at p = 256 only).
- Fork-to-fork CV is < 1 %.

**SLEEP (10 ms; quiet-Mac d = 15 ms)**

| Construct | ms/op | CPU J/op | Memory J/op |
|---|---|---|---|
| VT (p = 1 to 64) | 14.5 | **0.0003** | 0.0008 |
| VT_256 | 14.4 | 0.0012 | |
| PT | 21.3 | 0.0187 | 0.0034 |
| FP_256 | 20.0 | 0.0445 | 0.011 |
| FJ_256 | 23.5 | 0.0337 | |
| SEQ | 3728 | 0.041 raw / 0.004 idle-subtracted | |

The bounded pools follow the ⌈256/p⌉×d floor.

**SOCKET (loopback, 10 ms server delay)**

| Construct | ms/op | CPU J/op |
|---|---|---|
| VT_4 (VT minimum) | 19.9 | 0.031 |
| VT_256 | 20.6 | 0.049 |
| PT | 18.5 | 0.061 |
| FP_256 / FJ_256 | 21 | 0.112 |
| SEQ | 3119 | 0.060 |

**Caution:** the bounded pools at p = 8–64 use *less* CPU-cluster energy per op than VT (FP_16 0.010, FJ_64 0.0097 J/op), but they are **3–20× slower** (57–405 ms vs 20 ms). CPU-cluster energy does not charge them for the static power of the longer operation; this is the report's "static power seen only in part" threat. VT is lowest only at equal concurrency (p = 256: VT 0.049 < PT 0.061 < FP/FJ 0.112). The same pattern appears on SLEEP for idle-subtracted values (figure `lambda.pdf`).

**Tests**
- **Main:** every workload's KW test rejects (ε² 0.85–0.94).
- **H0-1.2:** SEQ is not the lowest-energy option on any workload (split sample, δ = 1).
- **H0-2.2 on blocking workloads:** VT_256 is significantly lower than PT, FP_256 and FJ_256 (one-sided p = 0.0001, δ = −1). It is **not** lower than SEQ on the idle-subtracted measure the A2 plan prescribes: SEQ's idle-subtracted J/op is about 0, because it mostly sleeps, while its raw J/op is 34× VT's. **The report must discuss both measures.**

## Experiment 2: BACKGROUND QoS vs DEFAULT (H0-3.1; time and energy ratios, BACKGROUND / DEFAULT)

| Workload | Time | Energy | Note |
|---|---|---|---|
| CPU | 4.2–5.5× slower | **0.07–0.13×** (8–15× less) | |
| SLEEP | 10–11.6× slower | 7–11× more | timer coalescing to ~170 ms; PT is the exception at 0.39× |
| SOCKET | 1.0–1.8× | 0.69–1.62× | |

H0-3.1: 14 tests reject, 10 do not. H0-3.2: the E-cluster share differs between constructs on every workload and p (KW ε² 0.60–0.91).

## Threats observed
- **AX7 drift:** run order correlates with energy on SLEEP (ρ = 0.30) and SOCKET (ρ = 0.20), but not on CPU. Batch idle rose from ~0.009 to ~0.012 W over the 15 h. The randomized order spreads this drift over all cells.
- **OS:** an automatic update (27.2 Beta 2 → 27.2) rebooted the Mac in the first attempt. Those runs are kept outside git (`results/aborted-macos-beta/`), and the campaign was rerun entirely on 26B118.
