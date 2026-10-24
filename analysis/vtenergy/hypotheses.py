"""Hypothesis families of the report (Table "Hypothesis families", Section 4.6).

Each public family function takes the run-level DataFrame from `load` (one platform) and
returns a DataFrame with the columns of ROW_COLS. Holm is applied within each family
(H0-2.2: within each workload, over its p levels, as the table states). Missing cells never
raise: the affected test is emitted as a row with decision "skipped" and a note.

Tested measure (Section 4.2): primary energy/op (package on Intel, CPU_Energy on the Mac)
on CPU, and idle-subtracted primary energy/op on SLEEP and SOCKET; Memory family: idle-
subtracted DRAM + AMCC + DCS energy/op (Mac only).

Decisions:
    primary tests        reject / not rejected (on p_holm)
    Dunn post-hoc        reject only if p_holm < alpha AND the parent KW was rejected
    IU components        "VT lower" / "not lower" (uncorrected: no correction inside an IU test)
    TOST                 equivalent / not equivalent (one row after every non-rejected
                         two-sided pairwise contrast; skipped when a ratio is undefined)
    descriptive rows     descriptive / below detection limit / detected
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import BLOCKING, DEFAULT_RESTRICTION, LONG, NO_P, P_LEVELS, POOLED, SHORT, WORKLOADS
from . import stats as S

ROW_COLS = ["family", "test", "platform", "workload", "p", "comparison", "measure", "statistic",
            "p_raw", "p_holm", "effect", "effect_name", "ci_lo", "ci_hi", "decision", "note"]
MAIN_K = {"mac": 8, "intel": 16}
EXP2_P = [4, 16]


@dataclass
class Opts:
    alpha: float = 0.05
    n_boot: int = 10000
    n_boot_eps: int = 2000
    seed: int = 0
    margin: float = 0.05
    fork_split: int = 5
    d_ms: dict = field(default_factory=lambda: {"SLEEP": 10.0, "SOCKET": 10.0})


# --------------------------------------------------------------------------- helpers

def lab(construct: str, p=None) -> str:
    s = SHORT.get(construct, construct)
    if construct in NO_P or p is None or pd.isna(p):
        return s
    return f"{s}_{int(p)}"


def measure_for(workload: str) -> str:
    return "primary_J_op" if workload == "CPU" else "primary_J_op_active"


def _platform(df: pd.DataFrame, platform: str | None) -> str | None:
    if platform:
        return platform
    if df is None or df.empty or "platform" not in df.columns:
        return None
    ps = df["platform"].dropna().unique()
    return ps[0] if len(ps) else None


def _with_label(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["label", "workload", "construct", "p", "restriction"])
    d = df.copy()
    d["label"] = [lab(c, p) for c, p in zip(d["construct"], d["p"])]
    return d


def _exp1(df: pd.DataFrame, platform: str) -> pd.DataFrame:
    d = _with_label(df)
    if d.empty:
        return d
    return d[d["restriction"] == DEFAULT_RESTRICTION.get(platform, "DEFAULT")]


def _vals(d: pd.DataFrame, workload: str, label: str, measure: str) -> np.ndarray:
    if d.empty or measure not in d.columns:
        return np.array([])
    x = d.loc[(d["workload"] == workload) & (d["label"] == label), measure]
    return x.astype(float).dropna().to_numpy()


def _cells(pairs) -> list[str]:
    return [lab(LONG.get(c, c), p) for c, p in pairs]


_ID = itertools.count()


def _row(**kw) -> dict:
    r = {c: np.nan for c in ROW_COLS}
    r.update({"p": pd.NA, "comparison": "", "note": "", "decision": "", "effect_name": "",
              "measure": "", "workload": ""})
    r.update(kw)
    r.setdefault("_id", next(_ID))
    r.setdefault("_kind", "primary")
    return r


def _skip(family, test, platform, workload, p, comparison, measure, note) -> dict:
    return _row(family=family, test=test, platform=platform, workload=workload, p=p,
                comparison=comparison, measure=measure, decision="skipped", note=note,
                _kind="skipped")


def _bdl_labels(d, workload, labels, measure, opts) -> list[str]:
    if not measure.endswith("_active"):
        return []
    out = []
    for l in labels:
        x = _vals(d, workload, l, measure)
        if len(x) and S.below_detection_limit(x, n_boot=opts.n_boot, seed=opts.seed):
            out.append(l)
    return out


def _kw(family, d, platform, workload, p, labels, measure, opts, test="KW") -> dict:
    groups = {l: _vals(d, workload, l, measure) for l in labels}
    present = [l for l in labels if len(groups[l])]
    missing = [l for l in labels if not len(groups[l])]
    comp = " | ".join(labels)
    if len(present) < 2:
        return _skip(family, test, platform, workload, p, comp, measure,
                     f"fewer than 2 cells with data; missing: {', '.join(missing) or '-'}")
    H, pv = S.kruskal([groups[l] for l in present])
    e, lo, hi = S.epsilon_squared_ci([groups[l] for l in present], n_boot=opts.n_boot_eps,
                                     seed=opts.seed)
    notes = []
    if missing:
        notes.append(f"incomplete, missing: {', '.join(missing)}")
    bdl = _bdl_labels(d, workload, present, measure, opts)
    if bdl:
        notes.append(f"below detection limit: {', '.join(bdl)}")
    notes.append("n=" + ",".join(str(len(groups[l])) for l in present))
    return _row(family=family, test=test, platform=platform, workload=workload, p=p,
                comparison=" | ".join(present), measure=measure, statistic=H, p_raw=pv,
                effect=e, effect_name="epsilon^2", ci_lo=lo, ci_hi=hi, note="; ".join(notes))


def _pair_effect(a, b, opts):
    return S.cliffs_delta_ci(a, b, n_boot=opts.n_boot, seed=opts.seed)


def _dunn_rows(family, d, platform, workload, p, labels, measure, opts, parent, pairs=None):
    """Dunn post-hoc rows for `pairs` (default: all pairs among labels with data).
    Holm is applied over exactly the reported pairs."""
    sub = d[(d["workload"] == workload) & (d["label"].isin(labels))][["label", measure]].dropna()
    present = [l for l in labels if (sub["label"] == l).any()]
    if len(present) < 2:
        return []
    if pairs is None:
        pairs = list(itertools.combinations(present, 2))
    pairs = [(a, b) for a, b in pairs if a in present and b in present]
    if not pairs:
        return []
    pm = S.dunn(sub, measure, "label", p_adjust=None)
    raw = [float(pm.loc[a, b]) for a, b in pairs]
    adj = S.holm(raw)
    rows = []
    for (a, b), pr, ph in zip(pairs, raw, adj):
        xa, xb = _vals(d, workload, a, measure), _vals(d, workload, b, measure)
        dl, lo, hi = _pair_effect(xa, xb, opts)
        bdl = _bdl_labels(d, workload, [a, b], measure, opts)
        rows.append(_row(family=family, test="Dunn", platform=platform, workload=workload, p=p,
                         comparison=f"{a} vs {b}", measure=measure, p_raw=pr, p_holm=ph,
                         effect=dl, effect_name="Cliff's delta", ci_lo=lo, ci_hi=hi,
                         note=(f"below detection limit: {', '.join(bdl)}" if bdl else ""),
                         _kind="posthoc", _parent=parent, _samples=(xa, xb), _bdl=bool(bdl)))
    return rows


def _mw_row(family, d_a, d_b, platform, workload, p, la, lb, measure, opts, comparison,
            test="MW", note="") -> dict:
    xa, xb = _vals(d_a, workload, la, measure), _vals(d_b, workload, lb, measure)
    if not len(xa) or not len(xb):
        miss = [n for n, x in ((comparison.split(" vs ")[0], xa), (comparison.split(" vs ")[-1], xb))
                if not len(x)]
        return _skip(family, test, platform, workload, p, comparison, measure,
                     f"missing data: {', '.join(miss)}" + (f"; {note}" if note else ""))
    U, pv = S.mann_whitney(xa, xb, "two-sided")
    dl, lo, hi = _pair_effect(xa, xb, opts)
    bdl = _bdl_labels(d_a, workload, [la], measure, opts) + _bdl_labels(d_b, workload, [lb], measure, opts)
    notes = [note] if note else []
    if bdl:
        notes.append(f"below detection limit: {', '.join(bdl)}")
    notes.append(f"n={len(xa)},{len(xb)}")
    return _row(family=family, test=test, platform=platform, workload=workload, p=p,
                comparison=comparison, measure=measure, statistic=U, p_raw=pv, effect=dl,
                effect_name="Cliff's delta", ci_lo=lo, ci_hi=hi, note="; ".join(notes),
                _samples=(xa, xb), _bdl=bool(bdl))


def _tost_row(r: dict, opts: Opts) -> dict:
    xa, xb = r["_samples"]
    base = dict(family=r["family"], test="TOST", platform=r["platform"], workload=r["workload"],
                p=r["p"], comparison=r["comparison"], measure=r["measure"],
                effect_name="ratio of medians", _kind="tost")
    if r.get("_bdl"):
        return _row(**base, decision="skipped",
                    note="ratio undefined: a cell is below the detection limit")
    if not len(xb) or np.median(xb) <= 0 or np.median(xa) < 0:
        return _row(**base, decision="skipped", note="ratio undefined: non-positive median")
    t = S.tost_ratio(xa, xb, margin=opts.margin, level=0.90, n_boot=opts.n_boot, seed=opts.seed)
    return _row(**base, effect=t["ratio"], ci_lo=t["ci_lo"], ci_hi=t["ci_hi"],
                decision="equivalent" if t["equivalent"] else "not equivalent",
                note=f"90% bootstrap CI vs [{1 - opts.margin:.2f}, {1 + opts.margin:.2f}]")


def _decide(p_holm, alpha):
    if p_holm is None or not np.isfinite(p_holm):
        return "skipped"
    return "reject" if p_holm < alpha else "not rejected"


def _finalize(rows: list[dict], opts: Opts, holm_key=None) -> pd.DataFrame:
    """Holm within groups of primary rows, then post-hoc decisions, IU summaries, and TOST rows.

    holm_key(row) -> group key; default: the family."""
    holm_key = holm_key or (lambda r: r["family"])
    prim = [r for r in rows if r["_kind"] == "primary"]
    groups: dict = {}
    for r in prim:
        groups.setdefault(holm_key(r), []).append(r)
    for g in groups.values():
        adj = S.holm([r["p_raw"] for r in g])
        for r, a in zip(g, adj):
            r["p_holm"] = a
            r["decision"] = _decide(a, opts.alpha)
    by_id = {r["_id"]: r for r in rows}
    for r in rows:
        if r["_kind"] == "posthoc":
            parent = by_id.get(r.get("_parent"))
            ok = parent is not None and parent["decision"] == "reject"
            r["decision"] = "reject" if (ok and np.isfinite(r["p_holm"]) and r["p_holm"] < opts.alpha) \
                else "not rejected"
            if not ok:
                r["note"] = "; ".join(x for x in [r["note"], "parent test not rejected"] if x)

    out = []
    for r in rows:
        out.append(r)
        if "_samples" in r and r["decision"] == "not rejected":
            out.append(_tost_row(r, opts))

    # IU summaries: smallest p whose IU test rejects, per (family, workload, measure).
    iu = [r for r in out if r["test"] == "IU"]
    keys = []
    for r in iu:
        k = (r["family"], r["workload"], r["measure"], r["platform"])
        if k not in keys:
            keys.append(k)
    for fam, w, m, plat in keys:
        g = [r for r in iu if (r["family"], r["workload"], r["measure"], r["platform"]) == (fam, w, m, plat)]
        rej = [r for r in g if r["decision"] == "reject"]
        if rej:
            best = min(rej, key=lambda r: int(r["p"]))
            out.append(_row(family=fam, test="IU smallest p", platform=plat, workload=w, p=best["p"],
                            comparison=best["comparison"], measure=m, p_raw=best["p_raw"],
                            p_holm=best["p_holm"], effect=best["effect"],
                            effect_name=best["effect_name"], ci_lo=best["ci_lo"],
                            ci_hi=best["ci_hi"], decision="reject",
                            note=f"rejecting p levels: {', '.join(str(int(r['p'])) for r in rej)}",
                            _kind="summary"))
        else:
            tested = [r for r in g if r["decision"] != "skipped"]
            out.append(_row(family=fam, test="IU smallest p", platform=plat, workload=w,
                            comparison="VT vs every alternative", measure=m,
                            decision="not rejected" if tested else "skipped",
                            note="no p level rejects" if tested else "no p level testable",
                            _kind="summary"))
    return _frame(out)


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame([{c: r.get(c) for c in ROW_COLS} for r in rows], columns=ROW_COLS)
    df["p"] = pd.array([pd.NA if (v is None or pd.isna(v)) else int(v) for v in df["p"]], dtype="Int64")
    return df


# --------------------------------------------------------------------------- families

def main_family(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """Main: per workload, KW across SEQ, PT, FP_k, FJ_k, VT_k on CPU (k = 8 Mac, 16 Intel) and
    across PT, FP_256, FJ_256, VT_256 on SLEEP and SOCKET. Rejected if any workload rejects."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    d = _exp1(df, platform)
    k = MAIN_K.get(platform, 8)
    rows = []
    for w in WORKLOADS:
        if w == "CPU":
            labels = _cells([("SEQ", None), ("PT", None), ("FP", k), ("FJ", k), ("VT", k)])
            p = k
        else:
            labels = _cells([("PT", None), ("FP", 256), ("FJ", 256), ("VT", 256)])
            p = 256
        rows.append(_kw("Main", d, platform, w, p, labels, measure_for(w), opts))
    out = _finalize(rows, opts)
    tested = out[out["decision"].isin(["reject", "not rejected"])]
    any_rej = (tested["decision"] == "reject").any()
    summary = _row(family="Main", test="any workload", platform=platform,
                   comparison="H0 rejected if any workload's KW rejects",
                   p_holm=float(tested["p_holm"].min()) if len(tested) else np.nan,
                   decision=("reject" if any_rej else "not rejected") if len(tested) else "skipped",
                   note=f"{len(tested)} of 3 workloads tested", _kind="summary")
    return pd.concat([out, _frame([summary])], ignore_index=True)


def _h0_1_1_rows(d, platform, workloads, measure_fn, family, opts):
    rows = []
    for w in workloads:
        m = measure_fn(w)
        for c in POOLED:
            labels = [lab(c, p) for p in P_LEVELS]
            r = _kw(family, d, platform, w, pd.NA, labels, m, opts, test="KW across p")
            r["comparison"] = f"{SHORT[c]}: " + r["comparison"]
            rows.append(r)
            if r["_kind"] == "primary":
                rows += _dunn_rows(family, d, platform, w, pd.NA, labels, m, opts, r["_id"])
    return rows


def h0_1_1(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """H0-1.1: KW across p per construct (FP, FJ, VT) and workload; Dunn (Holm); eps^2."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    rows = _h0_1_1_rows(_exp1(df, platform), platform, WORKLOADS, measure_for, "H0-1.1", opts)
    return _finalize(rows, opts)


def select_best_configs(df, platform=None, fork_max: int | None = None) -> pd.DataFrame:
    """Per workload: SEQ plus the lowest-median concurrent configuration (any construct but SEQ)
    of the tested measure, under default restriction. fork_max limits the forks used for the
    selection (Mac split sample: 5). Returns columns construct, p, workload, restriction, median."""
    platform = _platform(df, platform)
    d = _exp1(df, platform)
    restriction = DEFAULT_RESTRICTION.get(platform, "DEFAULT")
    if fork_max is not None and not d.empty:
        d = d[d["fork_index"] <= fork_max]
    out = []
    for w in WORKLOADS:
        m = measure_for(w)
        sub = d[(d["workload"] == w) & (d["construct"] != "SEQUENTIAL")] if not d.empty else d
        if sub.empty or m not in sub.columns:
            continue
        med = sub.groupby("label")[m].median().dropna()
        if med.empty:
            continue
        best = med.idxmin()
        row = sub[sub["label"] == best].iloc[0]
        out.append({"construct": "SEQUENTIAL", "p": pd.NA, "workload": w, "restriction": restriction,
                    "median": float(d[(d["workload"] == w) & (d["construct"] == "SEQUENTIAL")][m].median())
                    if (d["construct"] == "SEQUENTIAL").any() else np.nan})
        out.append({"construct": row["construct"], "p": row["p"], "workload": w,
                    "restriction": restriction, "median": float(med[best])})
    res = pd.DataFrame(out, columns=["construct", "p", "workload", "restriction", "median"])
    res["p"] = res["p"].astype("Int64")
    return res


def h0_1_2_split(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """H0-1.2 (Mac): forks 1..5 select the lowest-median concurrent configuration, forks 6..10
    test SEQ against it (MW two-sided, Cliff's delta). Holm over the workloads."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    d = _exp1(df, platform)
    rows = []
    for w in WORKLOADS:
        m = measure_for(w)
        sel = select_best_configs(df, platform, fork_max=opts.fork_split)
        sel = sel[(sel["workload"] == w) & (sel["construct"] != "SEQUENTIAL")]
        if sel.empty:
            rows.append(_skip("H0-1.2", "MW", platform, w, pd.NA, "SEQ vs best", m,
                              f"no concurrent cell in forks 1-{opts.fork_split}"))
            continue
        best = lab(sel.iloc[0]["construct"], sel.iloc[0]["p"])
        test = d[d["fork_index"] > opts.fork_split] if not d.empty else d
        rows.append(_mw_row("H0-1.2", test, test, platform, w, sel.iloc[0]["p"], "SEQ", best, m, opts,
                            f"SEQ vs {best}",
                            note=f"selected on forks 1-{opts.fork_split} (median {sel.iloc[0]['median']:.4g}); "
                                 f"tested on forks > {opts.fork_split}"))
    return _finalize(rows, opts)


def h0_1_2_confirm(confirm_df, platform=None, opts: Opts | None = None, cells=None) -> pd.DataFrame:
    """H0-1.2 (Intel, A3-D6): test SEQ against the selected configuration on the fresh forks of the
    confirmation campaign only. `cells` (from select_best) disambiguates if needed."""
    opts = opts or Opts()
    platform = _platform(confirm_df, platform) or "intel"
    d = _with_label(confirm_df)
    rows = []
    for w in WORKLOADS:
        m = measure_for(w)
        sub = d[d["workload"] == w] if not d.empty else d
        others = sorted(set(sub["label"]) - {"SEQ"}) if not sub.empty else []
        if cells is not None and len(cells):
            want = [lab(c, p) for c, p, ww in zip(cells["construct"], cells["p"], cells["workload"])
                    if ww == w and c != "SEQUENTIAL"]
            others = [o for o in others if o in want]
        if len(others) != 1:
            rows.append(_skip("H0-1.2", "MW", platform, w, pd.NA, "SEQ vs best", m,
                              f"confirmation campaign has {len(others)} concurrent cells for {w} "
                              f"({', '.join(others) or 'none'}); need exactly 1"))
            continue
        best = others[0]
        p = sub[sub["label"] == best]["p"].iloc[0]
        rows.append(_mw_row("H0-1.2", sub, sub, platform, w, p, "SEQ", best, m, opts, f"SEQ vs {best}",
                            note="confirmation campaign (A3-D6): fresh forks only"))
    return _finalize(rows, opts)


def h0_1_2(df, platform=None, confirm_df=None, opts: Opts | None = None) -> pd.DataFrame:
    opts = opts or Opts()
    platform = _platform(df, platform)
    if platform == "mac":
        return h0_1_2_split(df, platform, opts)
    if confirm_df is not None and not confirm_df.empty:
        cells = select_best_configs(df, platform) if df is not None and not df.empty else None
        return h0_1_2_confirm(confirm_df, platform, opts, cells=cells)
    return _frame([_skip("H0-1.2", "MW", platform, w, pd.NA, "SEQ vs best", measure_for(w),
                         "Intel uses the confirmation campaign (A3-D6); pass --confirm DIR")
                   for w in WORKLOADS])


def h0_1_3(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """H0-1.3: Spearman rho between cell-median time/op and energy/op, CPU only (23 cells)."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    d = _exp1(df, platform)
    sub = d[d["workload"] == "CPU"] if not d.empty else d
    if sub.empty:
        return _frame([_skip("H0-1.3", "Spearman", platform, "CPU", pd.NA, "cell medians ms_op vs J_op",
                             "primary_J_op", "no CPU cells")])
    med = sub.groupby("label")[["ms_op", "primary_J_op"]].median().dropna()
    if len(med) < 3:
        return _frame([_skip("H0-1.3", "Spearman", platform, "CPU", pd.NA, "cell medians ms_op vs J_op",
                             "primary_J_op", f"{len(med)} cells; need >= 3")])
    rho, pv = S.spearman(med["ms_op"], med["primary_J_op"])
    lo, hi = S.bootstrap_ci(lambda i: S.spearman(med["ms_op"].to_numpy()[i.astype(int)],
                                                 med["primary_J_op"].to_numpy()[i.astype(int)])[0],
                            np.arange(len(med)), n_boot=min(opts.n_boot, 2000), seed=opts.seed)
    row = _row(family="H0-1.3", test="Spearman", platform=platform, workload="CPU",
               comparison="cell medians ms_op vs primary_J_op", measure="primary_J_op",
               statistic=rho, p_raw=pv, effect=rho, effect_name="Spearman rho", ci_lo=lo, ci_hi=hi,
               note=f"{len(med)} cells" + ("" if len(med) == 23 else " (expected 23)"))
    return _finalize([row], opts)


def _h0_2_1_rows(d, platform, workloads, measure_fn, family, opts):
    rows = []
    for w in workloads:
        m = measure_fn(w)
        for p in P_LEVELS:
            vt = lab("VIRTUAL_THREADS", p)
            labels = [lab("FIXED_POOL", p), lab("FORK_JOIN", p), vt, "PT", "SEQ"]
            if not len(_vals(d, w, vt, m)):
                rows.append(_skip(family, "KW", platform, w, p, " | ".join(labels), m, f"no data for {vt}"))
                continue
            r = _kw(family, d, platform, w, p, labels, m, opts)
            if w in BLOCKING and p < 256:
                r["note"] = "; ".join(x for x in [r["note"], f"FP/FJ at p<256 are floor-bound (see Blocking)"] if x)
            rows.append(r)
            if r["_kind"] == "primary":
                pairs = [(vt, o) for o in labels if o != vt]
                rows += _dunn_rows(family, d, platform, w, p, labels, m, opts, r["_id"], pairs=pairs)
    return rows


def h0_2_1(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """H0-2.1: per workload and p, KW across FP_p, FJ_p, VT_p, PT, SEQ; Dunn VT vs each; delta."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    return _finalize(_h0_2_1_rows(_exp1(df, platform), platform, WORKLOADS, measure_for, "H0-2.1", opts),
                     opts)


def _h0_2_2_rows(d, platform, workloads, measure_fn, family, opts):
    rows = []
    for w in workloads:
        m = measure_fn(w)
        for p in (P_LEVELS if w == "CPU" else [256]):
            vt = lab("VIRTUAL_THREADS", p)
            alts = [lab("FIXED_POOL", p), lab("FORK_JOIN", p), "PT", "SEQ"]
            xv = _vals(d, w, vt, m)
            if not len(xv):
                rows.append(_skip(family, "IU", platform, w, p, f"{vt} < every alternative", m,
                                  f"no data for {vt}"))
                continue
            comps, missing = [], []
            for a in alts:
                xa = _vals(d, w, a, m)
                if not len(xa):
                    missing.append(a)
                    continue
                U, pv = S.mann_whitney(xv, xa, "less")
                dl, lo, hi = _pair_effect(xv, xa, opts)
                comps.append(_row(family=family, test="MW one-sided (IU component)", platform=platform,
                                  workload=w, p=p, comparison=f"{vt} < {a}", measure=m, statistic=U,
                                  p_raw=pv, effect=dl, effect_name="Cliff's delta", ci_lo=lo, ci_hi=hi,
                                  decision="VT lower" if pv < opts.alpha else "not lower",
                                  note="uncorrected (no correction inside the IU test)",
                                  _kind="component"))
            rows += comps
            if missing:
                rows.append(_skip(family, "IU", platform, w, p, f"{vt} < every alternative", m,
                                  f"missing alternatives: {', '.join(missing)}"))
                continue
            weakest = max(comps, key=lambda r: r["effect"])
            bdl = _bdl_labels(d, w, [vt] + alts, m, opts)
            rows.append(_row(family=family, test="IU", platform=platform, workload=w, p=p,
                             comparison=f"{vt} < every alternative", measure=m,
                             p_raw=max(r["p_raw"] for r in comps), effect=weakest["effect"],
                             effect_name="Cliff's delta (weakest alternative)", ci_lo=weakest["ci_lo"],
                             ci_hi=weakest["ci_hi"],
                             note="; ".join(x for x in [f"weakest vs {weakest['comparison'].split(' < ')[1]}",
                                                         f"below detection limit: {', '.join(bdl)}" if bdl else ""]
                                            if x)))
    return rows


def h0_2_2(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """H0-2.2 (IU): VT_p lower than FP_p, FJ_p, PT and SEQ by one-sided MW each; IU p = max.
    Holm over the p levels per workload (7 on CPU, p = 256 only on SLEEP/SOCKET)."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    rows = _h0_2_2_rows(_exp1(df, platform), platform, WORKLOADS, measure_for, "H0-2.2", opts)
    return _finalize(rows, opts, holm_key=lambda r: (r["family"], r["workload"]))


def floor_ratio(df: pd.DataFrame, d_ms=None) -> pd.Series:
    """ms_op / (ceil(256/p) * d) for FP, FJ (p = pool size) and SEQ (p = 1) on SLEEP/SOCKET."""
    d_ms = d_ms if d_ms is not None else Opts().d_ms
    if not isinstance(d_ms, dict):
        d_ms = {w: float(d_ms) for w in BLOCKING}
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for i, (c, p, w, ms) in enumerate(zip(df["construct"], df["p"], df["workload"], df["ms_op"])):
        if w not in BLOCKING or w not in d_ms:
            continue
        if c == "SEQUENTIAL":
            pp = 1
        elif c in ("FIXED_POOL", "FORK_JOIN") and not pd.isna(p):
            pp = int(p)
        else:
            continue
        out.iloc[i] = ms / (S.ceil_div(256, pp) * d_ms[w])
    return out


def blocking(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """Blocking workloads: detection-limit rule per cell on idle-subtracted J/op (and on the
    memory measure on the Mac), and floor ratios for FP, FJ, SEQ (descriptive)."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    d = _exp1(df, platform)
    rows = []
    if d.empty or not d["workload"].isin(BLOCKING).any():
        return _frame([_skip("Blocking", "detection limit", platform, w, pd.NA, "", "primary_J_op_active",
                             "no cells") for w in BLOCKING])
    measures = ["primary_J_op_active"] + (["mem_J_op_active"] if platform == "mac" and "mem_J_op_active" in d else [])
    d = d.assign(floor_ratio=floor_ratio(d, opts.d_ms))
    keys = d[d["workload"].isin(BLOCKING)][["workload", "label", "construct", "p"]].drop_duplicates()
    keys = keys.sort_values(["workload", "construct", "p"])
    for _, k in keys.iterrows():
        w, l = k["workload"], k["label"]
        for m in measures:
            x = _vals(d, w, l, m)
            if not len(x):
                continue
            med, lo, hi = S.median_ci(x, n_boot=opts.n_boot, seed=opts.seed)
            rows.append(_row(family="Blocking", test="detection limit", platform=platform, workload=w,
                             p=k["p"], comparison=l, measure=m, effect=med, effect_name="median",
                             ci_lo=lo, ci_hi=hi, _kind="descriptive",
                             decision="below detection limit" if lo <= 0 <= hi
                             else ("detected (negative: below idle)" if hi < 0 else "detected"),
                             note=f"95% bootstrap CI of the median; n={len(x)}"))
        fr = _vals(d, w, l, "floor_ratio")
        if len(fr):
            med, lo, hi = S.median_ci(fr, n_boot=opts.n_boot, seed=opts.seed)
            pp = 1 if k["construct"] == "SEQUENTIAL" else int(k["p"])
            rows.append(_row(family="Blocking", test="floor ratio", platform=platform, workload=w, p=k["p"],
                             comparison=l, measure="ms_op / (ceil(256/p) d)", effect=med,
                             effect_name="floor ratio", ci_lo=lo, ci_hi=hi, decision="descriptive",
                             note=f"floor = {S.ceil_div(256, pp)} x {opts.d_ms[w]:g} ms", _kind="descriptive"))
    return _frame(rows)


def h0_3_1(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """H0-3.1. Mac: BACKGROUND vs DEFAULT per Exp-2 cell (MW, delta, time penalty % with a 95%
    bootstrap CI). Intel: 2E and 2LP-E vs 2P per placement cell; unpinned vs 2P descriptive."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    d = _with_label(df)
    rows = []
    if platform == "mac":
        treat, refs = ["BACKGROUND"], "DEFAULT"
    else:
        treat, refs = ["2E", "2LPE"], "2P"
    # Exp-2 / placement cells: those run under a non-default restriction.
    restricted = d["restriction"] != DEFAULT_RESTRICTION.get(platform, "DEFAULT") if not d.empty else None
    tcells = d[restricted][["workload", "label", "construct", "p"]].drop_duplicates() \
        if not d.empty else pd.DataFrame()
    if tcells.empty:
        return _frame([_skip("H0-3.1", "MW", platform, w, pd.NA, f"{'/'.join(treat)} vs {refs}",
                             measure_for(w), "no restricted cells in this campaign") for w in WORKLOADS])
    tcells = tcells.sort_values(["workload", "construct", "p"])
    for _, k in tcells.iterrows():
        w, l, p = k["workload"], k["label"], k["p"]
        m = measure_for(w)
        dr = d[d["restriction"] == refs]
        for t in treat:
            dt = d[d["restriction"] == t]
            comp = f"{l} {t} vs {refs}"
            r = _mw_row("H0-3.1", dt, dr, platform, w, p, l, l, m, opts, comp)
            rows.append(r)
            ta, tb = _vals(dt, w, l, "ms_op"), _vals(dr, w, l, "ms_op")
            if len(ta) and len(tb):
                ratio, lo, hi = S.ratio_of_medians_ci(ta, tb, n_boot=opts.n_boot, seed=opts.seed)
                rows.append(_row(family="H0-3.1", test="time penalty", platform=platform, workload=w, p=p,
                                 comparison=comp, measure="ms_op", effect=(ratio - 1) * 100,
                                 effect_name="time penalty %", ci_lo=(lo - 1) * 100, ci_hi=(hi - 1) * 100,
                                 decision="descriptive", note="median time/op ratio - 1; 95% bootstrap CI",
                                 _kind="descriptive"))
        if platform != "mac":
            du = d[d["restriction"] == "unpinned"]
            ua, ub = _vals(du, w, l, m), _vals(dr, w, l, m)
            if len(ua) and len(ub):
                ratio, lo, hi = S.ratio_of_medians_ci(ua, ub, n_boot=opts.n_boot, seed=opts.seed)
                rows.append(_row(family="H0-3.1", test="descriptive", platform=platform, workload=w, p=p,
                                 comparison=f"{l} unpinned vs 2P", measure=m, effect=ratio,
                                 effect_name="ratio of medians", ci_lo=lo, ci_hi=hi, decision="descriptive",
                                 note="unpinned is reported descriptively", _kind="descriptive"))
    return _finalize(rows, opts)


def h0_3_2(df, platform=None, opts: Opts | None = None) -> pd.DataFrame:
    """H0-3.2 (Mac): per workload at p in {4, 16}, DEFAULT, KW of the E-cluster share across the
    five constructs (SEQ and PT shared between the two p levels)."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    if platform != "mac":
        return _frame([])
    d = _exp1(df, platform)
    rows = []
    for w in WORKLOADS:
        for p in EXP2_P:
            labels = ["SEQ", "PT", lab("FIXED_POOL", p), lab("FORK_JOIN", p), lab("VIRTUAL_THREADS", p)]
            r = _kw("H0-3.2", d, platform, w, p, labels, "ecpu_share", opts)
            r["note"] = "; ".join(x for x in [r["note"], "SEQ, PT shared across p (not independent)"] if x)
            rows.append(r)
    return _finalize(rows, opts)


def memory_family(df, platform=None, opts: Opts | None = None,
                  measure: str = "mem_J_op_active") -> pd.DataFrame:
    """Memory (Mac; SLEEP, SOCKET): H0-1.1, H0-2.1 and H0-2.2 repeated on memory-subsystem
    energy/op (DRAM + AMCC + DCS, idle-subtracted), one Holm family over all their tests."""
    opts = opts or Opts()
    platform = _platform(df, platform)
    if platform != "mac":
        return _frame([])
    d = _exp1(df, platform)
    if measure not in d.columns:
        return _frame([_skip("Memory", "KW", platform, w, pd.NA, "", measure, f"no {measure} column")
                       for w in BLOCKING])
    mf = lambda w: measure  # noqa: E731
    rows = []
    for sub, fn in (("H0-1.1", _h0_1_1_rows), ("H0-2.1", _h0_2_1_rows), ("H0-2.2", _h0_2_2_rows)):
        rs = fn(d, platform, BLOCKING, mf, "Memory", opts)
        for r in rs:
            r["test"] = f"{sub} {r['test']}"
        rows += rs
    out = _finalize(rows, opts)
    # _finalize keys IU summaries on test == "IU"; ours are prefixed, so add them here.
    iu = out[out["test"] == "H0-2.2 IU"]
    extra = []
    for w in BLOCKING:
        g = iu[(iu["workload"] == w) & (iu["decision"] == "reject")]
        extra.append(_row(family="Memory", test="H0-2.2 IU smallest p", platform=platform, workload=w,
                          p=g["p"].min() if len(g) else pd.NA, measure=measure,
                          comparison="VT vs every alternative",
                          decision="reject" if len(g) else ("not rejected" if (iu["workload"] == w).any()
                                                            and (iu[iu["workload"] == w]["decision"] != "skipped").any()
                                                            else "skipped"),
                          _kind="summary"))
    return pd.concat([out, _frame(extra)], ignore_index=True)


def ax7_drift(df, measure: str = "primary_J_op", opts: Opts | None = None) -> pd.DataFrame:
    """AX7: Spearman of the within-cell residual (value / cell median) against run order, per
    platform (all workloads) and per platform x workload. Holm within the family."""
    opts = opts or Opts()
    rows = []
    if df is None or df.empty or "order" not in df.columns:
        return _frame([_skip("AX7", "Spearman", None, "", pd.NA, "residual vs order", measure, "no data")])
    keys = [k for k in ["construct", "p", "workload", "restriction"] if k in df.columns]
    for plat, g in df.groupby("platform"):
        g = g.copy()
        g["_k"] = ["|".join(str(v) for v in t) for t in g[keys].itertuples(index=False)]
        med = g.groupby("_k")[measure].transform("median")
        cnt = g.groupby("_k")[measure].transform("count")
        with np.errstate(divide="ignore", invalid="ignore"):
            g["_res"] = np.where((med != 0) & (cnt >= 2), g[measure] / med, np.nan)
        g["_ord"] = g["order"].astype("Float64").astype(float)
        for w, gg in [("", g)] + [(w, g[g["workload"] == w]) for w in WORKLOADS if (g["workload"] == w).any()]:
            ok = gg[["_res", "_ord"]].dropna()
            if len(ok) < 3:
                rows.append(_skip("AX7", "Spearman", plat, w, pd.NA, "residual vs run order", measure,
                                  f"{len(ok)} usable runs"))
                continue
            rho, pv = S.spearman(ok["_res"], ok["_ord"])
            rows.append(_row(family="AX7", test="Spearman", platform=plat, workload=w or "all",
                             comparison="within-cell residual (value / cell median) vs run order",
                             measure=measure, statistic=rho, p_raw=pv, effect=rho, effect_name="Spearman rho",
                             note=f"n={len(ok)} runs"))
    return _finalize(rows, opts)


def run_all(df, platform=None, confirm_df=None, opts: Opts | None = None) -> pd.DataFrame:
    opts = opts or Opts()
    platform = _platform(df, platform)
    parts = [
        main_family(df, platform, opts),
        h0_1_1(df, platform, opts),
        h0_1_2(df, platform, confirm_df, opts),
        h0_1_3(df, platform, opts),
        h0_2_1(df, platform, opts),
        h0_2_2(df, platform, opts),
        blocking(df, platform, opts),
        h0_3_1(df, platform, opts),
        h0_3_2(df, platform, opts),
        memory_family(df, platform, opts),
        ax7_drift(df, opts=opts),
    ]
    parts = [p for p in parts if p is not None and len(p)]
    return pd.concat(parts, ignore_index=True) if parts else _frame([])
