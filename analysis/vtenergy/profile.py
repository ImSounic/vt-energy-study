"""Event counts of a profiling campaign's JFR recordings (report Section 5.4).

  python analysis/vtenergy/profile.py results/intel/profile [--jfr $JAVA_HOME/bin/jfr]

Writes <campaign>/profile/profile.csv: one row per recording with its cell and
the counts of the events that attribute Java-level causes (thread starts, park
and sleep, socket I/O, GC, allocation samples, CPU samples).
"""
import argparse
import csv
import os
import re
import subprocess
from pathlib import Path

EVENTS = ["jdk.ThreadStart", "jdk.VirtualThreadStart", "jdk.ThreadPark", "jdk.ThreadSleep",
          "jdk.SocketRead", "jdk.SocketWrite", "jdk.GarbageCollection", "jdk.ObjectAllocationSample",
          "jdk.ExecutionSample", "jdk.JavaMonitorWait", "jdk.VirtualThreadPinned"]
_ROW = re.compile(r"^\s*(jdk\.\w+)\s+(\d+)\s+\d+\s*$")


def counts(summary_text):
    """Event name -> count from `jfr summary` output."""
    out = {}
    for line in summary_text.splitlines():
        m = _ROW.match(line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign")
    ap.add_argument("--jfr", default=str(Path(os.environ.get("JAVA_HOME", Path.home() / ".local/opt/jdk-25")) / "bin" / "jfr"))
    args = ap.parse_args()
    campaign = Path(args.campaign)
    with open(campaign / "schedule.csv", newline="") as f:
        cells = {r["run_id"]: r for r in csv.DictReader(f)}
    rows = []
    for rec in sorted((campaign / "profile").rglob("*.jfr")):
        run_id = rec.stem
        text = subprocess.run([args.jfr, "summary", str(rec)], capture_output=True, text=True, check=True).stdout
        c = counts(text)
        cell = cells.get(run_id, {})
        rows.append({"run_id": run_id, **{k: cell.get(k, "") for k in
                                          ("construct", "p", "workload", "restriction", "fork_index")},
                     **{e: c.get(e, 0) for e in EVENTS}})
    out = campaign / "profile" / "profile.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["run_id"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} recordings)")


if __name__ == "__main__":
    main()
