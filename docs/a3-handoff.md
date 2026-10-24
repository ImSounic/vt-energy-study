# A3 handoff: run the Mac arm first, then Intel (state of 24 Oct 2026, 23:00)

Read this first on the Mac, whether you are Sounic or a Claude session. It is self-contained. Details are in `docs/replication.md` (commands) and `docs/superpowers/plans/2026-10-24-assignment-3-implementation.md` (decisions A3-D1 to A3-D12, plus the execution log of everything found so far).

**Deadline:** A3 (results, final report, replication package, presentation) is due **Fri 30 Oct**.

## Status

| | Done (branch `assignment-3`) | Still to do |
|---|---|---|
| Harness (B1–B4) | SEQ; recursive Fork/Join bounded at p threads; VT carrier check; p ∈ {1,2,4,8,16,64,256}; SLEEP and SOCKET workloads + NIO delay server | — |
| Orchestrator (B5) | `scripts/run_experiment.py`: randomized schedule, quiet gate with app deny-list, gated idle baselines with a quiet ceiling, resume after any stop, re-queue of unverified batches, retries, keep-awake, profile mode | First use on the Mac (smoke run below) |
| Ancillaries (B6) | `scripts/ancillary/` AX2–AX6 and SRV, plus `analysis/vtenergy/ancillary.py` | Run them |
| Analysis (B7) | `analysis/analyse.py` + `vtenergy`: every hypothesis family of the report, Holm, Cliff's δ, bootstrap, TOST, power, figures | Run it on real data |
| Intel arm (B8) | Frequency logging, pinning arms, power-profile and EPP preflight | Two nights of runs, after the Mac |
| Replication (B9) | `docs/replication.md`, README, pinned requirements | Final pass after the runs |

**Tests on Linux:** 58 Java (the 2 RAPL hardware tests need `sudo scripts/enable-rapl.sh`), 37 orchestrator, 57 analysis. **No energy campaign has produced valid data yet.**

**The Mac code paths have not been run since the A2 pilot.** That covers the IOReport profiler under the new runner, `taskpolicy -b` through `scripts/mac/bg-java.sh`, the cooldown that waits for Nominal thermal pressure, the Mac quiet-check deny-list, and the ancillary scripts. Do the smoke run before anything long.

## Order of work (the user decided on 24 Oct: Mac first, then Intel)

1. **Mac** (this machine; it is the primary platform in the A2 plan): set up, smoke test, ancillaries, the main campaign (930 runs, about 14 h, can be split over several sessions), then the profile campaign.
2. **Intel laptop:**
   - The laptop is in daily use, so it runs only at night (Ctrl-C in the morning, resume the next night).
   - Main: 705 runs ≈ 14.5 h ≈ two nights (Exp 1 ≈ 7.1 h, placement arm ≈ 7.4 h).
   - Then the H0-1.2 confirmation (30 runs) and the profile campaign.
3. **Analysis and final report:** see "For the report" at the end.

## 0. State of the Mac (checked over SSH on 24 Oct, 23:00)

- **Reachable:** `ssh imsounic@mac.home` uses the laptop's key; Remote Login is on.
- **Repo:** a clone of this repo is at `~/vt-energy` on `assignment-3`, up to date.
  - `gh` is **not** logged in on the Mac, and `git pull` over SSH fails (the keychain is locked in SSH sessions).
  - Code reaches the Mac from the laptop with `git push mac assignment-3:refs/heads/from-laptop`, followed on the Mac by `git merge --ff-only from-laptop`.
  - Results come back with `git fetch mac`, or with `git push` from the Mac's own GUI terminal.
- **Built and tested:**
  - Toolchain: JDK 25.0.4.1, Maven, Python 3.14, tectonic, tmux.
  - The IOReport shim (29 channels) and `benchmarks.jar`.
  - `.venv`, with 57 analysis tests and 37 orchestrator tests OK.
  - Java: all tests pass except the SOCKET tests, which need `somaxconn` raised (next item).
- **`kern.ipc.somaxconn` is 128.** That resets SOCKET connections above 128 concurrent: 3/20 operations failed at 200, and 19/20 at 256. It must be set to 1024 after every boot (section 2). The runner checks it.
- **macOS is now 27.2, a beta build (26B5091g)**, not the 27.0 (26A428) of the A2 pilot. State this in the report. The smoke test shows whether the IOReport refresh still behaves as AX1 measured.

- **Animated Aerial wallpaper and screen saver.** `WallpaperAerials` plus `VTDecoderXPCService` decoding video after a few idle minutes made CPU idle swing between 93 and 98 %.
  - The quiet gate then failed at random, and the idle baselines disagreed (0.014 vs 0.03–0.12 W, mostly P cores).
  - The user switched to a static wallpaper and screen saver. After that the median idle was 99.2 % (min 96.0 %).
  - **Keep it that way** on the Mac, and on any machine that reruns this.
- **Wi-Fi stays on** (`en1`) because the Mac is controlled over SSH; Ethernet is not connected. `airportd` and `kernel_task` use a few % of CPU. **Report this as a deviation** from the quiet protocol: it is a small, constant cost for every construct.
- **24 Oct, 23:31:** the ancillaries (AX2–AX6, SRV) started, then `--campaign main` (930 runs, about 14 h), in tmux session `vt` on the Mac. Do not SSH in while it runs: logins show up in the measurements.

## 1. Mac setup (once; already done on 24 Oct, kept for replication)

Clone the repo and switch to the branch:

```bash
gh repo clone ImSounic/vt-energy ~/vt-energy && cd ~/vt-energy && git switch assignment-3
```

Install the toolchain. Skip what is already installed; `python@3.14` provides a Python ≥ 3.11 for the analysis venv:

```bash
brew install openjdk@25 maven python@3.14 tectonic
```

Check the versions. Expect 25.0.4.1, Maven 3.9.x, and Python ≥ 3.11:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home && $JAVA_HOME/bin/java -version && mvn -v | head -1 && python3 --version
```

Build the IOReport shim (needs the Xcode command-line tools) and run its smoke test:

```bash
bash harness/native/build.sh
```

Build the benchmark jar and run the tests:

```bash
cd harness && mvn -B -DskipTests package && mvn -B test; cd ..
```

On the Mac the RAPL tests are skipped. One IOReport test is skipped unless powermetrics is running; that is expected.

Create the analysis environment:

```bash
python3 -m venv .venv && .venv/bin/pip install -r analysis/requirements.txt
```

## 2. Before every Mac session

Raise the listen backlog. The default of 128 overflows with 256 simultaneous SOCKET connects, and the setting resets at reboot:

```bash
sudo sysctl kern.ipc.somaxconn=1024
```

Pause Spotlight indexing. Re-enable it afterwards with `sudo mdutil -a -i on`:

```bash
sudo mdutil -a -i off
```

Then make the machine quiet:
- Use AC power and keep Low Power Mode off.
- Turn on Do Not Disturb and turn Wi-Fi off. SOCKET uses loopback only.
- **Quit every app except Terminal**: browsers, Claude, Discord, Slack, Spotify, Mail, Messages, Code, and so on. `scripts/mac/quiet-check.sh` refuses to measure while a deny-listed app runs and lists the offenders.
- Run inside `tmux` (`brew install tmux`), so that closing the terminal cannot interrupt anything.
- The display may sleep; the runner holds the system awake with `caffeinate`.

**If you use the Mac with apps open, nothing is measured.** RAPL and IOReport count the whole chip, not the JVM. The A2 pilot showed 9× idle CPU power with everyday apps open, and the 24 Oct Intel pilot was invalid for this reason (see the execution log). Stop with **one Ctrl-C**, then rerun the same command later to resume.

## 3. Mac smoke test (about 5 min; do it first)

```bash
python3 scripts/run_experiment.py --platform mac --campaign smoke --subset smoke --forks 1 --idle-seconds 20
```

It asks for the sudo password once (for powermetrics). Expect `done: 3 of 3 runs ok`. Then check the results:
- `results/mac/smoke/runs/*.json` contain `ioreport.CPU_Energy.J_per_op`.
- `batches.csv` has both idle values: around 0.02–0.03 W when quiet, and below the 0.08 W ceiling.
- `batches/b01/` contains `powermetrics.txt.gz` and `server.json`.

Next, check the BACKGROUND wrapper. Write a one-cell file, then run it:

```bash
printf 'construct,p,workload,restriction\nFIXED_POOL,4,CPU,BACKGROUND\n' > /tmp/bg-cell.csv
```

```bash
python3 scripts/run_experiment.py --platform mac --campaign smoke-bg --cells-file /tmp/bg-cell.csv --forks 1 --idle-seconds 20
```

In the run JSON, `ioreport.PCPU.J` should be close to 0 next to `ioreport.ECPU.J`, because BACKGROUND confines the JVM to the E cores. A large PCPU means `taskpolicy -b` is not working.

If anything fails, look at `results/mac/smoke/runs/<run_id>.a1.log` first. When both checks pass, delete `results/mac/smoke*`.

## 4. Mac campaigns

Run the ancillaries (about 25 min) in one quiet session:

```bash
bash scripts/ancillary/ax2-refresh-overhead.sh && bash scripts/ancillary/ax3-readpath.sh && bash scripts/ancillary/ax4-load-scaling.sh && bash scripts/ancillary/ax5-latency.sh && bash scripts/ancillary/ax6-ecore.sh && bash scripts/ancillary/srv-overhead.sh
```

Main campaign: 93 cells × 10 forks = 930 runs, about 14.2 h. It can be split: Ctrl-C once, then rerun the same command to resume.

```bash
python3 scripts/run_experiment.py --platform mac --campaign main --subset full --forks 10
```

Profile campaign (JFR, 38 runs, about 0.7 h):

```bash
python3 scripts/run_experiment.py --platform mac --campaign profile --mode profile --subset profile
```

Use `--dry-run` on any of these to see the run count and the estimate without running anything.

**Fallback if time runs out:** the plan allows 7 forks per cell. That needs a new campaign name, because a schedule is fixed per campaign:

```bash
python3 scripts/run_experiment.py --platform mac --campaign main7 --subset full --forks 7
```

Do not mix forks counts within one campaign.

**Check after each session:** in `results/mac/main/batches.csv`, `agree` should mostly be True. The runner re-runs unverified batches once by itself (`bNN-r1`).

## 5. Commit the data

After each campaign:

```bash
git add results/ && git commit -m "data: mac main campaign" && git push
```

Raw powermetrics text and JFR files are git-ignored. The gzipped logs, JSON and CSV files are committed.

## 6. Intel arm afterwards (laptop, nights only)

Before every night:
1. `sudo scripts/enable-rapl.sh` (once per boot).
2. `powerprofilesctl set balanced`. The runner requires EPP `balance_performance`; the laptop is normally on `performance`.
3. Quit every app, including the Claude app and Zen. Turn Wi-Fi off, keep the lid open, and leave the charger in.
4. Start everything inside tmux.

First night (ancillaries ≈ 30 min, then main):

```bash
bash scripts/ancillary/ax4-load-scaling.sh && bash scripts/ancillary/ax5-latency.sh && bash scripts/ancillary/srv-overhead.sh && python3 scripts/run_experiment.py --platform intel --campaign main --subset full --forks 5
```

In the morning, press Ctrl-C once. The next night, rerun only the `run_experiment.py` command; it resumes.

When main is complete, pick the confirmation cells:

```bash
.venv/bin/python analysis/vtenergy/select_best.py results/intel/main > results/intel/confirm-cells.csv
```

Run the confirmation stage (30 runs):

```bash
python3 scripts/run_experiment.py --platform intel --campaign confirm --cells-file results/intel/confirm-cells.csv --forks 5
```

Run the profile campaign:

```bash
python3 scripts/run_experiment.py --platform intel --campaign profile --mode profile --subset profile
```

## 7. Analysis

Mac:

```bash
.venv/bin/python analysis/analyse.py --campaign results/mac/main --out results/mac/analysis --sleep-d-ms <AX5 median sleep on the Mac>
```

Intel:

```bash
.venv/bin/python analysis/analyse.py --campaign results/intel/main --confirm results/intel/confirm --out results/intel/analysis --sleep-d-ms <AX5 median on Intel>
```

JFR counts:

```bash
.venv/bin/python analysis/vtenergy/profile.py results/mac/profile
```

Each ancillary summary is produced with `.venv/bin/python analysis/vtenergy/ancillary.py <ax3|ax4|ax5|ax6|srv> results/ancillary/mac[/<axN>]`.

## For the report (findings so far that A3 must state)

1. **Intel's binding sustained limit is the firmware's MMIO RAPL PL1 = 25 W** (`intel-rapl-mmio:0`), not the MSR value of 65 W.
   - CPU-bound cells at p ≥ 16 run power-capped at 25 W.
   - The A1 "power-regime shift" (62 → 25 J per 1 s iteration) is this cap.
   - **Correct** the A2 sentence "the RAPL limits (PL1 65 W, PL2 115 W) were not reached".
2. **Pitfall (6), 24 Oct Intel pilot.** With a browser and the Claude app open and the `performance` power profile:
   - Idle package power was 8.5–14 W instead of 3.65 W.
   - Every batch's idle pair disagreed.
   - PT/SLEEP drew 26 W instead of 6.5 W.
   - The response was the app deny-list in the quiet gate, the idle ceiling, and the EPP preflight. The data were discarded.
3. **Deviations from A2:**
   - Intel H0-1.2 by a confirmation stage (A3-D6): 5 forks split 2/3 cannot reach p < 0.05.
   - The Mac idle-agreement rule has a 10 mW floor (A3-D9): the two quiet pilot baselines differed by 32 %.
   - Fork/Join is capped at p threads. JDK 25 did not compensate anyway, so the cap is a safeguard; it does not explain the A2 FJ anomaly.
   - SOCKET clients close with SO_LINGER 0, which avoids running out of ports.
4. **Blocking workloads.**
   - Idle-subtracted J/op of FP, FJ and VT is at the detection limit. Power for it is 0.04–0.13 at n = 10, and adding forks cannot fix it.
   - The decisive contrasts are therefore PT vs VT, raw energy, and (Mac) memory-subsystem energy.
5. **Schedule estimates:** Mac main 14.2 h and Intel main 14.5 h. The A2 report said 12 h and about 13 h. Both are inside the 40 h total.
6. **AX5 on Intel** (24 Oct, not quiet, indicative only): `Thread.sleep(10)` takes 10.13 ms on a platform thread and 10.26 ms on a virtual thread, and the SOCKET round trip 10.14 ms. Rerun AX5 quietly for the report.
