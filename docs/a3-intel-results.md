# A3 Intel results (reduced campaign, 30 Oct 2026)

Platform: Intel Core Ultra 7 255H laptop (6 P, 8 E, 2 LPE cores), Linux, JDK 25, JMH 1.37.
Energy: RAPL `package-0` (whole package, including uncore and idle power; the Mac figures are CPU clusters only).
Power profile `balanced` (EPP `balance_performance`), all apps closed, Wi-Fi off.

## Design and deviation from the A2 plan

The full Intel campaign (705 runs, 5 forks, about 14.5 h) did not fit before the deadline. Instead we ran a **reduced campaign** that covers every run type with fewer levels and forks:

| Part | Cells | Content |
|---|---|---|
| Unpinned CPU, SLEEP, SOCKET | 45 | SEQ, PT; FP, FJ, VT at p = 4, 16, 256; reused FP, FJ (control) at p = 16, 256 |
| Unpinned MIXED | 7 | the Mac control set: PT, FP 256, FJ 256, reused FP/FJ 256, VT 16, VT 256 |
| Pinned 2P, 2E, 2LPE (taskset, first two cores of each class) × CPU, SLEEP, SOCKET | 54 | SEQ, PT, FP 4, FJ 4, VT 4, reused FP 4 |

- 106 cells × **3 forks** = 318 runs, all `ok`, in 10 batch executions. Every idle pair agreed (3.2–4.0 W, ceiling 6 W). Two batches were rerun after a stop and resume.
- Cells: `results/intel/reduced-cells.csv`. Data: `results/intel/reduced/`. Sleep and socket latency (AX5): `results/ancillary/intel/`.
- **Statistics:** with 3 forks, Mann-Whitney cannot reach p < 0.05 (the smallest two-sided p for 3 vs 3 is 0.10). The Intel results are therefore **descriptive**: medians, plus whether the min–max ranges of the 3 forks overlap. The H0-1.2 confirmation stage and the profile campaign were not run.
- 53 of 318 runs have an iteration more than the regime tolerance away from the run median (`regime_flag`). They are kept, as on the Mac.

Values below are medians of 3 forks, raw package J/op unless marked. `active` is idle-subtracted.

## AX5 latency (quiet)

| | median | p99 |
|---|---|---|
| `Thread.sleep(10)`, platform thread | 10.13 ms | 10.38 ms |
| `Thread.sleep(10)`, virtual thread | 10.31 ms | 10.80 ms |
| SOCKET round trip | 10.38 ms | 12.10 ms |

There is no timer coalescing in the default class, unlike the Mac's background QoS (a 10 ms sleep took 177 ms there).

## RQ1: CPU work, unpinned

| construct | p | J/op | ms/op | package W | P / E clock (MHz) |
|---|---|---|---|---|---|
| SEQ | – | 8.38 | 1976 | 4.2 | 983 / 770 |
| VT | 4 | 3.70 | 510 | 7.2 | 1900 / 928 |
| VT | 16 | 2.14 | 163 | 13.1 | 2240 / 1700 |
| VT | 256 | **2.12** | 162 | 13.1 | 2123 / 1700 |
| FP reused | 256 | 2.14 | 162 | 13.2 | 2208 / 1695 |
| FJ reused | 256 | 2.16 | 163 | 13.2 | 2099 / 1699 |
| FP new each op | 256 | 2.92 | 117 | **25.0** | 3725 / 3145 |
| FJ new each op | 256 | 2.82 | 113 | **25.0** | 3229 / 3222 |
| PT | – | 2.72 | **109** | **25.0** | 1919 / 2950 |

- At p ≥ 16, VT and the reused pools sit at 2.12–2.16 J. That is **4.0× less energy than sequential, at 12× the speed** (Mac: 2.4× and 6.7×).
- **Faster is not always greener on Intel.** Thread per task and the rebuilt pools at p = 256 run at the package's PL1 limit (25 W), with E cores at about 3.1 GHz instead of 1.7 GHz. They finish 28–33% faster (109–117 ms against 162 ms) but use **28–38% more energy** (2.72–2.92 J against 2.12 J). The 3-fork ranges do not overlap.
  - The rank correlation of time and energy over the 15 unpinned CPU cells is **ρ = 0.45** (Mac: 0.99).
  - The likely mechanism is DVFS: the governor runs the cores at higher clocks, and so higher voltage, when threads are created continuously. We observe the clocks but do not prove the cause.
- At equal clocks the construct barely matters. VT, reused FP and reused FJ at 256 are within 2% (2.12, 2.14 and 2.16 J; the VT and reused-FP fork ranges are 2.10–2.14 and 2.14–2.17 J).

## RQ2: SLEEP and SOCKET, unpinned

The package figure includes about 3.3 W of idle power, so raw J/op is roughly power × time: slow configurations pay for the time they spend waiting.

SLEEP:

| construct | p | J/op | ms/op | active J/op |
|---|---|---|---|---|
| VT | 4 | **0.038** | **10.7** | 0.002 |
| VT | 16 | 0.040 | 10.9 | 0.005 |
| FJ reused | 256 | 0.079 | 13.0 | 0.038 |
| FP reused | 256 | 0.089 | 18.5 | 0.024 |
| PT | – | 0.201 | 31.6 | 0.100 |
| VT | 256 | 0.208 | 15.4 | 0.158 |
| FP new each op | 256 | 0.281 | 42.9 | 0.144 |
| FJ new each op | 256 | 0.326 | 50.4 | 0.142 |
| FP reused / FP new / FJ new / FJ reused | 16 | 0.57–0.64 | 164–183 | – |
| SEQ | – | 9.33 | 2602 | – |

SOCKET:

| construct | p | J/op | ms/op | active J/op |
|---|---|---|---|---|
| VT | 4 | **0.106** | **18.6** | 0.047 |
| VT | 16 | 0.125 | 19.7 | 0.060 |
| FP reused | 256 | 0.136 | 21.4 | 0.067 |
| FJ reused | 256 | 0.146 | 21.2 | 0.078 |
| VT | 256 | 0.242 | 21.3 | 0.164 |
| PT | – | 0.289 | 38.2 | 0.162 |
| FP new each op | 256 | 0.360 | 48.9 | 0.197 |
| FJ new each op | 256 | 0.411 | 60.3 | 0.217 |

1. **Rebuilding pools costs a lot on Intel too.** At p = 256, reused pools use 3.2–4.1× (SLEEP) and 2.6–2.8× (SOCKET) less energy than rebuilt ones, and run 2.3–3.9× faster. The per-operation rebuild bias found on the Mac reproduces.
2. **The best virtual-thread configuration beats the best reused pool.** VT with 4 carriers against a reused pool of 256:
   - SLEEP: 0.038 against 0.079–0.089 J, 2.1–2.3× less, and faster (10.7 against 13–18.5 ms).
   - SOCKET: 0.106 against 0.136–0.146 J, 22–27% less, and faster (18.6 against 21.2–21.4 ms).
   - The 3-fork ranges do not overlap.
3. **At equal width (256 carriers against 256 workers), VT loses to reused pools,** as on the Mac SOCKET slide: 0.208 against 0.079–0.089 J on SLEEP, and 0.242 against 0.136–0.146 J on SOCKET. VT at 256 carriers draws 11–13 W, against 5–7 W for the reused pools.
   - The VT carrier count is a parameter. Few carriers is VT's efficient setting; a pool has to be as wide as the concurrency it needs.
   - The Mac shows the same pattern: VT 1–64 carriers use 0.0003–0.0004 J against 0.0012 J at 256. The Mac slides compared at 256 only.

## MIXED (1.5 ms compute, then 10 ms sleep), unpinned

| construct | p | J/op | ms/op |
|---|---|---|---|
| VT | 16 | **1.158** | **28.8** |
| FJ new each op | 256 | 1.218 | 54.8 |
| FP reused | 256 | 1.221 | 31.1 |
| VT | 256 | 1.241 | 30.4 |
| FJ reused | 256 | 1.254 | 29.7 |
| FP new each op | 256 | 1.282 | 52.9 |
| PT | – | 1.314 | 39.0 |

- Energy is within 13% across all constructs. VT with 16 carriers is lowest and fastest; reused FP is 5% higher.
- Rebuilt pools are about 1.8× slower than reused ones (53–55 ms against 30–31 ms).
- This matches the Mac: VT is the fastest on MIXED, with energy within a few percent of the reused pools.
- One reused-FP fork read 0.85 J, so its range overlaps VT 16.

## RQ3: pinned to two cores of one class

SLEEP, thread per task against VT with 4 carriers:

| arm | PT J/op | PT W | PT ms | VT J/op | VT ms | PT / VT |
|---|---|---|---|---|---|---|
| 2P | 0.195 | 12.5 | 15.5 | 0.037 | 10.7 | 5.2× |
| 2E | 0.129 | 7.8 | 16.5 | 0.037 | 10.7 | **3.5×** |
| 2LPE | 0.264 | 4.2 | 63.0 | 0.038 | 11.1 | 6.9× |

SOCKET: 2P 0.297 against 0.099 J (3.0×); 2E 0.210 against 0.088 J (2.4×); 2LPE 0.628 against 0.172 J (3.7×).

- **The placement effect is confirmed by direct pinning.** The same thread-per-task workload costs 1.5× more on two P cores than on two E cores (0.195 against 0.129 J; 12.5 W against 7.8 W, at the same speed). VT is unaffected: 0.037 J on every class, because its carriers are mostly asleep.
- **On the same cores, VT still uses 3.5× (E) to 5.2× (P) less than thread per task on SLEEP.** This is the Intel counterpart of the Mac's 62× → 3.3× (both on E cores). The two platforms agree on about 3× on efficiency cores.
- The LPE cores are slow for thread creation: PT takes 63 ms instead of 16 ms, so the package pays idle power for longer.
- With p = 4 on two cores, FP, FJ and reused FP sleep in waves (650–690 ms, 2.2–2.6 J) on every class, as the bounded design predicts.

CPU work on two cores (median over the five parallel constructs, p = 4 or PT):

| arm | J/op | ms/op | package W |
|---|---|---|---|
| 2P | 5.39–5.53 | 1017–1041 | 5.3–5.4 |
| 2E | 5.12–5.33 | 1273–1296 | 4.0–4.1 |
| 2LPE | 8.26–9.18 | 1485–1908 | 5.0–5.6 |

- Two E cores use about 5% less energy than two P cores, but are 25% slower.
- The LPE cores are worse on both: they are slower, and the package's fixed power accumulates for longer.
- Within an arm, the pools and VT are within 3%. PT is up to 4% higher, and 9% higher on 2LPE (9.18 J, 1908 ms).

## What the report should say

1. **Reproduced on both platforms:**
   - At equal clocks the construct does not matter for CPU work.
   - Pools rebuilt every operation are a large bias for waiting work.
   - On the same efficiency cores, VT uses about 3–3.5× less than thread per task on SLEEP.
   - VT is the fastest on MIXED.
2. **Intel-only:**
   - "Faster is greener" fails when speed comes from higher clocks: thread per task and rebuilt pools at 25 W are faster and use more energy (ρ = 0.45).
   - Direct pinning shows P cores cost 1.5× more than E cores for the same blocking work.
3. **Correction to the Mac reading:** comparing VT at 256 carriers is VT's worst case. With few carriers, VT beats the best reused pool on Intel (SLEEP 2.1–2.3×, SOCKET 22–27%). The Mac data agree for SLEEP (VT 1–64 carriers use 0.0003–0.0004 J, against reused FP 0.0011 J).
4. **Limitations:**
   - 3 forks, so the results are descriptive only.
   - A reduced level grid and no confirmation or profile stage.
   - RAPL package energy includes uncore and idle power, so Mac and Intel absolute values are not comparable.
   - The frequency mechanism is observed, not proven.
