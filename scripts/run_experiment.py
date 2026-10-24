#!/usr/bin/env python3
"""Runs one measurement campaign of the A3 experiment (standard library only).

A campaign is a randomized schedule of runs; one run is one JMH fork of one
cell (construct x concurrency level x workload x core restriction), i.e. one
trial. Runs execute in batches of about 40, each bracketed by a gated idle
baseline and its environment manifest. Everything is appended to
results/<platform>/<campaign>/, so an interrupted campaign resumes where it
stopped (see docs/superpowers/plans/2026-10-24-assignment-3-implementation.md,
A3-D1 to A3-D12).

  python3 scripts/run_experiment.py --platform intel --campaign main --subset full --forks 5 --dry-run
  python3 scripts/run_experiment.py --platform intel --campaign main --subset full --forks 5

Ctrl-C once: finish the current run, close the batch, stop. Twice: abort now.
Run it inside tmux or screen: closing the terminal stops the campaign (cleanly).
"""
from __future__ import annotations  # macOS /usr/bin/python3 is 3.9

import argparse
import csv
import dataclasses
import datetime
import json
import math
import os
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JAR = REPO / "harness" / "target" / "benchmarks.jar"

CONSTRUCTS = ["SEQUENTIAL", "PLATFORM_THREADS", "FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"]
UNLEVELED = ["SEQUENTIAL", "PLATFORM_THREADS"]  # no concurrency level
POOLED = ["FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"]
LEVELS = [1, 2, 4, 8, 16, 64, 256]
EXP2_LEVELS = [4, 16]  # bracket the Mac's 6 E cores
PILOT_LEVELS = [1, 16, 256]
WORKLOADS = ["CPU", "SLEEP", "SOCKET"]
DEFAULT_RESTRICTION = {"intel": "unpinned", "mac": "DEFAULT"}
PINNED_ARMS = ["2P", "2E", "2LPE"]

SCRIPT_DIR = {"intel": REPO / "scripts" / "linux", "mac": REPO / "scripts" / "mac"}
PROFILER = {"intel": "nl.utwente.gsd.energy.RaplProfiler", "mac": "nl.utwente.gsd.energy.IoReportProfiler"}
PRIMARY_DOMAIN = {"intel": "intel-rapl:0:package-0", "mac": "CPU_Energy"}
# Idle ceiling (W, primary domain): a baseline above it means the machine is not quiet.
# Quiet references: Intel package 3.65 W (2 Oct, balanced EPP), Mac CPU clusters 0.02-0.03 W.
IDLE_CEILING = {"intel": 6.0, "mac": 0.08}
IDLE_RETRIES, IDLE_RETRY_WAIT_S = 5, 60
# Idle agreement: |end - start| <= max(rel * start, abs) (A3-D9).
IDLE_TOLERANCE = {"intel": (0.10, 0.0), "mac": (0.10, 0.010)}
JAVA_HOME = {
    "intel": Path.home() / ".local" / "opt" / "jdk-25",
    "mac": Path("/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home"),
}

BATCH_SIZE = 40
RUN_TIMEOUT_S = 20 * 60
COOLDOWN_S = 10
QUIET_ATTEMPTS, QUIET_WAIT_S = 30, 20
SOCKET_DELAY_MS = 10
SOCKET_PORT = 31000  # below Linux's ephemeral range (32768-60999)
PERF_EVENTS = "context-switches,cpu-migrations,cpu_core/cycles/,cpu_atom/cycles/,cpu_lowpower/cycles/"


@dataclasses.dataclass(frozen=True, order=True)
class Cell:
    construct: str
    p: int | None
    workload: str
    restriction: str

    def key(self):
        return f"{self.construct}-{self.p if self.p is not None else 'x'}-{self.workload}-{self.restriction}"


@dataclasses.dataclass(frozen=True)
class Run:
    run_id: str
    order: int
    batch: str
    cell: Cell
    fork_index: int


# ---------------------------------------------------------------- cells

def _block(workload, restriction, levels):
    return ([Cell(c, None, workload, restriction) for c in UNLEVELED]
            + [Cell(c, p, workload, restriction) for c in POOLED for p in levels])


def cells(platform, subset):
    """The cells of a campaign. full = the design of report Section 4.5."""
    default = DEFAULT_RESTRICTION[platform]
    if subset == "full":
        out = [c for w in WORKLOADS for c in _block(w, default, LEVELS)]  # Experiment 1
        restricted = PINNED_ARMS if platform == "intel" else ["BACKGROUND"]
        out += [c for r in restricted for w in WORKLOADS for c in _block(w, r, EXP2_LEVELS)]
        return out
    if subset == "pilot":
        return [c for w in WORKLOADS for c in _block(w, default, PILOT_LEVELS)]
    if subset == "profile":
        out = [Cell(c, p, "CPU", default) for c, p in
               [("SEQUENTIAL", None), ("PLATFORM_THREADS", None), ("FIXED_POOL", 16),
                ("FORK_JOIN", 16), ("VIRTUAL_THREADS", 16)]]
        for w in ["SLEEP", "SOCKET"]:
            out += [Cell("PLATFORM_THREADS", None, w, default)]
            out += [Cell(c, p, w, default) for p in [8, 256] for c in POOLED]
        return out
    if subset == "smoke":
        return [Cell("VIRTUAL_THREADS", 4, "SLEEP", default), Cell("FIXED_POOL", 4, "CPU", default),
                Cell("PLATFORM_THREADS", None, "SOCKET", default)]
    raise ValueError(f"unknown subset: {subset}")


def cells_from_file(path):
    with open(path, newline="") as f:
        return [Cell(r["construct"], int(r["p"]) if r["p"] else None, r["workload"], r["restriction"])
                for r in csv.DictReader(f)]


# ---------------------------------------------------------------- schedule

def schedule(cell_list, forks, seed, batch_size=BATCH_SIZE):
    """Seeded shuffle of all (cell, fork) runs. Fork indices are fixed before any data exist."""
    pairs = [(cell, k) for cell in cell_list for k in range(1, forks + 1)]
    random.Random(seed).shuffle(pairs)
    return [Run(run_id=f"{i:04d}_{cell.key()}_f{k}", order=i, batch=f"b{i // batch_size + 1:02d}",
                cell=cell, fork_index=k)
            for i, (cell, k) in enumerate(pairs)]


SCHEDULE_FIELDS = ["run_id", "order", "batch", "construct", "p", "workload", "restriction", "fork_index", "seed"]


def write_schedule(path, runs, seed):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(SCHEDULE_FIELDS)
        for r in runs:
            c = r.cell
            w.writerow([r.run_id, r.order, r.batch, c.construct, "" if c.p is None else c.p,
                        c.workload, c.restriction, r.fork_index, seed])


def read_schedule(path):
    with open(path, newline="") as f:
        return [Run(r["run_id"], int(r["order"]), r["batch"],
                    Cell(r["construct"], int(r["p"]) if r["p"] else None, r["workload"], r["restriction"]),
                    int(r["fork_index"]))
                for r in csv.DictReader(f)]


# ---------------------------------------------------------------- topology

def expand_cpus(spec):
    out = []
    for part in filter(None, spec.split(",")):
        lo, _, hi = part.partition("-")
        out += list(range(int(lo), int(hi or lo) + 1))
    return out


def pinned_arms(p_cores, e_cores, lpe_cores):
    """Equal-count arms: the first two cores of each class (A3-D5)."""
    return {arm: ",".join(str(c) for c in expand_cpus(spec)[:2])
            for arm, spec in zip(PINNED_ARMS, [p_cores, e_cores, lpe_cores])}


def server_core(e_cores):
    """The SOCKET server's core: the last E core, outside the 2E arm (A3-D4b)."""
    return str(expand_cpus(e_cores)[-1])


def read_topology():
    out = subprocess.run(["bash", "-c", f"source '{REPO}/scripts/topology.sh'; "
                          'echo "$P_CORES|$E_CORES|$LPE_CORES"'],
                         capture_output=True, text=True, check=True).stdout.strip()
    return out.split("|")


# ---------------------------------------------------------------- commands

def jmh_command(cell, platform, *, java, jar, out_json, socket_port, arms=None,
                mode="energy", profile_dir=None, perf=False):
    argv = []
    if cell.restriction in PINNED_ARMS:
        argv += ["taskset", "-c", arms[cell.restriction]]
    heat_soak = platform == "intel" and cell.workload == "CPU"
    argv += [str(java), "--enable-native-access=ALL-UNNAMED", "-jar", str(jar),
             "-p", f"strategy={cell.construct}",
             "-p", f"parallelism={cell.p if cell.p is not None else 1}",
             "-p", f"workloadType={cell.workload}",
             "-f", "1", "-wi", "12" if heat_soak else "5", "-w", "5s" if heat_soak else "1s",
             "-i", "5", "-r", "5s", "-rf", "json", "-rff", str(out_json), "-foe", "true"]
    props = []
    if cell.construct == "VIRTUAL_THREADS":
        props += [f"-Djdk.virtualThreadScheduler.parallelism={cell.p}",
                  f"-Djdk.virtualThreadScheduler.maxPoolSize={cell.p}"]
    if cell.workload == "SOCKET":
        props.append(f"-Dvtenergy.socket.port={socket_port}")
    if props:  # never -jvmArgs: it would replace the @Fork flags
        argv += ["-jvmArgsAppend", " ".join(props)]
    if cell.restriction == "BACKGROUND":
        argv += ["-jvm", str(REPO / "scripts" / "mac" / "bg-java.sh")]
    if mode == "energy":
        argv += ["-prof", PROFILER[platform]]
    elif mode == "profile":
        argv += ["-prof", f"jfr:dir={profile_dir}"]
        if perf:
            argv += ["-prof", f"perf:events={PERF_EVENTS}"]
    return argv


# ---------------------------------------------------------------- pure checks

def idle_agrees(start_w, end_w, rel, abs_):
    return abs(end_w - start_w) <= max(rel * start_w, abs_)


STATUSES = {"ok", "failed", "timeout", "discarded"}
PROGRESS_FIELDS = ["run_id", "attempt", "status", "batch", "start_utc", "end_utc", "exit_code"]
BATCH_FIELDS = ["batch", "attempt", "primary_domain", "idle_start_W", "idle_end_W", "agree"]


def _append_csv(path, fields, row):
    new = not path.exists()
    if not new and path.stat().st_size:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            torn = f.read(1) != b"\n"  # a line cut short by a crash or power loss
        if torn:
            with open(path, "a") as f:
                f.write("\n")
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fields})
        f.flush()
        os.fsync(f.fileno())


def append_progress(path, row):
    _append_csv(path, PROGRESS_FIELDS, row)


def progress_history(path):
    """run_id -> list of (status, attempt, batch) in file order; malformed lines are skipped."""
    out = {}
    if not path.exists():
        return out
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                row = (r["status"], int(r["attempt"]), r["batch"])
            except (KeyError, TypeError, ValueError):
                continue
            if row[0] in STATUSES:
                out.setdefault(r["run_id"], []).append(row)
    return out


def latest_status(path):
    """run_id -> (status, attempt) of its latest progress row."""
    out = {}
    for run_id, rows in progress_history(path).items():
        best = rows[0]
        for row in rows[1:]:
            if row[1] >= best[1]:
                best = row
        out[run_id] = best[:2]
    return out


def latest_rows(history):
    """run_id -> (status, attempt, batch) of the latest row (ties: the later row)."""
    out = {}
    for run_id, rows in history.items():
        best = rows[0]
        for row in rows[1:]:
            if row[1] >= best[1]:
                best = row
        out[run_id] = best
    return out


def is_retry_execution(batch_exec):
    return "-r" in batch_exec or batch_exec.startswith("retry")


def requeue_candidates(batch_rows, history):
    """Runs to re-run once because their batch execution is not verified (A3-D9).

    An execution is verified iff its batches.csv row says agree=True. Runs whose
    latest row is ok in an unverified, non-retry execution are re-queued, unless
    they were discarded before (each run gets at most one such retry). Derived
    from the files alone, so it survives any stop. Returns {execution: [run_id]}.
    """
    verified = {r["batch"] for r in batch_rows if str(r.get("agree", "")).strip() == "True"}
    out = {}
    for run_id, (status, _, batch) in sorted(latest_rows(history).items()):
        if status != "ok" or batch in verified or is_retry_execution(batch):
            continue
        if any(s == "discarded" for s, _, _ in history[run_id]):
            continue
        out.setdefault(batch, []).append(run_id)
    return out


def failed_once(history):
    """Runs whose latest row failed or timed out and that have not been retried yet."""
    latest = latest_rows(history)
    return sorted(rid for rid, rows in history.items()
                  if latest[rid][0] in ("failed", "timeout")
                  and sum(s in ("failed", "timeout") for s, _, _ in rows) == 1)


def chunks(items, size=BATCH_SIZE):
    return [items[i:i + size] for i in range(0, len(items), size)]


# Per-op time model (s) for the estimate, from the A2 pilots.
CPU_TASK_S = {"intel": 0.009, "mac": 0.0057}
CORES = {"intel": 16, "mac": 10}
SLEEP_D_S = {"intel": 0.0103, "mac": 0.0121}


def op_seconds(cell, platform):
    cores = 2 if cell.restriction in PINNED_ARMS else CORES[platform]
    width = {"SEQUENTIAL": 1}.get(cell.construct, cell.p if cell.p is not None else 256)
    if cell.workload == "CPU":
        return 256 * CPU_TASK_S[platform] / min(width, cores)
    return math.ceil(256 / width) * SLEEP_D_S[platform]


def run_seconds(cell, platform):
    op = op_seconds(cell, platform)
    heat_soak = platform == "intel" and cell.workload == "CPU"
    wi, w = (12, 5.0) if heat_soak else (5, 1.0)
    iteration = lambda length: max(length, op) + op / 2
    return 3 + wi * iteration(w) + 5 * iteration(5.0) + COOLDOWN_S + 3


def estimate_seconds(runs, platform, idle_s=60):
    batches = len({r.batch for r in runs})
    return sum(run_seconds(r.cell, platform) for r in runs) + batches * (2 * (idle_s + 8) + 10)


# ---------------------------------------------------------------- side effects

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


class CampaignStopped(Exception):
    pass


# Helpers run in their own process group, so a Ctrl-C at the terminal reaches only this
# runner (which then closes the batch in order) while they keep the controlling tty for sudo.
# process_group=0 is thread-safe (3.11+); preexec_fn is the fallback for macOS's Python 3.9.
OWN_GROUP = {"process_group": 0} if sys.version_info >= (3, 11) else {"preexec_fn": os.setpgrp}


def tail(path, nbytes=65536):
    """The last ~nbytes of a (possibly huge, still growing) text file."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - nbytes))
        return f.read().decode(errors="replace")


class Campaign:
    def __init__(self, args):
        self.args = args
        self.platform = args.platform
        self.dir = REPO / "results" / args.platform / args.campaign
        self.java_home = Path(os.environ.get("JAVA_HOME") or JAVA_HOME[args.platform])
        self.java = self.java_home / "bin" / "java"
        self.env = dict(os.environ, JAVA_HOME=str(self.java_home))
        self.stop = False
        self.arms, self.server_cpu = None, None
        if self.platform == "intel":
            p, e, lpe = read_topology()
            self.arms, self.server_cpu = pinned_arms(p, e, lpe), server_core(e)
        self.server = None
        self.server_stats = None
        self.energy = args.mode == "energy" and not args.no_energy

    # ---- preflight
    def preflight(self):
        problems = []
        if not JAR.exists():
            problems.append(f"{JAR} missing: run mvn -DskipTests package in harness/")
        for script in ["quiet-check.sh", "env-manifest.sh"]:
            if not (SCRIPT_DIR[self.platform] / script).exists():
                problems.append(f"{SCRIPT_DIR[self.platform] / script} missing")
        if not self.java.exists():
            problems.append(f"{self.java} missing: set JAVA_HOME")
        if self.platform == "intel":
            if self.energy:
                try:
                    Path("/sys/class/powercap/intel-rapl:0/energy_uj").read_text()
                except OSError:
                    problems.append("RAPL not readable: sudo scripts/enable-rapl.sh")
            online = [p.read_text().strip() for p in Path("/sys/class/power_supply").glob("AC*/online")]
            if online and online[0] != "1":
                problems.append("not on AC power")
            epp = sorted({p.read_text().strip() for p in
                          Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/energy_performance_preference")})
            if epp and epp != [self.args.epp]:
                problems.append(f"energy_performance_preference is {', '.join(epp)}, expected {self.args.epp}"
                                f" (balance_performance: powerprofilesctl set balanced)")
        else:
            somax = int(subprocess.run(["sysctl", "-n", "kern.ipc.somaxconn"], capture_output=True,
                                       text=True).stdout.strip() or 0)
            if somax < 1024:
                problems.append(f"kern.ipc.somaxconn={somax}: sudo sysctl kern.ipc.somaxconn=1024")
            if "AC Power" not in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout:
                problems.append("not on AC power")
            pm = subprocess.run(["pmset", "-g"], capture_output=True, text=True).stdout
            if any(line.split()[:2] == ["lowpowermode", "1"] for line in pm.splitlines()):
                problems.append("Low Power Mode is on")
        if problems:
            sys.exit("preflight failed:\n  " + "\n  ".join(problems))
        self.keep_awake()
        if self.platform == "mac" and self.energy:
            # powermetrics restarts every batch, unattended: keep the sudo ticket alive.
            subprocess.run(["sudo", "-v"], check=True)

            def keepalive():
                while True:
                    time.sleep(60)
                    subprocess.run(["sudo", "-n", "true"], capture_output=True)

            threading.Thread(target=keepalive, daemon=True).start()

    def keep_awake(self):
        """Hold off system sleep (and, on Linux, the lid switch) until this process exits."""
        pid = str(os.getpid())
        if self.platform == "mac":
            argv = ["caffeinate", "-i", "-s", "-w", pid]
        elif shutil.which("systemd-inhibit"):
            argv = ["systemd-inhibit", "--what=sleep:idle:handle-lid-switch", "--who=vt-energy",
                    "--why=energy measurement campaign", "--mode=block", "tail", f"--pid={pid}", "-f", "/dev/null"]
        else:
            log("warning: systemd-inhibit not found; make sure the machine cannot suspend")
            return
        inhibitor = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     **OWN_GROUP)
        time.sleep(1)
        if inhibitor.poll() is not None:
            log(f"warning: could not inhibit sleep: {inhibitor.stderr.read().decode().strip()}")

    # ---- helpers
    def sh(self, *argv, **kw):
        return subprocess.run([str(a) for a in argv], env=self.env, **OWN_GROUP, **kw)

    def quiet_gate(self):
        if self.args.no_gate:
            return
        script = SCRIPT_DIR[self.platform] / "quiet-check.sh"
        for attempt in range(1, QUIET_ATTEMPTS + 1):
            if self.sh("bash", script, self.args.min_idle, capture_output=True).returncode == 0:
                return
            if self.stop:
                raise CampaignStopped()
            log(f"machine not quiet (attempt {attempt}/{QUIET_ATTEMPTS}); waiting {QUIET_WAIT_S} s")
            time.sleep(QUIET_WAIT_S)
        raise CampaignStopped("machine never became quiet; close applications and resume")

    def manifest(self, out):
        self.sh("bash", SCRIPT_DIR[self.platform] / "env-manifest.sh", out, capture_output=True, check=True)

    def idle_baseline(self, out):
        """A gated idle baseline; one above the quiet ceiling is retried, then the campaign stops."""
        if not self.energy:
            return None
        ceiling = self.args.idle_ceiling
        for attempt in range(1, IDLE_RETRIES + 1):
            self.quiet_gate()
            self.sh(self.java, "--enable-native-access=ALL-UNNAMED", "-cp", JAR,
                    "nl.utwente.gsd.energy.IdleBaseline", self.args.idle_seconds, out,
                    capture_output=True, check=True)
            watts = json.loads(Path(out).read_text())["watts"][PRIMARY_DOMAIN[self.platform]]
            if watts <= ceiling:
                return watts
            Path(out).rename(Path(out).with_suffix(f".rejected{attempt}.json"))
            log(f"idle power {watts:.3f} W above the quiet ceiling {ceiling} W "
                f"(attempt {attempt}/{IDLE_RETRIES}); waiting {IDLE_RETRY_WAIT_S} s")
            if self.stop:
                raise CampaignStopped()
            time.sleep(IDLE_RETRY_WAIT_S)
        raise CampaignStopped(f"idle power stays above {ceiling} W: background load, or the wrong power profile")

    def start_server(self, stats_json):
        argv = [self.java, "-cp", JAR, "nl.utwente.gsd.workload.SocketDelayServer",
                self.args.socket_port, SOCKET_DELAY_MS, stats_json]
        if self.platform == "intel":
            argv = ["taskset", "-c", self.server_cpu] + argv
        self.server = subprocess.Popen([str(a) for a in argv], env=self.env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, **OWN_GROUP)
        first = []
        reader = threading.Thread(target=lambda: first.append(self.server.stdout.readline().strip()), daemon=True)
        reader.start()
        reader.join(30)
        if not first or not first[0].startswith("READY"):
            self.stop_server()
            raise RuntimeError(f"SocketDelayServer did not start (port {self.args.socket_port} busy?): {first}")
        self.server_stats = stats_json

    def ensure_server(self, bdir):
        if self.server is None or self.server.poll() is not None:
            log("SocketDelayServer not running; restarting it")
            n = len(list(bdir.glob("server*.json")))
            self.start_server(bdir / ("server.json" if n == 0 else f"server-{n + 1}.json"))

    def stop_server(self):
        if self.server is not None:
            self.server.terminate()
            try:
                self.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.wait()
            self.server = None

    def start_refresher(self, bdir):
        if self.platform == "mac" and self.energy:
            self.sh("bash", REPO / "scripts" / "mac" / "powermetrics-start.sh", 100,
                    bdir / "powermetrics.txt", check=True, stdin=subprocess.DEVNULL)

    def stop_refresher(self, bdir):
        if self.platform == "mac" and self.energy:
            self.sh("bash", REPO / "scripts" / "mac" / "powermetrics-stop.sh", stdin=subprocess.DEVNULL)
            log_file = bdir / "powermetrics.txt"
            if log_file.exists():  # ~140 MB per batch at 100 ms: keep it compressed
                self.sh("sudo", "-n", "gzip", "-f", log_file, stdin=subprocess.DEVNULL)

    def cooldown(self, bdir):
        time.sleep(COOLDOWN_S)
        if self.platform != "mac" or not self.energy:
            return
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                pressure = [line for line in tail(bdir / "powermetrics.txt").splitlines() if "pressure level" in line]
            except OSError as e:
                log(f"warning: cannot read powermetrics log ({e}); fixed cooldown only")
                return
            if not pressure or pressure[-1].strip().endswith("Nominal"):
                return
            time.sleep(5)

    # ---- one run
    def execute(self, run, batch_exec, attempt, bdir):
        runs_dir = self.dir / "runs"
        out_json = runs_dir / f"{run.run_id}.json"
        out_json.unlink(missing_ok=True)
        profile_dir = self.dir / "profile" / run.run_id
        # JMH stops JFR via `jcmd ... filename=<path>`, which breaks on spaces in the path
        # (this repo lives under "Green Software Development"): record into a staging dir.
        staging = Path(tempfile.mkdtemp(prefix="vtenergy-jfr-")) if self.args.mode == "profile" else None
        argv = jmh_command(run.cell, self.platform, java=self.java, jar=JAR, out_json=out_json,
                           socket_port=self.args.socket_port, arms=self.arms,
                           mode="none" if self.args.no_energy and self.args.mode == "energy" else self.args.mode,
                           profile_dir=staging, perf=self.args.perf)
        if run.cell.workload == "SOCKET":
            self.ensure_server(bdir)
        start = utc_now()
        log(f"run {run.order + 1} {run.run_id}")
        with open(runs_dir / f"{run.run_id}.a{attempt}.log", "w") as out:
            out.write(" ".join(str(a) for a in argv) + "\n")
            out.flush()
            # New session: JMH and its forked benchmark JVM form one process group,
            # killed together on a timeout or abort (killing only the host would orphan the fork).
            proc = subprocess.Popen([str(a) for a in argv], env=self.env, stdout=out, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                code = proc.wait(timeout=RUN_TIMEOUT_S)
                status = "ok" if code == 0 and valid_result(out_json, self.energy) else "failed"
            except subprocess.TimeoutExpired:
                kill_group(proc)
                code, status = -1, "timeout"
            except BaseException:
                kill_group(proc)
                raise
        if staging is not None:
            profile_dir.mkdir(parents=True, exist_ok=True)
            for f in staging.rglob("*.jfr"):
                shutil.move(f, profile_dir / f"{run.run_id}.jfr")
            shutil.rmtree(staging, ignore_errors=True)
            if status == "ok" and not (profile_dir / f"{run.run_id}.jfr").exists():
                status = "failed"  # no recording: the profiling run is worthless
        append_progress(self.dir / "progress.csv", dict(
            run_id=run.run_id, attempt=attempt, status=status, batch=batch_exec,
            start_utc=start, end_utc=utc_now(), exit_code=code))
        if status != "ok":
            log(f"  {status} (exit {code}); see runs/{run.run_id}.a{attempt}.log")
        self.cooldown(bdir)
        return status

    # ---- one batch execution
    def run_batch(self, batch, runs, attempts):
        k = 1
        while (self.dir / "batches" / (batch if k == 1 else f"{batch}-{k}")).exists():
            k += 1
        batch_exec = batch if k == 1 else f"{batch}-{k}"
        bdir = self.dir / "batches" / batch_exec
        bdir.mkdir(parents=True)
        log(f"batch {batch_exec}: {len(runs)} runs")
        idle_start = idle_end = None
        try:
            self.start_refresher(bdir)
            self.start_server(bdir / "server.json")
            self.manifest(bdir / "env-start.txt")
            idle_start = self.idle_baseline(bdir / "idle-start.json")
            for run in runs:
                if self.stop:
                    break
                self.quiet_gate()
                if self.stop:
                    break
                attempt = attempts.get(run.run_id, 0) + 1
                attempts[run.run_id] = attempt
                self.execute(run, batch_exec, attempt, bdir)
            idle_end = self.idle_baseline(bdir / "idle-end.json")
            self.manifest(bdir / "env-end.txt")
        finally:
            self.stop_server()
            self.stop_refresher(bdir)
            agree = ""
            if idle_start is not None and idle_end is not None:
                agree = idle_agrees(idle_start, idle_end, *IDLE_TOLERANCE[self.platform])
            _append_csv(self.dir / "batches.csv", BATCH_FIELDS, dict(
                batch=batch_exec, attempt=k, primary_domain=PRIMARY_DOMAIN[self.platform],
                idle_start_W=idle_start, idle_end_W=idle_end, agree=agree))
        if agree is False:
            log(f"batch {batch_exec}: idle baselines disagree ({idle_start:.4f} vs {idle_end:.4f} W)")
        return agree

    def guarded_batch(self, batch, runs, attempts):
        """run_batch, but an unexpected error ends only this batch (its runs stay pending or unverified,
        and the re-queue pass picks them up); two errors in a row stop the campaign."""
        try:
            self.run_batch(batch, runs, attempts)
            self.errors = 0
        except (CampaignStopped, KeyboardInterrupt):
            raise
        except Exception:
            self.errors = getattr(self, "errors", 0) + 1
            log(f"batch {batch} failed:\n{traceback.format_exc()}")
            if self.errors >= 2:
                raise CampaignStopped("two batches in a row failed; see the log above")

    # ---- the campaign
    def plan(self):
        if self.args.cells_file:
            cell_list = cells_from_file(self.args.cells_file)
        else:
            cell_list = cells(self.platform, self.args.subset)
        return schedule(cell_list, self.args.forks, self.args.seed)

    def run(self):
        runs = self.plan()
        sched = self.dir / "schedule.csv"
        if sched.exists():
            if read_schedule(sched) != runs:
                sys.exit(f"{sched} differs from this invocation (seed, forks, subset?); use another --campaign")
        if self.args.dry_run:
            self.print_plan(runs)
            return
        self.preflight()
        (self.dir / "runs").mkdir(parents=True, exist_ok=True)
        if not sched.exists():
            write_schedule(sched, runs, self.args.seed)
        progress = self.dir / "progress.csv"
        by_id = {r.run_id: r for r in runs}
        status = latest_status(progress)
        attempts = {rid: a for rid, (_, a) in status.items()}
        pending = [r for r in runs if status.get(r.run_id, ("", 0))[0] != "ok"]
        if self.args.max_runs:
            pending = pending[:self.args.max_runs]
        log(f"{len(pending)} of {len(runs)} runs pending in {self.dir}")
        self.manifest(self.dir / f"env-campaign-{utc_now().replace(':', '')}.txt")

        # 1. The schedule, batch by batch.
        for batch in sorted({r.batch for r in pending}):
            if self.stop:
                break
            self.guarded_batch(batch, [r for r in pending if r.batch == batch], attempts)

        # 2. One re-run of the runs of every unverified batch execution (idle baselines that
        #    disagree or are missing), derived from the files so that it survives any stop.
        if self.energy and not self.args.max_runs:
            batch_rows = read_csv_rows(self.dir / "batches.csv")
            for execution, run_ids in requeue_candidates(batch_rows, progress_history(progress)).items():
                if self.stop:
                    break
                log(f"re-queueing {len(run_ids)} runs of unverified batch {execution}")
                for rid in run_ids:
                    append_progress(progress, dict(run_id=rid, attempt=attempts[rid], status="discarded",
                                                   batch=execution, start_utc=utc_now(), end_utc=utc_now()))
                for i, part in enumerate(chunks([by_id[rid] for rid in run_ids])):
                    if self.stop:
                        break
                    self.guarded_batch(f"{execution}-r{i + 1}", part, attempts)

        # 3. One retry of every run that failed or timed out.
        retry = [by_id[rid] for rid in failed_once(progress_history(progress)) if rid in by_id]
        if retry and not self.stop and not self.args.max_runs:
            log(f"retrying {len(retry)} failed runs once")
            for i, part in enumerate(chunks(retry)):
                if self.stop:
                    break
                self.guarded_batch(f"retry{i + 1:02d}", part, attempts)

        status = latest_status(progress)
        left = sum(1 for r in runs if status.get(r.run_id, ("", 0))[0] != "ok")
        log(f"done: {len(runs) - left} of {len(runs)} runs ok" + (f", {left} not ok" if left else ""))

    def print_plan(self, runs):
        hours = estimate_seconds(runs, self.platform, self.args.idle_seconds) / 3600
        n_cells = len({r.cell for r in runs})
        print(f"{self.platform}/{self.args.campaign}: {n_cells} cells x {self.args.forks} forks = {len(runs)} runs, "
              f"{len({r.batch for r in runs})} batches, est. {hours:.1f} h")
        for r in runs[:3]:
            argv = jmh_command(r.cell, self.platform, java=self.java, jar=JAR, out_json=f"runs/{r.run_id}.json",
                               socket_port=self.args.socket_port, arms=self.arms, mode=self.args.mode,
                               profile_dir="profile/", perf=self.args.perf)
            print("  " + " ".join(f"'{a}'" if " " in str(a) else str(a) for a in argv))


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def read_csv_rows(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def valid_result(path, energy):
    try:
        rows = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return False
    if len(rows) != 1:
        return False
    return not energy or any(k.endswith(".J_per_op") for k in rows[0].get("secondaryMetrics", {}))


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=["intel", "mac"], required=True)
    ap.add_argument("--campaign", required=True, help="results/<platform>/<campaign>/")
    ap.add_argument("--mode", choices=["energy", "profile"], default="energy")
    ap.add_argument("--subset", choices=["full", "pilot", "profile", "smoke"], default="full")
    ap.add_argument("--cells-file", help="CSV construct,p,workload,restriction (overrides --subset)")
    ap.add_argument("--forks", type=int, default=None, help="default: 5 (intel), 10 (mac), 2 (profile)")
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--max-runs", type=int, default=0, help="run at most N pending runs, no re-queue (testing)")
    ap.add_argument("--idle-seconds", type=int, default=60)
    ap.add_argument("--min-idle", type=int, default=95, help="quiet gate: minimum CPU idle percent")
    ap.add_argument("--idle-ceiling", type=float, default=None,
                    help="maximum quiet idle power in W, primary domain (default: 6.0 intel, 0.08 mac)")
    ap.add_argument("--epp", default="balance_performance",
                    help="required energy_performance_preference on every CPU (intel)")
    ap.add_argument("--socket-port", type=int, default=SOCKET_PORT)
    ap.add_argument("--perf", action="store_true", help="profile mode: add perf stat (Linux)")
    ap.add_argument("--no-gate", action="store_true", help="skip the quiet gate (testing only)")
    ap.add_argument("--no-energy", action="store_true", help="no energy profiler or idle baselines (testing only)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.forks is None:
        args.forks = 2 if args.mode == "profile" else {"intel": 5, "mac": 10}[args.platform]
    if args.mode == "profile":
        args.no_energy = True
    if args.idle_ceiling is None:
        args.idle_ceiling = IDLE_CEILING[args.platform]
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    campaign = Campaign(args)

    def on_sigint(signum, frame):
        if campaign.stop:
            raise KeyboardInterrupt
        campaign.stop = True
        log("stopping after the current run (Ctrl-C again to abort now)")

    def on_terminate(signum, frame):
        raise KeyboardInterrupt  # closing the terminal or kill: unwind, closing the batch in finally

    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_terminate)
    signal.signal(signal.SIGHUP, on_terminate)
    try:
        campaign.run()
    except CampaignStopped as e:
        log(f"campaign stopped{': ' + str(e) if str(e) else ''}; rerun the same command to resume")
        sys.exit(1)
    except KeyboardInterrupt:
        log("campaign aborted; rerun the same command to resume")
        sys.exit(130)


if __name__ == "__main__":
    main()
