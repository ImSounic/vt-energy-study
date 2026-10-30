"""Figures of the A3 report that analyse.py does not produce.

Usage: python analysis/report_figures.py [--out paper/figures]

- cpu-energy-vs-time.pdf (Figure 2): CPU-bound cell medians, energy/op against time/op,
  Mac main campaign (DEFAULT QoS) next to the Intel reduced campaign (unpinned).
- mac-lambda.pdf (Figure 1) is analyse.py's results/mac/analysis/figures/lambda.pdf, copied.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as tk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
from vtenergy.load import load_campaign  # noqa: E402

MARKERS = {
    "SEQUENTIAL": ("s", "k", "SEQ"),
    "PLATFORM_THREADS": ("D", "#E69F00", "PT"),
    "FIXED_POOL": ("o", "#56B4E9", "FP"),
    "FORK_JOIN": ("^", "#009E73", "FJ"),
    "VIRTUAL_THREADS": ("v", "#D55E00", "VT"),
    "FIXED_POOL_PERSISTENT": ("o", "#0072B2", "FP reused"),
    "FORK_JOIN_PERSISTENT": ("^", "#004D40", "FJ reused"),
}
PANELS = [
    (ROOT / "results/mac/main", "DEFAULT", "Mac M4 (CPU clusters)"),
    (ROOT / "results/intel/reduced", "unpinned", "Intel 255H (package)"),
]


def cpu_cells(path, restriction):
    loaded = load_campaign(path)
    df = loaded[0] if isinstance(loaded, tuple) else loaded
    df = df[(df.workload == "CPU") & (df.restriction == restriction)]
    return (df.groupby(["construct", "p"], dropna=False)
              .agg(J=("primary_J_op", "median"), ms=("ms_op", "median")).reset_index())


def energy_vs_time(out: Path):
    fig, axes = plt.subplots(1, 2, figsize=(3.4, 1.75))
    for ax, (path, restriction, title) in zip(axes, PANELS):
        seen = set()
        for _, r in cpu_cells(path, restriction).iterrows():
            marker, colour, label = MARKERS[r.construct]
            ax.scatter(r.ms, r.J, marker=marker, c=colour, s=9, edgecolors="none",
                       label=None if label in seen else label)
            seen.add(label)
        ax.set_xscale("log")
        ax.set_title(title, fontsize=6.5)
        ax.xaxis.set_major_locator(tk.LogLocator(base=10, subs=(1.0,)))
        ax.xaxis.set_minor_formatter(tk.NullFormatter())
        ax.tick_params(which="both", labelsize=5.5)
        ax.set_xlabel("time/op (ms, log)", fontsize=6)
        ax.grid(alpha=.3, lw=.4)
    axes[0].set_ylabel("energy/op (J)", fontsize=6)
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=5, ncol=7, loc="upper center", bbox_to_anchor=(0.5, 1.06),
               frameon=False, handletextpad=0.1, columnspacing=0.5)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out / "cpu-energy-vs-time.pdf", bbox_inches="tight")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "paper/figures"))
    ap.add_argument("--mac-analysis", default=str(ROOT / "results/mac/analysis"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    energy_vs_time(out)
    shutil.copy(Path(args.mac_analysis) / "figures/lambda.pdf", out / "mac-lambda.pdf")
    print(f"figures -> {out}")


if __name__ == "__main__":
    main()
