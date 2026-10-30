# Replication guide

This guide covers how to regenerate every table and figure of the A3 report from the committed data, how to rebuild the harness, and how to rerun every campaign. Design rationale is in `paper/` (Sections 4 and 5) and in `docs/superpowers/plans/2026-10-24-assignment-3-implementation.md` (decisions A3-D1 to A3-D12).

**Fastest path (no special hardware):** `./reproduce.sh` (Python) or the Docker image (Section 5) rebuilds every analysis output of the report in under a minute from the raw data in `results/`. Rerunning the *measurements* needs the original hardware (Section 7).

## 1. Toolchain

| | Intel arm | Mac arm |
|---|---|---|
| Machine | Intel Core Ultra 7 255H (6P + 8E + 2LP-E), 32 GB, Arch-based Linux (Omarchy), kernel 7.2.8 | Mac mini M4 (`Mac16,10`, 4P + 6E), 16 GB, macOS 27.2 (build 26B118) |
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

## 3. Campaigns

`scripts/run_experiment.py` runs one campaign into `results/<platform>/<campaign>/`. Rerunning the same command resumes it, and Ctrl-C finishes the current run and stops. Use `--dry-run` to see the run count and a time estimate. A campaign defined by `--cells-file` runs exactly the cells listed in that CSV (`construct,p,workload,restriction`).

### 3.1 What was run for the A3 report

| Campaign | Directory | Runs | Command |
|---|---|---|---|
| Mac ancillaries AX2–AX6, SRV | `results/ancillary/mac/` | – | the `scripts/ancillary/*.sh` scripts below |
| Mac main (Experiments 1 and 2) | `results/mac/main/` | 930 (93 cells × 10 forks) | `--platform mac --campaign main --subset full --forks 10` |
| Mac reused-pool control (+ MIXED) | `results/mac/control/` | 280 (28 cells × 10 forks) | `--platform mac --campaign control --cells-file results/mac/control-cells.csv --forks 10` |
| Intel AX5 | `results/ancillary/intel/` | – | `bash scripts/ancillary/ax5-latency.sh` |
| Intel reduced campaign | `results/intel/reduced/` | 318 (106 cells × 3 forks) | `--platform intel --campaign reduced --cells-file results/intel/reduced-cells.csv --forks 3` |

Mac, in order (smoke test: see `docs/a3-handoff.md`):

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
python3 scripts/run_experiment.py --platform mac --campaign control --cells-file results/mac/control-cells.csv --forks 10
```
```bash
python3 scripts/run_experiment.py --platform mac --campaign profile --mode profile --subset profile
```

Intel (after the preparation of Section 2; it ran in one day with the laptop idle):

```bash
bash scripts/ancillary/ax5-latency.sh && python3 scripts/run_experiment.py --platform intel --campaign reduced --cells-file results/intel/reduced-cells.csv --forks 3
```

### 3.2 The full Intel arm of the A2 plan (not run)

The A2 plan's Intel arm (705 runs, 5 forks, about 14.5 h, then a 30-run confirmation stage and a profile campaign) did not fit before the deadline; the reduced campaign above replaced it (report Section 4.5). To run it:

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

| Campaign | Runs | Estimate | Actual |
|---|---|---|---|
| Mac main | 930 | 14.2 h | about 15 h |
| Mac control | 280 | – | 3.7 h |
| Intel reduced | 318 | 6.3 h | ran 06:04–19:50 with two stops and resumes |
| Intel main (not run) | 705 | 14.5 h | – |

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

Every table and figure of the report comes from the committed raw data. Either run the script with the analysis environment of Section 1:

```bash
PYTHON=.venv/bin/python ./reproduce.sh
```

or use the container, which needs only Docker:

```bash
docker build -t vt-energy-analysis .
```
```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/reproduced:/out" vt-energy-analysis
```

Both write to `reproduced/`:

| Output | Script | Report |
|---|---|---|
| `mac/analysis/cells.csv`, `tests.csv`, `power.csv`, `runs.csv` | `analysis/analyse.py` (Mac main, `--sleep-d-ms 15.03 --socket-d-ms 12.34` from AX5) | Table 5; Mac columns of Tables 6–8; cluster split |
| `mac/analysis/figures/*.pdf` | `analysis/analyse.py` | Figure 1 (`lambda.pdf`) and further figures |
| `mac/control-cells.csv` | `analysis/cell_summary.py` | reused-pool and MIXED rows of Tables 6 and 7 |
| `intel/reduced-cells.csv` | `analysis/cell_summary.py` | Intel columns of Tables 6–8 |
| `ancillary/{mac,intel}/*-summary.csv` | `analysis/vtenergy/ancillary.py` | AX3–AX6, SRV (Sections 5, 6, 8) |
| `figures/cpu-energy-vs-time.pdf`, `figures/mac-lambda.pdf` | `analysis/report_figures.py` | Figures 1 and 2 |

`analyse.py` runs every hypothesis test of the plan, with Holm-adjusted p, effect size, and bootstrap CI (seeded, so reruns are identical). The control and reduced campaigns are outside the full design, so `cell_summary.py` reports per-cell medians, IQR, and CV for them; the Intel results are descriptive (3 forks). The Mac profile campaign (38 runs, 2 forks per cell) was recorded on 25 Oct but not analyzed in time; its 580 MB of JFR recordings are kept on the Mac, not in this package. `analysis/vtenergy/profile.py results/mac/profile` summarizes them.

To rebuild the report PDF: `cd paper && make` (uses `tectonic` if installed, otherwise `pdflatex` and `bibtex`).

## 6. Data inventory

| Directory | Content |
|---|---|
| `results/mac/main/` | Mac main campaign: 930 JMH JSON files, schedule, progress, batch manifests and idle baselines (compressed `powermetrics` logs) |
| `results/mac/control/`, `results/mac/control-cells.csv` | Reused-pool control (280 runs) and its cell list |
| `results/mac/analysis/` | The committed output of `analyse.py` for the Mac main campaign |
| `results/intel/reduced/`, `results/intel/reduced-cells.csv` | Intel reduced campaign (318 runs, frequency logged per iteration) and its cell list |
| `results/ancillary/{mac,intel}/` | AX2–AX6 and SRV raw data and summaries |
| `results/pilot*/` | A2 feasibility pilots |
| `docs/a3-mac-results.md`, `docs/a3-intel-results.md` | Plain-text result summaries per platform |

Excluded from git: JMH console logs (`*.log`), uncompressed `powermetrics` logs, the Mac profile campaign's JFR recordings (580 MB), and the Mac runs from before an automatic OS update (kept on the Mac, not used).

## 7. Limitations to replicability

- **Hardware and OS.** Energy comes from on-chip counters: Apple IOReport (through a C shim and the FFM API, plus `sudo powermetrics` as refresher) on an M-series Mac, and Intel RAPL through Linux powercap. Other processors give other absolute values; the study compares configurations on one machine, so rankings and ratios are what should replicate.
- **No container for the measurements.** A container cannot read IOReport (macOS has no native containers; Docker on macOS runs a Linux VM), and RAPL inside a container needs privileged access to the host's powercap files and still measures the whole host. The container therefore covers the analysis only.
- **Privileges.** `sudo` is needed for `powermetrics` (Mac), for making RAPL readable (`scripts/enable-rapl.sh`), and for raising `kern.ipc.somaxconn` (Mac).
- **Quiet machine.** Results depend on an idle machine (Section 2); open applications raised Intel idle power from 3.6 to 8.5–14 W in a discarded pilot. The runner's quiet gate, idle ceiling, and EPP check enforce this.
- **Firmware and OS versions.** The Intel sustained power limit (PL1 25 W) is set by the laptop firmware, and macOS updates change the energy model; the env manifests in every batch record both.
- **Apple's counters are unvalidated estimates**; no wall-power meter was used.
