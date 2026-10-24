# Replication guide

This guide covers how to rebuild the harness, rerun every campaign, and regenerate every table and figure of the report. Design rationale is in `paper/` (Sections 4 and 5) and in `docs/superpowers/plans/2026-10-24-assignment-3-implementation.md` (decisions A3-D1 to A3-D12).

## 1. Toolchain

| | Intel arm | Mac arm |
|---|---|---|
| Machine | Intel Core Ultra 7 255H (6P + 8E + 2LP-E), 32 GB, CachyOS (kernel 7.2) | Mac mini M4 (`Mac16,10`, 4P + 6E), 16 GB, macOS 27.0 |
| JDK | Temurin 25.0.4.1, at `~/.local/opt/jdk-25` (`mise install java@temurin-25.0.4+101.0.LTS`) | Homebrew `openjdk@25` 25.0.4.1 |
| Build | Maven 3.9.16, JMH 1.37 | the same, plus Apple clang (IOReport shim) |
| Analysis | Python 3.14 with `analysis/requirements.txt` | the same |

```bash
cd harness && mvn -B -DskipTests package          # -> harness/target/benchmarks.jar
bash harness/native/build.sh                       # Mac only: IOReport shim
python3 -m venv .venv && .venv/bin/pip install -r analysis/requirements.txt
```

Tests:

```bash
(cd harness && mvn -B test)    # the 2 RaplReaderTest hardware tests need readable RAPL
python3 -m unittest discover -s scripts -p 'test_run_experiment.py'
(cd analysis && ../.venv/bin/python -m unittest discover -s tests)
```

## 2. Before every measurement session

**Intel**
1. Run `sudo scripts/enable-rapl.sh` once per boot. It makes `/sys/class/powercap/*/energy_uj` readable.
2. Run `powerprofilesctl set balanced`. Every CPU's `energy_performance_preference` must be `balance_performance`, and the runner refuses to start otherwise. With the `performance` profile, idle package power roughly doubles and every wakeup boosts to maximum frequency.
3. Put the laptop on AC power. Quit every application, including the Claude app, browsers, and chat clients. The quiet gate fails while a deny-listed application runs (`scripts/linux/quiet-check.sh`), and an idle baseline above 6 W stops the campaign. Turn Wi-Fi off; SOCKET uses loopback only.
4. Optional, for the profiling campaign's `perf stat`: `sudo pacman -S perf`.

Note that the binding sustained package limit is the firmware's MMIO RAPL PL1 of **25 W** (`intel-rapl-mmio:0`), not the MSR value of 65 W. CPU-bound cells at p ≥ 16 run power-capped at 25 W, and the env manifests log both domains.

**Mac**
1. Run `sudo sysctl kern.ipc.somaxconn=1024`. The default of 128 overflows with 256 simultaneous connects.
2. Use AC power and keep Low Power Mode off.
3. Quiet the machine:
   - Quit all applications except Terminal and turn on Do Not Disturb.
   - Turn Wi-Fi off.
   - `sudo mdutil -a -i off` (re-enable afterwards with `-i on`).
   - Let the display sleep. The runner holds the system awake with `caffeinate` until it exits.
4. The runner asks for `sudo` once (for `powermetrics`) and keeps the ticket alive. If the ticket expires anyway, a batch fails at once instead of waiting at a password prompt.

**Both platforms:** start campaigns inside `tmux` (or `screen`). On Linux the runner blocks sleep, idle suspend, and the lid switch through `systemd-inhibit` for as long as it runs. Closing the terminal or `kill` aborts the current run cleanly, and the campaign resumes on the next invocation.

Every run is gated: the CPU must be ≥ 95 % idle over 3 s. If the machine never becomes quiet within 10 minutes, the campaign stops cleanly.

## 3. Campaigns (Mac first, then Intel)

`scripts/run_experiment.py` runs one campaign into `results/<platform>/<campaign>/`. Rerunning the same command resumes it, and Ctrl-C finishes the current run and stops. Use `--dry-run` to see the run count and a time estimate.

Mac first, in order (smoke test: see `docs/a3-handoff.md`):

```bash
python3 scripts/run_experiment.py --platform mac --campaign pilot2 --subset pilot --forks 3
```
```bash
bash scripts/ancillary/ax2-refresh-overhead.sh
```
```bash
bash scripts/ancillary/ax3-readpath.sh
```
```bash
bash scripts/ancillary/ax4-load-scaling.sh
```
```bash
bash scripts/ancillary/ax5-latency.sh
```
```bash
bash scripts/ancillary/ax6-ecore.sh
```
```bash
bash scripts/ancillary/srv-overhead.sh
```
```bash
python3 scripts/run_experiment.py --platform mac --campaign main --subset full --forks 10
```
```bash
python3 scripts/run_experiment.py --platform mac --campaign profile --mode profile --subset profile
```

Then Intel, in order (the laptop is in daily use, so it runs at night: Ctrl-C in the morning, rerun the same command the next night to resume):

```bash
python3 scripts/run_experiment.py --platform intel --campaign pilot2 --subset pilot --forks 3
```
```bash
bash scripts/ancillary/ax4-load-scaling.sh
```
```bash
bash scripts/ancillary/ax5-latency.sh
```
```bash
bash scripts/ancillary/srv-overhead.sh
```
```bash
python3 scripts/run_experiment.py --platform intel --campaign main --subset full --forks 5
```
```bash
.venv/bin/python analysis/vtenergy/select_best.py results/intel/main > results/intel/confirm-cells.csv
```
```bash
python3 scripts/run_experiment.py --platform intel --campaign confirm --cells-file results/intel/confirm-cells.csv --forks 5
```
```bash
python3 scripts/run_experiment.py --platform intel --campaign profile --mode profile --subset profile
```

Estimated machine time (from `--dry-run`):

| Campaign | Runs | Estimate |
|---|---|---|
| Intel pilot2 | 99 | 2.1 h |
| Intel main | 705 | 14.5 h |
| Intel confirm | 30 | 0.6 h |
| Intel profile | 38 | 0.7 h |
| Mac main | 930 | 14.2 h |

## 4. What a campaign directory contains

| File | Content |
|---|---|
| `schedule.csv` | Every planned run: run_id, order, batch, cell, fork_index, seed |
| `progress.csv` | One appended row per attempt. The latest row of a run is its status (`ok`, `failed`, `timeout`, or `discarded`) |
| `runs/<run_id>.json`, `<run_id>.a<attempt>.log` | The JMH result of the one fork, and the command plus JMH output of every attempt |
| `batches/<batch>/` | `env-start.txt`, `env-end.txt`, `idle-start.json`, `idle-end.json`, `server.json` (SOCKET server requests and CPU time), and on the Mac `powermetrics.txt` |
| `batches.csv` | Primary-domain idle power at batch start and end, and whether they agree |
| `profile/` | JFR recordings (profile campaigns) and `profile.csv` |

Rules applied by the runner and the analysis:
- An interrupted batch resumes as `<batch>-2`.
- A batch execution counts as verified only if both idle baselines exist and agree: within 10 % on Intel, within max(10 %, 10 mW) on the Mac. The runs of an unverified execution are re-run once, as `<batch>-r1` (at most 40 runs per execution).
  - This list is rebuilt from `batches.csv` and `progress.csv` on every start, so it survives any stop.
  - Runs that are still unverified afterwards are flagged in `runs.csv` (`idle_mismatch`, `idle_unverified`).
- A run that fails or times out is retried once, in `retryNN` executions. A timed-out run's whole process group, including the forked benchmark JVM, is killed.
- One unexpected error ends only its batch; two in a row stop the campaign.

## 5. Regenerating the results

```bash
.venv/bin/python analysis/analyse.py --campaign results/intel/main --confirm results/intel/confirm --out results/intel/analysis
```
```bash
.venv/bin/python analysis/analyse.py --campaign results/mac/main --out results/mac/analysis
```
```bash
.venv/bin/python analysis/vtenergy/profile.py results/intel/profile
```
```bash
.venv/bin/python analysis/vtenergy/ancillary.py ax4 results/ancillary/intel/ax4
```

`analyse.py` writes:
- `runs.csv`: one row per fork.
- `cells.csv`: median, IQR, and CV per cell.
- `tests.csv`: every hypothesis test of report Table 4, with Holm-adjusted p, effect size, and bootstrap CI.
- `power.csv`.
- `figures/*.pdf`: Λ curves, energy vs time, cluster split, and placement.

Set `--sleep-d-ms` to the AX5 median `Thread.sleep(10)` latency of the platform for the floor ratios.
