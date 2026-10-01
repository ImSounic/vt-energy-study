#!/usr/bin/env python3
"""Summarise a JMH JSON file produced with an energy profiler.

Usage: analysis/summarize_pilot.py <pilot.json> [idle.json]

One Markdown row per (strategy, workload): median ms/op and J/op for the
primary energy domain (medians of per-fork medians), mean power, coefficient
of variation of per-fork J/op, and idle-subtracted J/op when idle.json is given.
"""
import json
import statistics
import sys

PRIMARY = {"ioreport": "CPU_Energy", "rapl": "intel-rapl:0:package-0"}


def primary_domain(secondary):
    for prefix, domain in PRIMARY.items():
        if f"{prefix}.{domain}.J_per_op" in secondary:
            return prefix, domain
    raise KeyError("no known energy domain in secondaryMetrics")


def fork_medians(raw):
    return [statistics.median(fork) for fork in raw]


def summarise(rows, idle_watts=None):
    out = []
    for r in rows:
        sec = r["secondaryMetrics"]
        prefix, domain = primary_domain(sec)
        ms = fork_medians(r["primaryMetric"]["rawData"])
        jop = fork_medians(sec[f"{prefix}.{domain}.J_per_op"]["rawData"])
        joules = fork_medians(sec[f"{prefix}.{domain}.J"]["rawData"])
        window = fork_medians(sec[f"{prefix}.window_s"]["rawData"])
        ms_med = statistics.median(ms)
        jop_med = statistics.median(jop)
        row = {
            "strategy": r["params"]["strategy"],
            "workload": r["params"]["workloadType"],
            "ms_per_op": ms_med,
            "J_per_op": jop_med,
            "W": statistics.mean(j / w for j, w in zip(joules, window)),
            "cv_J_per_op": (statistics.stdev(jop) / statistics.mean(jop)) if len(jop) > 1 else float("nan"),
        }
        if idle_watts is not None:
            row["J_per_op_active"] = jop_med - idle_watts * ms_med / 1000.0
        out.append(row)
    return out


def main(argv):
    with open(argv[1]) as f:
        rows = json.load(f)
    idle = None
    if len(argv) > 2:
        with open(argv[2]) as f:
            idle = json.load(f)["watts"][primary_domain(rows[0]["secondaryMetrics"])[1]]
    cols = ["strategy", "workload", "ms_per_op", "J_per_op", "W", "cv_J_per_op"]
    if idle is not None:
        cols.append("J_per_op_active")
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for row in summarise(rows, idle):
        cells = [f"{row[c]:.4g}" if isinstance(row[c], float) else str(row[c]) for c in cols]
        print("| " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main(sys.argv)
