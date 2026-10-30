"""Per-cell summary of any campaign directory (main, control, Intel reduced, ...).

Usage: python analysis/cell_summary.py results/<platform>/<campaign> [--out cells.csv]

One row per cell (restriction, workload, construct, p) with the number of ok runs and the
median, IQR, and CV of raw energy/op, idle-subtracted energy/op, time/op, and power, plus the
median per-class core frequency (Intel) and E-cluster share (Mac) where the campaign has them.
analyse.py runs the hypothesis tests of the full design; this script covers the campaigns
outside that design (the reused-pool control and the reduced Intel campaign).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vtenergy.load import load_campaign  # noqa: E402

KEYS = ["restriction", "workload", "construct", "p"]
MEASURES = ["primary_J_op", "primary_J_op_active", "ms_op", "primary_W"]


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    extra = [c for c in df.columns if c.startswith("freq_") or c == "ecpu_share"]
    g = df.groupby(KEYS, dropna=False)
    out = g.size().rename("n").to_frame()
    for m in MEASURES:
        col = g[m]
        out[f"{m}_median"] = col.median()
        out[f"{m}_iqr"] = col.quantile(0.75) - col.quantile(0.25)
        out[f"{m}_cv"] = col.std() / col.mean()
    for m in extra:
        out[f"{m}_median"] = g[m].median()
    return out.reset_index()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("campaign", help="results/<platform>/<campaign>")
    ap.add_argument("--out", help="CSV path (default: <campaign>/cells.csv)")
    args = ap.parse_args(argv)
    loaded = load_campaign(args.campaign)
    df = loaded[0] if isinstance(loaded, tuple) else loaded
    cells = summarise(df)
    out = Path(args.out) if args.out else Path(args.campaign) / "cells.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out, index=False)
    print(f"{args.campaign}: {len(df)} runs, {len(cells)} cells -> {out}")


if __name__ == "__main__":
    main()
