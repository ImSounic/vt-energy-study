# Energy Behaviour of Java Thread Management Constructs on Hybrid Processors

Replication package of the Green Software Development course project (University of Twente, 2026) by Sounic Akkaraju and Vasil Zapryanov.

The study revisits Pinto, Castor & Liu (OOPSLA 2014) for JDK 25 and JEP 444 virtual threads. It compares five constructs (sequential execution, one platform thread per task, fixed thread pools, Fork/Join, and virtual threads) at concurrency levels 1 to 256 under CPU-bound, sleep, loopback-socket, and mixed workloads on two hybrid processors:
- an Apple Mac mini M4, measured with IOReport counters: 930 runs, plus a 280-run control with thread pools reused across operations;
- an Intel Core Ultra 7 255H, measured with RAPL: a reduced 318-run campaign with equal-count P/E/LP-E core pinning.

The report is `paper/main.tex`; the results are summarized per platform in [docs/a3-mac-results.md](docs/a3-mac-results.md) and [docs/a3-intel-results.md](docs/a3-intel-results.md).

## Reproduce the report's results (no special hardware)

Every table and figure is regenerated from the raw data in `results/` in under a minute, with Docker:

```bash
docker build -t vt-energy-analysis .
```
```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/reproduced:/out" vt-energy-analysis
```

or with Python 3.14:

```bash
python3 -m venv .venv && .venv/bin/pip install -r analysis/requirements.txt
```
```bash
PYTHON=.venv/bin/python ./reproduce.sh
```

Outputs land in `reproduced/`; [docs/replication.md](docs/replication.md) (Section 5) maps each file to its table or figure.

## Rerun the measurements

Rerunning the experiments needs the original kind of hardware and `sudo` (macOS IOReport with `powermetrics`, or Linux RAPL), a quiet machine, and several hours per campaign. [docs/replication.md](docs/replication.md) gives the toolchain, the per-session preparation, every campaign command as it was run, and the limitations to replicability (Section 7).

```bash
cd harness && mvn -B -DskipTests package && cd ..
```
```bash
python3 scripts/run_experiment.py --platform intel --campaign reduced --cells-file results/intel/reduced-cells.csv --forks 3 --dry-run
```

## Layout

| Path | Content |
|---|---|
| `harness/` | Java 25 + JMH 1.37 benchmarks (constructs, workloads, reused-pool control), energy profilers (RAPL, IOReport via FFM), the SOCKET delay server, ancillary tools |
| `scripts/run_experiment.py` | Campaign orchestrator: randomized schedule, quiet gate, idle baselines, resume, re-queue |
| `scripts/linux/`, `scripts/mac/`, `scripts/ancillary/` | Environment and quiet checks; ancillary experiments AX2–AX6 and SRV |
| `analysis/` | `analyse.py` (hypothesis tests), `cell_summary.py`, `report_figures.py`, and the `vtenergy` package |
| `results/` | Raw data of every campaign (`results/<platform>/<campaign>/`), ancillaries, pilots |
| `reproduce.sh`, `Dockerfile` | One-command regeneration of the analysis |
| `paper/` | The ACM `acmart` report (LaTeX) |
| `docs/` | Replication guide, result summaries, plans, and the execution log |

## Tests

```bash
(cd harness && mvn -B test)
```
```bash
python3 -m unittest discover -s scripts -p 'test_run_experiment.py'
```
```bash
(cd analysis && ../.venv/bin/python -m unittest discover -s tests)
```
