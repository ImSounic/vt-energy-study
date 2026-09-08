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
