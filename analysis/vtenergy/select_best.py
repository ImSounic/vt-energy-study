#!/usr/bin/env python3
"""Pick the Intel H0-1.2 confirmation cells (A3-D6).

Usage: select_best.py CAMPAIGN_DIR [--platform intel] [--out FILE]
       python -m vtenergy.select_best results/intel/main > results/intel/confirm-cells.csv

Prints a cells CSV (construct,p,workload,restriction): per workload SEQ plus the lowest-median
concurrent configuration from all forks of the main campaign, restriction unpinned. The tested
measure decides (package J/op on CPU, idle-subtracted package J/op on SLEEP/SOCKET).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from vtenergy.hypotheses import select_best_configs  # type: ignore
    from vtenergy.load import load_campaign  # type: ignore
else:
    from .hypotheses import select_best_configs
    from .load import load_campaign


def cells_csv(df, platform="intel") -> str:
    sel = select_best_configs(df, platform)
    lines = ["construct,p,workload,restriction"]
    for _, r in sel.iterrows():
        p = "" if pd.isna(r["p"]) else str(int(r["p"]))
        lines.append(f"{r['construct']},{p},{r['workload']},{r['restriction']}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("campaign")
    ap.add_argument("--platform", default="intel")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    df = load_campaign(a.campaign)
    if df.empty:
        print(f"no ok runs in {a.campaign}", file=sys.stderr)
        return 1
    text = cells_csv(df, a.platform)
    if a.out:
        Path(a.out).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
