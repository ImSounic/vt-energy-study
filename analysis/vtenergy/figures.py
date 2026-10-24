"""Figures (PDF): Lambda curves, energy-vs-time scatter, Mac cluster-split bars, Intel placement bars.

Okabe-Ito colorblind-safe palette; every axis labeled with units. Each function returns the
written path, or None when the data needed for the figure are absent.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import BLOCKING, DEFAULT_RESTRICTION, NO_P, P_LEVELS, SHORT, WORKLOADS  # noqa: E402

COLORS = {  # Okabe-Ito
    "SEQUENTIAL": "#000000",
    "PLATFORM_THREADS": "#E69F00",
    "FIXED_POOL": "#56B4E9",
    "FORK_JOIN": "#009E73",
    "VIRTUAL_THREADS": "#D55E00",
}
MARKERS = {"SEQUENTIAL": "s", "PLATFORM_THREADS": "D", "FIXED_POOL": "o", "FORK_JOIN": "^",
           "VIRTUAL_THREADS": "v"}
RESTRICTION_COLORS = {"unpinned": "#999999", "2P": "#0072B2", "2E": "#009E73", "2LPE": "#CC79A7",
                      "DEFAULT": "#0072B2", "BACKGROUND": "#009E73"}
PRIMARY_NAME = {"intel": "package", "mac": "CPU clusters"}


def _measure(workload: str) -> str:
    return "primary_J_op" if workload == "CPU" else "primary_J_op_active"


def _ylabel(platform: str, workload: str) -> str:
    name = PRIMARY_NAME.get(platform, "primary")
    if workload == "CPU":
        return f"{name} energy/op (J)"
    return f"idle-subtracted {name} energy/op (J)"


def _q(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if not len(x):
        return np.nan, np.nan, np.nan
    q1, m, q3 = np.quantile(x, [0.25, 0.5, 0.75])
    return m, q1, q3


def _default(df, platform):
    return df[df["restriction"] == DEFAULT_RESTRICTION.get(platform, "DEFAULT")]


def _save(fig, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def lambda_curves(df: pd.DataFrame, platform: str, out, measure_fn=_measure, tag="") -> Path | None:
    """Energy/op against p (log2 axis), one panel per workload, one line per pooled construct
    (median with IQR bars); SEQ and PT as horizontal reference lines (median, IQR band)."""
    d = _default(df, platform)
    wls = [w for w in WORKLOADS if (d["workload"] == w).any()]
    if not wls:
        return None
    fig, axes = plt.subplots(1, len(wls), figsize=(4.8 * len(wls), 3.4), squeeze=False)
    fig.subplots_adjust(wspace=0.38)
    for ax, w in zip(axes[0], wls):
        m = measure_fn(w)
        sub = d[d["workload"] == w]
        if m not in sub.columns:
            continue
        for c in ["FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"]:
            pts = []
            for p in P_LEVELS:
                med, q1, q3 = _q(sub[(sub["construct"] == c) & (sub["p"] == p)][m])
                if np.isfinite(med):
                    pts.append((p, med, q1, q3))
            if not pts:
                continue
            ps, med, q1, q3 = map(np.array, zip(*pts))
            ax.errorbar(ps, med, yerr=[med - q1, q3 - med], color=COLORS[c], marker=MARKERS[c],
                        capsize=3, label=SHORT[c], lw=1.4, ms=5)
        for c in NO_P:
            med, q1, q3 = _q(sub[sub["construct"] == c][m])
            if np.isfinite(med):
                ax.axhline(med, color=COLORS[c], ls="--" if c == "SEQUENTIAL" else ":", lw=1.2,
                           label=SHORT[c])
                ax.axhspan(q1, q3, color=COLORS[c], alpha=0.12, lw=0)
        ax.set_xscale("log", base=2)
        ax.set_xlim(0.75, 340)
        ax.set_xticks(P_LEVELS)
        ax.set_xticklabels([str(p) for p in P_LEVELS])
        ax.set_xlabel("concurrency level p (workers / carriers)")
        ax.set_ylabel(_ylabel(platform, w) if m.startswith("primary") else f"{m} (J)")
        if w in BLOCKING:
            ax.axhline(0, color="#555555", lw=0.6)
        ax.set_title(w)
        ax.grid(alpha=0.3)
    handles, labels = axes[0][0].get_legend_handles_labels()
    for ax in axes[0][1:]:
        h, l = ax.get_legend_handles_labels()
        for hh, ll in zip(h, l):
            if ll not in labels:
                handles.append(hh)
                labels.append(ll)
    fig.legend(handles, labels, loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 1.08))
    fig.suptitle(f"{platform}: energy/op vs concurrency{tag}", y=1.13)
    return _save(fig, Path(out))


def energy_time_scatter(df: pd.DataFrame, platform: str, out) -> Path | None:
    """CPU: cell-median time/op against cell-median energy/op, one color per construct."""
    d = _default(df, platform)
    sub = d[d["workload"] == "CPU"]
    if sub.empty:
        return None
    fig, ax = plt.subplots(figsize=(5, 3.8))
    for c in COLORS:
        g = sub[sub["construct"] == c]
        if g.empty:
            continue
        med = g.groupby("p", dropna=False)[["ms_op", "primary_J_op"]].median().reset_index()
        ax.scatter(med["ms_op"], med["primary_J_op"], color=COLORS[c], marker=MARKERS[c],
                   label=SHORT[c], s=36, edgecolor="white", lw=0.5)
        for _, r in med.iterrows():
            if not pd.isna(r["p"]):
                ax.annotate(str(int(r["p"])), (r["ms_op"], r["primary_J_op"]), fontsize=6,
                            xytext=(3, 2), textcoords="offset points")
    ax.set_xscale("log")
    ax.set_xlabel("time/op (ms, cell median, log scale)")
    ax.set_ylabel(_ylabel(platform, "CPU"))
    ax.set_title(f"{platform} CPU: energy vs time (labels: p)")
    ax.grid(alpha=0.3)
    ax.legend(frameon=False, fontsize=8)
    return _save(fig, Path(out))


def _exp2_labels(sub):
    labels = []
    for c in ["SEQUENTIAL", "PLATFORM_THREADS"]:
        if (sub["construct"] == c).any():
            labels.append((c, None))
    for p in (4, 16):
        for c in ["FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"]:
            if ((sub["construct"] == c) & (sub["p"] == p)).any():
                labels.append((c, p))
    return labels


def _sel(sub, c, p):
    g = sub[sub["construct"] == c]
    return g if p is None else g[g["p"] == p]


def _name(c, p):
    return SHORT[c] if p is None else f"{SHORT[c]}$_{{{p}}}$"


def cluster_split_bars(df: pd.DataFrame, out) -> Path | None:
    """Mac: stacked median ECPU and PCPU energy/op per Exp-2 cell, DEFAULT (solid) next to
    BACKGROUND (hatched), one panel per workload."""
    if not {"ecpu_J_op", "pcpu_J_op"} <= set(df.columns):
        return None
    wls = [w for w in WORKLOADS if (df["workload"] == w).any()]
    if not wls:
        return None
    fig, axes = plt.subplots(1, len(wls), figsize=(4.8 * len(wls), 3.6), squeeze=False)
    fig.subplots_adjust(wspace=0.38)
    restrictions = [r for r in ("DEFAULT", "BACKGROUND") if (df["restriction"] == r).any()]
    width = 0.8 / max(1, len(restrictions))
    for ax, w in zip(axes[0], wls):
        sub = df[df["workload"] == w]
        labels = _exp2_labels(sub)
        for j, r in enumerate(restrictions):
            sr = sub[sub["restriction"] == r]
            e = [np.nanmedian(_sel(sr, c, p)["ecpu_J_op"]) if len(_sel(sr, c, p)) else np.nan for c, p in labels]
            pc = [np.nanmedian(_sel(sr, c, p)["pcpu_J_op"]) if len(_sel(sr, c, p)) else np.nan for c, p in labels]
            x = np.arange(len(labels)) + (j - (len(restrictions) - 1) / 2) * width
            hatch = "//" if r == "BACKGROUND" else None
            ax.bar(x, e, width, color="#009E73", hatch=hatch, edgecolor="white",
                   label=f"ECPU ({r})")
            ax.bar(x, pc, width, bottom=np.nan_to_num(e), color="#0072B2", hatch=hatch,
                   edgecolor="white", label=f"PCPU ({r})")
        ax.set_xticks(np.arange(len(labels)))
        ax.set_xticklabels([_name(c, p) for c, p in labels], rotation=45, ha="right")
        ax.set_ylabel("CPU energy/op by cluster (J, median)")
        ax.set_title(w)
        ax.grid(axis="y", alpha=0.3)
    axes[0][0].legend(frameon=False, fontsize=7)
    fig.suptitle("mac: E/P cluster split of CPU energy/op")
    return _save(fig, Path(out))


def placement_bars(df: pd.DataFrame, out) -> Path | None:
    """Intel: median primary energy/op (IQR bars) per placement cell for 2P, 2E, 2LP-E, with
    unpinned as a lighter descriptive reference."""
    restr = [r for r in ("2P", "2E", "2LPE", "unpinned") if (df["restriction"] == r).any()]
    if not any(r in restr for r in ("2P", "2E", "2LPE")):
        return None
    placed = df[df["restriction"].isin(["2P", "2E", "2LPE"])]
    wls = [w for w in WORKLOADS if (placed["workload"] == w).any()]
    fig, axes = plt.subplots(1, len(wls), figsize=(4.8 * len(wls), 3.6), squeeze=False)
    fig.subplots_adjust(wspace=0.38)
    width = 0.8 / len(restr)
    for ax, w in zip(axes[0], wls):
        m = _measure(w)
        sub = df[df["workload"] == w]
        labels = _exp2_labels(placed[placed["workload"] == w])
        for j, r in enumerate(restr):
            sr = sub[sub["restriction"] == r]
            qs = [_q(_sel(sr, c, p)[m]) for c, p in labels]
            med = np.array([q[0] for q in qs])
            lo = med - np.array([q[1] for q in qs])
            hi = np.array([q[2] for q in qs]) - med
            x = np.arange(len(labels)) + (j - (len(restr) - 1) / 2) * width
            ax.bar(x, med, width, yerr=[lo, hi], capsize=2, color=RESTRICTION_COLORS[r],
                   alpha=0.45 if r == "unpinned" else 1.0, label=r, edgecolor="white")
        ax.set_xticks(np.arange(len(labels)))
        ax.set_xticklabels([_name(c, p) for c, p in labels], rotation=45, ha="right")
        ax.set_ylabel(_ylabel("intel", w))
        if w in BLOCKING:
            ax.axhline(0, color="#555555", lw=0.6)
        ax.set_title(w)
        ax.grid(axis="y", alpha=0.3)
    axes[0][0].legend(frameon=False, fontsize=7)
    fig.suptitle("intel: equal-count placement (median, IQR)")
    return _save(fig, Path(out))


def all_figures(df: pd.DataFrame, platform: str, outdir) -> list[Path]:
    outdir = Path(outdir)
    made = [
        lambda_curves(df, platform, outdir / "lambda.pdf"),
        energy_time_scatter(df, platform, outdir / "energy_vs_time_cpu.pdf"),
    ]
    if platform == "mac":
        if "mem_J_op_active" in df.columns and df["mem_J_op_active"].notna().any():
            made.append(lambda_curves(df[df["workload"].isin(BLOCKING)], platform, outdir / "lambda_memory.pdf",
                                      measure_fn=lambda w: "mem_J_op_active", tag=" (memory, idle-subtracted)"))
        made.append(cluster_split_bars(df, outdir / "cluster_split.pdf"))
    else:
        made.append(placement_bars(df, outdir / "placement.pdf"))
    return [m for m in made if m is not None]
