"""Summaries of the ancillary experiments (scripts/ancillary/*.sh).

  python analysis/vtenergy/ancillary.py ax4 results/ancillary/intel/ax4
  python analysis/vtenergy/ancillary.py ax3 results/ancillary/mac/ax3
  python analysis/vtenergy/ancillary.py ax6 results/ancillary/mac/ax6
  python analysis/vtenergy/ancillary.py ax5 results/ancillary/intel
  python analysis/vtenergy/ancillary.py srv results/ancillary/intel

Each prints a small CSV table on stdout and writes it next to the inputs.
"""
import csv
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

import numpy as np

PRIMARY = ["intel-rapl:0:package-0", "CPU_Energy"]

_HEADER = re.compile(r"\*\*\* Sampled system activity \((.+?)\) \(([\d.]+)ms elapsed\) \*\*\*")
_FIELDS = {
    "cpu_mW": re.compile(r"^CPU Power: (\d+) mW"),
    "e_residency": re.compile(r"^E-Cluster HW active residency:\s+([\d.]+)%"),
    "p_residency": re.compile(r"^P-Cluster HW active residency:\s+([\d.]+)%"),
    "e_MHz": re.compile(r"^E-Cluster HW active frequency: (\d+) MHz"),
    "p_MHz": re.compile(r"^P-Cluster HW active frequency: (\d+) MHz"),
}


def parse_powermetrics(text):
    """One dict per sample: end time (epoch s), elapsed s, and the fields above."""
    samples, cur = [], None
    for line in text.splitlines():
        m = _HEADER.search(line)
        if m:
            when = dt.datetime.strptime(" ".join(m.group(1).split()), "%a %b %d %H:%M:%S %Y %z")
            cur = {"end": when.timestamp(), "elapsed": float(m.group(2)) / 1000}
            samples.append(cur)
            continue
        if cur is None:
            continue
        for key, rx in _FIELDS.items():
            m = rx.match(line.strip())
            if m:
                cur[key] = float(m.group(1))
    return samples


def window(samples, start, seconds):
    """Samples that end inside [start, start + seconds] (1 s header resolution)."""
    return [s for s in samples if start <= s["end"] <= start + seconds + 1]


def primary_watts(probe):
    for d in PRIMARY:
        if d in probe["watts"]:
            return probe["watts"][d]
    raise KeyError("no primary domain")


def linear_fit(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    r2 = 1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return slope, intercept, r2


def _probes(d, pattern):
    return {p.stem: json.loads(p.read_text()) for p in sorted(Path(d).glob(pattern))}


def ax4(d):
    probes = sorted(_probes(d, "k*.json").values(), key=lambda p: p["threads"])
    rows = [{"threads": p["threads"], "W": primary_watts(p), "ops_per_s": p["ops"] / p["seconds"]} for p in probes]
    slope, intercept, r2 = linear_fit([r["threads"] for r in rows], [r["W"] for r in rows])
    for r in rows:
        r["fit_W"] = slope * r["threads"] + intercept
    rows.append({"threads": "fit", "W": f"slope={slope:.4f} W/thread", "ops_per_s": f"intercept={intercept:.4f} W",
                 "fit_W": f"R2={r2:.4f}"})
    return rows


def ax3(d):
    samples = parse_powermetrics((Path(d) / "powermetrics.txt").read_text(errors="replace"))
    rows = []
    for name, p in _probes(d, "k*.json").items():
        start = p["start_epoch_ms"] / 1000
        win = [s for s in window(samples, start, p["seconds"]) if "cpu_mW" in s]
        pm_w = sum(s["cpu_mW"] * s["elapsed"] for s in win) / 1000 / sum(s["elapsed"] for s in win) if win else float("nan")
        io_w = p["watts"]["CPU_Energy"]
        rows.append({"threads": p["threads"], "ioreport_W": io_w, "powermetrics_W": pm_w,
                     "ratio": io_w / pm_w if pm_w else float("nan"), "samples": len(win)})
    return sorted(rows, key=lambda r: r["threads"])


def ax6(d):
    samples = parse_powermetrics((Path(d) / "powermetrics.txt").read_text(errors="replace"))
    rows = []
    for name, p in _probes(d, "*.json").items():
        if "threads" not in p:
            continue
        win = window(samples, p["start_epoch_ms"] / 1000, p["seconds"])
        mean = lambda k: float(np.mean([s[k] for s in win if k in s])) if win else float("nan")
        rows.append({"qos": name, "W": p["watts"].get("CPU_Energy"), "ecpu_W": p["watts"].get("ECPU"),
                     "pcpu_W": p["watts"].get("PCPU"), "ops_per_s": p["ops"] / p["seconds"],
                     "e_residency_pct": mean("e_residency"), "p_residency_pct": mean("p_residency"),
                     "e_MHz": mean("e_MHz"), "p_MHz": mean("p_MHz"), "samples": len(win)})
    return rows


def ax5(d):
    rows = []
    for name, data in _probes(d, "ax5-*.json").items():
        if name == "ax5-server":
            continue
        for kind, s in data.items():
            rows.append({"qos": name.removeprefix("ax5-"), "kind": kind, **s})
    return rows


def srv(d):
    rows = []
    for name, data in _probes(d, "srv-with*.json").items():
        rows.append({"run": name, **{k: v for k, v in data["watts"].items() if k in PRIMARY or k in
                                     ("intel-rapl:1:psys", "ECPU", "PCPU", "DRAM", "AMCC")}})
    return rows


def to_csv(rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main(argv):
    if len(argv) != 3 or argv[1] not in ("ax3", "ax4", "ax5", "ax6", "srv"):
        sys.exit(__doc__)
    rows = globals()[argv[1]](argv[2])
    text = to_csv(rows)
    (Path(argv[2]) / f"{argv[1]}-summary.csv").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main(sys.argv)
