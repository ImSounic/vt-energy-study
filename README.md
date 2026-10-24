# Energy Behaviour of Java Concurrency Constructs on Hybrid CPUs

Course project for Green Software Development, University of Twente, 2026.

Replicates and extends Pinto, Castor & Liu (OOPSLA 2014) for JEP 444 virtual
threads. It compares five constructs (sequential, platform thread per task,
fixed pool, Fork/Join, virtual threads) at seven concurrency levels under CPU,
sleep and loopback-socket workloads. It runs on a three-tier Intel Core Ultra 7
255H (RAPL) and an Apple M4 (IOReport).

## Layout
- `harness/`: Java 25 + JMH benchmarks, energy profilers (RAPL, IOReport via FFM), the SOCKET delay server, and ancillary tools (`tools/`)
- `scripts/`:
  - `run_experiment.py`: campaign orchestrator (randomized schedule, quiet gate, idle baselines, resume)
  - `linux/`, `mac/`: environment and quiet-check scripts
  - `ancillary/`: AX2–AX6 and SRV
- `analysis/`: `analyse.py` and the `vtenergy` package (loading, non-parametric tests, figures)
- `paper/`: LaTeX (ACM `acmart`) reports
- `results/`: pilots, campaigns (`results/<platform>/<campaign>/`), ancillary results
- `docs/`: plans, fact sheets, and the [replication guide](docs/replication.md)

## Quick start
```bash
cd harness && mvn -B -DskipTests package && cd ..
```
```bash
python3 scripts/run_experiment.py --platform intel --campaign main --subset full --forks 5 --dry-run
```

- Current state and next steps: [docs/a3-handoff.md](docs/a3-handoff.md).
- Setup, full run order, and how to regenerate every result: [docs/replication.md](docs/replication.md).
