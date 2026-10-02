| strategy | workload | ms_per_op | J_per_op | W | cv_J_per_op | J_per_op_active |
|---|---|---|---|---|---|---|
| PLATFORM_THREADS | CPU | 148.7 | 2.338 | 15.73 | 0.005931 | 1.795 |
| FIXED_POOL | CPU | 287.7 | 2.897 | 10.07 | 0.001503 | 1.847 |
| FORK_JOIN | CPU | 293.1 | 2.842 | 9.686 | 0.005668 | 1.773 |
| VIRTUAL_THREADS | CPU | 162 | 2.156 | 13.29 | 0.005011 | 1.565 |
| PLATFORM_THREADS | IO | 32.55 | 0.21 | 6.957 | 0.1195 | 0.09132 |
| FIXED_POOL | IO | 327.9 | 1.168 | 3.576 | 0.01299 | -0.02813 |
| FORK_JOIN | IO | 329.6 | 1.152 | 3.483 | 0.007073 | -0.0497 |
| VIRTUAL_THREADS | IO | 10.88 | 0.03977 | 3.669 | 0.01036 | 9.831e-05 |

Notes (2 Oct 2026, JDK 25.0.4.1, RAPL package domain, p = 8, unpinned, 3 forks x 5 x 5 s;
CPU-bound forks warmed up 12 x 5 s = 60 s heat-soak per D9b, IO forks 5 x 1 s):

- Heat-soak held every CPU-bound fork in one power regime: within-fork CV of package J per
  iteration 0.3-3.2 %, fork-to-fork CV of J/op 0.1-0.5 %. The A1 pilot's 62 -> 25 J drop
  did not recur. coretemp 56 C at start, 60 C at end.
- Idle baseline: use idle-start.json (package 3.647 W, psys 15.68 W). idle-end.json
  (package 14.99 W, uncore 7.10 W) is contaminated: the operator returned to the machine
  while it was being recorded. A3's orchestrator must run the quiet gate before every
  idle baseline, not only before benchmark runs.
- Blocking workload: package power is flat at idle level (3.5-3.7 W) for FP, FJ and VT, so
  their J/op is idle power x time/op and idle-subtracted J/op is ~0. PT is the exception
  (6.96 W; core domain 13.7 J vs 2.8 J per window): creating 256 OS threads per op costs
  measurable energy even on a blocking workload. VT vs PT at equal concurrency: 0.040 vs
  0.210 J/op (package), 10.9 vs 32.6 ms/op.
- Linux Thread.sleep overshoot is small: FP/IO 327.9 ms vs the 320 ms floor (2.5 %),
  against 43 % on macOS in the Mac pilot.
- CPU-bound rows carry the known p = 8 confound (pools on 8 workers, PT/VT on all 16
  cores); the full design resolves it with p up to 256.
