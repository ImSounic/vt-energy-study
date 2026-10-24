"""Pure statistical helpers for Section 4.6 of the report.

Every function takes plain sequences or arrays and returns plain numbers,
tuples, or DataFrames, so each can be unit-tested on synthetic data with a
known answer. NaNs are dropped from samples before any test.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np
import pandas as pd
import scikit_posthocs as sp
from scipy import stats as st

N_BOOT = 10000


def _arr(x) -> np.ndarray:
    a = np.asarray(x, dtype=float).ravel()
    return a[~np.isnan(a)]


# --------------------------------------------------------------------------- effect sizes

def cliffs_delta(a, b) -> float:
    """Cliff's delta = P(a > b) - P(a < b). +1 if every a exceeds every b."""
    a, b = _arr(a), _arr(b)
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    diff = a[:, None] - b[None, :]
    return float((np.sign(diff)).mean())


def _cliffs_delta_vec(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Row-wise Cliff's delta for bootstrap replicate matrices (n_boot, n_a), (n_boot, n_b)."""
    return np.sign(A[:, :, None] - B[:, None, :]).mean(axis=(1, 2))


def epsilon_squared(H: float, n: int) -> float:
    """Kruskal-Wallis effect size eps^2 = H / ((n^2 - 1) / (n + 1)) = H / (n - 1)."""
    if n is None or n < 2 or H is None or not np.isfinite(H):
        return float("nan")
    return float(H / ((n * n - 1) / (n + 1)))


# --------------------------------------------------------------------------- multiplicity

def holm(pvals: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values in the original order (monotone, capped at 1).

    NaN entries stay NaN and do not count towards the number of tests.
    """
    p = np.asarray(list(pvals), dtype=float)
    out = np.full(p.shape, np.nan)
    ok = np.where(~np.isnan(p))[0]
    m = len(ok)
    if m == 0:
        return out.tolist()
    order = ok[np.argsort(p[ok], kind="mergesort")]
    running = 0.0
    for rank, idx in enumerate(order):
        adj = min(1.0, (m - rank) * p[idx])
        running = max(running, adj)
        out[idx] = running
    return out.tolist()


# --------------------------------------------------------------------------- bootstrap

def bootstrap_ci(statfn: Callable, *samples, n_boot: int = N_BOOT, level: float = 0.95,
                 seed: int = 0, vectorized: bool = False) -> tuple[float, float]:
    """Percentile bootstrap CI of statfn(*samples); each sample is resampled independently.

    With vectorized=True, statfn receives 2-D arrays (n_boot, n_i) and must return
    n_boot values (much faster); otherwise it is called once per replicate.
    Non-finite replicates are kept as +/-inf (so a CI can be unbounded) and NaN
    replicates are ignored.
    """
    arrs = [_arr(s) for s in samples]
    if any(len(a) == 0 for a in arrs):
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    boots = [a[rng.integers(0, len(a), size=(n_boot, len(a)))] for a in arrs]
    with np.errstate(divide="ignore", invalid="ignore"):
        if vectorized:
            vals = np.asarray(statfn(*boots), dtype=float)
        else:
            vals = np.array([statfn(*[b[i] for b in boots]) for i in range(n_boot)], dtype=float)
    vals = vals[~np.isnan(vals)]
    if len(vals) == 0:
        return float("nan"), float("nan")
    alpha = (1 - level) / 2
    lo, hi = np.quantile(vals, [alpha, 1 - alpha])
    return float(lo), float(hi)


def median_ci(x, n_boot: int = N_BOOT, level: float = 0.95, seed: int = 0) -> tuple[float, float, float]:
    """(median, lo, hi) with a percentile bootstrap CI of the median."""
    x = _arr(x)
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan")
    lo, hi = bootstrap_ci(lambda X: np.median(X, axis=1), x, n_boot=n_boot, level=level,
                          seed=seed, vectorized=True)
    return float(np.median(x)), lo, hi


def ratio_of_medians_ci(a, b, n_boot: int = N_BOOT, level: float = 0.95,
                        seed: int = 0) -> tuple[float, float, float]:
    """(median(a)/median(b), lo, hi) with an independent-resampling percentile bootstrap CI."""
    a, b = _arr(a), _arr(b)
    if len(a) == 0 or len(b) == 0:
        return float("nan"), float("nan"), float("nan")
    mb = np.median(b)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = float(np.median(a) / mb) if mb != 0 else float("nan")
    lo, hi = bootstrap_ci(lambda A, B: np.median(A, axis=1) / np.median(B, axis=1), a, b,
                          n_boot=n_boot, level=level, seed=seed, vectorized=True)
    return ratio, lo, hi


def cliffs_delta_ci(a, b, n_boot: int = N_BOOT, level: float = 0.95,
                    seed: int = 0) -> tuple[float, float, float]:
    """(delta, lo, hi) with a percentile bootstrap CI."""
    d = cliffs_delta(a, b)
    lo, hi = bootstrap_ci(_cliffs_delta_vec, a, b, n_boot=n_boot, level=level, seed=seed,
                          vectorized=True)
    return d, lo, hi


def epsilon_squared_ci(groups, n_boot: int = 2000, level: float = 0.95,
                       seed: int = 0) -> tuple[float, float, float]:
    """(eps^2, lo, hi): eps^2 of a Kruskal-Wallis test with a bootstrap CI (groups resampled)."""
    groups = [_arr(g) for g in groups]
    groups = [g for g in groups if len(g)]
    n = sum(len(g) for g in groups)
    H, _ = kruskal(groups)
    e = epsilon_squared(H, n)
    if len(groups) < 2 or not np.isfinite(e):
        return e, float("nan"), float("nan")

    def f(*G):
        with np.errstate(all="ignore"):
            h = st.kruskal(*G, axis=1).statistic
        h = np.where(np.isnan(h), 0.0, h)  # a replicate with all values tied has H = 0
        return h / (n - 1)

    lo, hi = bootstrap_ci(f, *groups, n_boot=n_boot, level=level, seed=seed, vectorized=True)
    return e, lo, hi


# --------------------------------------------------------------------------- equivalence and detection

def tost_ratio(a, b, margin: float = 0.05, level: float = 0.90, n_boot: int = N_BOOT,
               seed: int = 0) -> dict:
    """Ratio-of-medians TOST: equivalent iff the bootstrap `level` CI of median(a)/median(b)
    lies within [1 - margin, 1 + margin]."""
    ratio, lo, hi = ratio_of_medians_ci(a, b, n_boot=n_boot, level=level, seed=seed)
    ok = bool(np.isfinite(lo) and np.isfinite(hi) and lo >= 1 - margin and hi <= 1 + margin)
    return {"equivalent": ok, "ratio": ratio, "ci_lo": lo, "ci_hi": hi,
            "margin": margin, "level": level}


def below_detection_limit(x, level: float = 0.95, n_boot: int = N_BOOT, seed: int = 0) -> bool:
    """True iff the bootstrap CI of the median of x includes 0 (idle-subtracted values)."""
    med, lo, hi = median_ci(x, n_boot=n_boot, level=level, seed=seed)
    if not np.isfinite(lo):
        return False
    return bool(lo <= 0 <= hi)


# --------------------------------------------------------------------------- tests

def kruskal(groups) -> tuple[float, float]:
    """Kruskal-Wallis (H, p) over groups with data; (0, 1) if every value is tied."""
    groups = [_arr(g) for g in groups]
    groups = [g for g in groups if len(g)]
    if len(groups) < 2:
        return float("nan"), float("nan")
    allv = np.concatenate(groups)
    if np.all(allv == allv[0]):
        return 0.0, 1.0
    r = st.kruskal(*groups)
    return float(r.statistic), float(r.pvalue)


def dunn(df: pd.DataFrame, val: str, group: str, p_adjust: str | None = "holm") -> pd.DataFrame:
    """Dunn's pairwise test (scikit-posthocs), Holm-adjusted by default; a square p matrix."""
    d = df[[val, group]].dropna()
    d = d.assign(**{val: d[val].astype(float), group: d[group].astype(str)})
    if d[group].nunique() < 2:
        return pd.DataFrame()
    if d[val].nunique() < 2:  # all tied: no evidence of any difference
        labels = sorted(d[group].unique())
        return pd.DataFrame(1.0, index=labels, columns=labels)
    return sp.posthoc_dunn(d, val_col=val, group_col=group, p_adjust=p_adjust)


def mann_whitney(a, b, alternative: str = "two-sided") -> tuple[float, float]:
    """Mann-Whitney U (U of a, p). alternative 'less' tests a < b."""
    a, b = _arr(a), _arr(b)
    if len(a) == 0 or len(b) == 0:
        return float("nan"), float("nan")
    allv = np.concatenate([a, b])
    if np.all(allv == allv[0]):
        return float(len(a) * len(b) / 2), 1.0
    r = st.mannwhitneyu(a, b, alternative=alternative)
    return float(r.statistic), float(r.pvalue)


def spearman(x, y) -> tuple[float, float]:
    """Spearman (rho, p) on pairs where both values are present."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    if len(x) < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return float("nan"), float("nan")
    r = st.spearmanr(x, y)
    return float(r.statistic), float(r.pvalue)


def mw_power(cv: float, n: int, ratio: float = 1.10, alpha: float = 0.05, sims: int = 2000,
             seed: int = 0) -> float:
    """Simulated power of a two-sided Mann-Whitney U with n per group, for medians that differ
    by `ratio`, with normal noise whose CV (sd/mean) is `cv` in both groups."""
    if not np.isfinite(cv) or n < 2:
        return float("nan")
    rng = np.random.default_rng(seed)
    a = rng.normal(1.0, cv, size=(sims, n))
    b = rng.normal(ratio, cv * ratio, size=(sims, n))
    p = st.mannwhitneyu(a, b, alternative="two-sided", axis=1).pvalue
    return float(np.mean(p < alpha))


# --------------------------------------------------------------------------- descriptive

def describe(x) -> dict:
    x = _arr(x)
    n = len(x)
    if n == 0:
        return {"median": np.nan, "q1": np.nan, "q3": np.nan, "iqr": np.nan, "mean": np.nan,
                "cv": np.nan, "n": 0}
    q1, med, q3 = np.quantile(x, [0.25, 0.5, 0.75])
    mean = float(np.mean(x))
    cv = float(np.std(x, ddof=1) / mean) if n > 1 and mean != 0 else float("nan")
    return {"median": float(med), "q1": float(q1), "q3": float(q3), "iqr": float(q3 - q1),
            "mean": mean, "cv": cv, "n": n}


def cell_summary(df: pd.DataFrame, value: str, by: Sequence[str] | None = None) -> pd.DataFrame:
    """Per cell: median, q1, q3, IQR, mean, CV (sample sd / mean), and n of `value`."""
    from . import CELL_KEYS
    by = [c for c in (by or CELL_KEYS) if c in df.columns]
    rows = []
    for key, g in df.groupby(by, dropna=False, sort=True):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by, key)), **describe(g[value])})
    out = pd.DataFrame(rows, columns=list(by) + ["median", "q1", "q3", "iqr", "mean", "cv", "n"])
    if "p" in out.columns:
        out["p"] = out["p"].astype("Int64")
    return out


def ceil_div(a: int, b: int) -> int:
    return int(math.ceil(a / b))
