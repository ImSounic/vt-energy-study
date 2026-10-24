#!/usr/bin/env python3
"""Run the full Section 4.6 analysis on one campaign (or the A2 pilot layout).

Usage:
    analyse.py --campaign results/intel/main [--confirm results/intel/confirm] [--out DIR]
    analyse.py --pilot results/pilot-intel/pilot.json --idle results/pilot-intel/idle-start.json \
               --platform intel --out DIR

Writes to --out (default: <campaign>/analysis):
    runs.csv    one row per ok run (fork), with floor_ratio on SLEEP/SOCKET
    cells.csv   per cell: median, q1, q3, IQR, CV, n of every reported measure, plus the
                detection-limit flag of the idle-subtracted measures
    tests.csv   every hypothesis-family row (vtenergy.hypotheses.ROW_COLS)
    power.csv   simulated Mann-Whitney power at n = 10 and n = 5 for a 10% difference
    figures/*.pdf
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from vtenergy import BLOCKING, CELL_KEYS, DEFAULT_RESTRICTION, WORKLOADS  # noqa: E402
from vtenergy import figures, hypotheses as H, stats as S  # noqa: E402
from vtenergy.load import load_campaign, load_pilot  # noqa: E402

CELL_MEASURES = ["ms_op", "primary_J_op", "primary_J_op_active", "primary_W", "mem_J_op",
                 "mem_J_op_active", "ecpu_share", "floor_ratio"]


def cells_table(df: pd.DataFrame, n_boot: int, seed: int) -> pd.DataFrame:
    keys = [k for k in CELL_KEYS if k in df.columns]
    base = None
    for m in CELL_MEASURES:
        if m not in df.columns or df[m].isna().all():
            continue
        s = S.cell_summary(df, m, by=keys).rename(columns={c: f"{m}_{c}" for c in
                                                         ["median", "q1", "q3", "iqr", "mean", "cv", "n"]})
        base = s if base is None else base.merge(s, on=keys, how="outer")
    if base is None:
        base = df[keys].drop_duplicates().reset_index(drop=True)
    flags = df.groupby(keys, dropna=False).agg(n=("run_id", "count"), n_regime_flag=("regime_flag", "sum"),
                                              n_idle_mismatch=("idle_mismatch", "sum"),
                                              n_idle_unverified=("idle_unverified", "sum")).reset_index()
    base = base.merge(flags, on=keys, how="left")
    for m in ("primary_J_op_active", "mem_J_op_active"):
        if m not in df.columns or df[m].isna().all():
            continue
        rows = []
        for key, g in df.groupby(keys, dropna=False):
            key = key if isinstance(key, tuple) else (key,)
            r = dict(zip(keys, key))
            x = g[m].dropna()
            r[f"{m}_below_detection_limit"] = bool(r["workload"] in BLOCKING and len(x)
                                                   and S.below_detection_limit(x, n_boot=n_boot, seed=seed))
            rows.append(r)
        flag = pd.DataFrame(rows)
        flag["p"] = flag["p"].astype("Int64")
        base = base.merge(flag, on=keys, how="left")
    base["p"] = base["p"].astype("Int64")
    return base.sort_values(keys).reset_index(drop=True)


def _cv(df, workload, label, measure):
    d = H._exp1(df, H._platform(df, None))
    x = H._vals(d, workload, label, measure)
    return S.describe(x)["cv"], len(x)


def _pick_vt(df, workload, prefer):
    d = H._exp1(df, H._platform(df, None))
    ps = sorted(int(p) for p in d[(d["construct"] == "VIRTUAL_THREADS") & (d["workload"] == workload)]["p"].dropna().unique())
    if not ps:
        return None
    return prefer if prefer in ps else min(ps, key=lambda p: abs(np.log2(p) - np.log2(prefer)))


def power_table(df: pd.DataFrame, platform: str, sims: int, seed: int) -> pd.DataFrame:
    """Power check (Section 4.6): VT vs PT per workload; SEQ vs best concurrent on CPU;
    VT vs PT on the memory measure (Mac). CV used = the larger of the two cells' fork CVs."""
    rows = []
    k = H.MAIN_K.get(platform, 8)

    def add(comparison, workload, measure, la, lb, note=""):
        cva, na = _cv(df, workload, la, measure)
        cvb, nb = _cv(df, workload, lb, measure)
        cvs = [c for c in (cva, cvb) if np.isfinite(c)]
        cv = max(abs(c) for c in cvs) if cvs else np.nan
        if not na or not nb:
            note = "; ".join(x for x in [note, f"no data for {la if not na else lb}: CV of the other cell only"] if x)
        for n in (10, 5):
            pw = S.mw_power(cv, n, ratio=1.10, alpha=0.05, sims=sims, seed=seed)
            rows.append({"comparison": comparison, "workload": workload, "measure": measure,
                         "cell_a": la, "cell_b": lb, "n_a_pilot": na, "n_b_pilot": nb, "cv_a": cva,
                         "cv_b": cvb, "cv_used": cv, "n": n, "ratio": 1.10, "power": pw,
                         "below_0_8": bool(np.isfinite(pw) and pw < 0.8), "note": note})

    for w in WORKLOADS:
        prefer = k if w == "CPU" else 256
        p = _pick_vt(df, w, prefer)
        if p is None:
            continue
        note = "" if p == prefer else f"VT_{prefer} absent; used VT_{p}"
        measures = [H.measure_for(w)] + (["primary_J_op"] if w in BLOCKING else [])
        for m in measures:
            add("VT vs PT", w, m, f"VT_{p}", "PT", note)
    sel = H.select_best_configs(df, platform)
    best = sel[(sel["workload"] == "CPU") & (sel["construct"] != "SEQUENTIAL")]
    if len(best):
        add("SEQ vs best concurrent", "CPU", "primary_J_op", "SEQ",
            H.lab(best.iloc[0]["construct"], best.iloc[0]["p"]))
    if platform == "mac":
        for w in BLOCKING:
            p = _pick_vt(df, w, 256)
            if p is None:
                continue
            for m in ("mem_J_op_active", "mem_J_op"):
                if m in df.columns:
                    add("VT vs PT (memory)", w, m, f"VT_{p}", "PT", "" if p == 256 else f"used VT_{p}")
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="vt-energy analysis (report Section 4.6)")
    ap.add_argument("--campaign", help="results/<platform>/<campaign> directory")
    ap.add_argument("--confirm", help="Intel H0-1.2 confirmation campaign directory (A3-D6)")
    ap.add_argument("--pilot", help="A2 pilot JMH JSON (several forks per entry)")
    ap.add_argument("--idle", help="idle baseline JSON for --pilot")
    ap.add_argument("--platform", choices=["intel", "mac"], help="platform for --pilot")
    ap.add_argument("--out", help="output directory")
    ap.add_argument("--sleep-d-ms", type=float, default=10.0, help="per-task wait d for SLEEP floor ratios (AX5)")
    ap.add_argument("--socket-d-ms", type=float, default=None, help="d for SOCKET (default: --sleep-d-ms)")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--power-sims", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    if bool(a.campaign) == bool(a.pilot):
        ap.error("give exactly one of --campaign or --pilot")
    if a.pilot:
        df = load_pilot(a.pilot, a.idle, a.platform)
        out = Path(a.out or Path(a.pilot).with_suffix("").as_posix() + "-analysis")
    else:
        df = load_campaign(a.campaign)
        out = Path(a.out or Path(a.campaign) / "analysis")
    if df.empty:
        print("no ok runs loaded", file=sys.stderr)
        return 1
    platform = a.platform or H._platform(df, None)
    confirm = load_campaign(a.confirm) if a.confirm else None

    opts = H.Opts(n_boot=a.n_boot, seed=a.seed,
                  d_ms={"SLEEP": a.sleep_d_ms, "SOCKET": a.socket_d_ms if a.socket_d_ms is not None else a.sleep_d_ms})
    df = df.assign(floor_ratio=H.floor_ratio(df, opts.d_ms))
    out.mkdir(parents=True, exist_ok=True)

    df.to_csv(out / "runs.csv", index=False)
    if confirm is not None and not confirm.empty:
        confirm.to_csv(out / "runs_confirm.csv", index=False)
    cells = cells_table(df, a.n_boot, a.seed)
    cells.to_csv(out / "cells.csv", index=False)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        tests = H.run_all(df, platform, confirm, opts)
    tests.to_csv(out / "tests.csv", index=False)

    power = power_table(df, platform, a.power_sims, a.seed)
    power.to_csv(out / "power.csv", index=False)

    figs = figures.all_figures(df, platform, out / "figures")

    counts = tests["decision"].value_counts().to_dict()
    print(f"{platform}: {len(df)} runs, {len(cells)} cells, {len(tests)} test rows {counts}")
    print(f"default restriction = {DEFAULT_RESTRICTION.get(platform)}; figures: {[f.name for f in figs]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
