# Intel pilot facts (2 Oct 2026) for the A2 report

Source: results/pilot-intel/{pilot.json,idle-start.json,env.txt}. Settings: JDK 25.0.4.1 (Temurin), RAPL via powercap, p = 8, unpinned, 3 forks x 5 x 5 s measured; CPU-bound forks warmed up 12 x 5 s (60 s heat-soak), IO forks 5 x 1 s. Quiet gate passed at 99 percent idle. Idle baseline (idle-start.json): package 3.647 W, psys 15.68 W. idle-end.json is CONTAMINATED (operator returned to the machine; package 14.99 W) and must not be used.

Table values: medians of per-fork medians; W = median over forks of (window J / window s); CV = fork-to-fork CV of pkg J/op; IO floor = ceil(256/8) x 10 ms = 320 ms.

| Construct | Workload | ms/op | pkg J/op | pkg W | CV | psys J/op | pkg J/op idle-subtracted | core J per 5 s window |
|---|---|---|---|---|---|---|---|---|
| PLATFORM_THREADS | CPU | 148.7 | 2.338 | 15.71 | 0.5% | 4.419 | 1.795 | 59.44 |
| FIXED_POOL | CPU | 287.7 | 2.897 | 10.07 | 0.1% | 6.444 | 1.847 | 34.03 |
| FORK_JOIN | CPU | 293.1 | 2.842 | 9.69 | 0.5% | 6.426 | 1.773 | 32.60 |
| VIRTUAL_THREADS | CPU | 162.0 | 2.156 | 13.28 | 0.4% | 4.306 | 1.565 | 48.47 |
| PLATFORM_THREADS | IO | 32.6 | 0.210 | 6.54 | 9.8% | 0.625 | 0.091 | 13.24 |
| FIXED_POOL | IO | 327.9 | 1.168 | 3.56 | 1.1% | 4.658 | -0.028 | 1.62 |
| FORK_JOIN | IO | 329.6 | 1.152 | 3.49 | 0.6% | 4.582 | -0.050 | 1.55 |
| VIRTUAL_THREADS | IO | 10.9 | 0.040 | 3.65 | 0.8% | 0.154 | 0.000 | 2.78 |

Regime check (CPU-bound, package J per 5 s iteration, within-fork CV): PT 0.3/0.3/0.3 percent, FP 1.6/2.7/0.5, FJ 0.8/3.2/0.3, VT 0.4/1.6/1.7. No iteration deviates more than 10 percent from its fork median; the A1 pilot's 62 to 25 J drop did not recur. coretemp 56 C at start, 60 C at end. RAPL limits logged: PL1 = 65 W (28 s window), PL2 = 115 W; CPU-bound forks drew 10 to 16 W package, far below PL1, so the A1 regime shift was not a PL1 cap; describe it as a power-regime shift of unconfirmed cause (plausibly platform thermal policy), not as PL2 to PL1.

IO floor: FP 327.9 ms and FJ 329.6 ms vs the 320 ms floor (2.5 and 3.0 percent over), against 43 percent over on the Mac (458.6 ms). On Intel, package power for FP, FJ and VT on IO equals the idle baseline within 0.1 W, so J/op = idle power x time/op and idle-subtracted J/op is about 0 (sign is noise). PT draws 6.54 W on IO (core domain 13.2 J per window vs 2.8 J for VT): creating 256 OS threads per operation is measurable even on a blocking workload. VT vs PT at equal concurrency: 0.040 vs 0.210 pkg J/op, 10.9 vs 32.6 ms/op.

Cross-platform caveat: Intel package idle 3.65 W vs Mac CPU_Energy idle 0.020 W (about 180x); the instruments count different things at zero load, so cross-platform comparisons must be of rankings and curve shapes, never absolute J/op.

Design consequence: the Intel arm is no longer conditional (laptop repaired 2 Oct; pilot complete; go/no-go met early). Keep its 5-fork design and the <= 15 h budget; D9b heat-soak confirmed; add 'quiet gate before every idle baseline' to the procedure.
