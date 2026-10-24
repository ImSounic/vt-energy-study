"""Loaders: campaign directories (A3-D8 layout) and the A2 pilot layout -> one row per run.

A run is one JMH fork. Its value for every metric is the median over its measured
iterations (report Section 4.5: "its value is the median of its 5 measured iterations").

Columns (all platforms):
    run_id, platform, campaign, construct, p (Int64, NA for SEQ/PT), workload, restriction,
    fork_index, order, batch, seed, n_iter, ms_op,
    <d>_J_op, <d>_W, <d>_idle_W, <d>_J_op_active   for every energy domain d (short names below),
    primary_J_op, primary_W, primary_idle_W, primary_J_op_active, primary_domain,
    regime_flag, idle_mismatch, idle_unverified, freq_<class>_MHz (Intel, when present)
Mac only:
    mem_J_op (DRAM + AMCC + DCS), mem_W, mem_idle_W, mem_J_op_active, ecpu_share
"""
from __future__ import annotations

import csv
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import NO_P

PREFIX_PLATFORM = {"rapl": "intel", "ioreport": "mac"}
PRIMARY_DOMAIN = {"intel": "intel-rapl:0:package-0", "mac": "CPU_Energy"}
# Short, column-safe names for the domains we use most; anything else is sanitised.
DOMAIN_ALIAS = {
    "intel-rapl:0:package-0": "pkg",
    "intel-rapl:0:0:core": "core",
    "intel-rapl:0:1:uncore": "uncore",
    "intel-rapl:1:psys": "psys",
    "CPU_Energy": "cpu",
}
MEM_DOMAINS = ["DRAM", "AMCC", "DCS"]
REGIME_TOL = 0.10
WORKLOAD_ALIAS = {"IO": "SLEEP"}


def domain_column(domain: str) -> str:
    if domain in DOMAIN_ALIAS:
        return DOMAIN_ALIAS[domain]
    return re.sub(r"[^0-9a-zA-Z]+", "_", domain).strip("_").lower()


def _median(xs) -> float:
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and np.isnan(x))]
    return float(np.median(xs)) if xs else float("nan")


def _energy_prefix(secondary: dict) -> str | None:
    for key in secondary:
        pre = key.split(".", 1)[0]
        if pre in PREFIX_PLATFORM:
            return pre
    return None


def _domains(secondary: dict, prefix: str) -> list[str]:
    out = []
    for key in secondary:
        if key.startswith(prefix + ".") and key.endswith(".J_per_op"):
            out.append(key[len(prefix) + 1:-len(".J_per_op")])
    return sorted(out)


ENERGY_NAN_COLS = ["primary_J_op", "primary_W", "primary_idle_W", "primary_J_op_active"]
MAC_NAN_COLS = ["mem_J_op", "mem_W", "mem_idle_W", "mem_J_op_active", "ecpu_share"]


def _fork_metrics(bench: dict, fork: int, idle_watts: dict | None,
                  platform_hint: str | None = None) -> dict:
    """Per-fork values (medians over iterations) from one JMH benchmark entry.

    Without rapl.* / ioreport.* metrics (a --no-energy campaign) only time/op is filled and
    the energy columns are NaN; the platform then comes from `platform_hint`."""
    sec = bench.get("secondaryMetrics", {}) or {}
    prefix = _energy_prefix(sec)
    ms = bench["primaryMetric"]["rawData"][fork]
    row: dict = {"ms_op": _median(ms), "n_iter": len(ms)}
    if prefix is None:
        row["platform"] = platform_hint or "unknown"
        row["primary_domain"] = PRIMARY_DOMAIN.get(platform_hint, "")
        for c in ENERGY_NAN_COLS + (MAC_NAN_COLS if platform_hint == "mac" else []):
            row[c] = float("nan")
        row["regime_flag"] = False
        return row
    platform = PREFIX_PLATFORM[prefix]
    row["platform"] = platform
    window = sec.get(f"{prefix}.window_s", {}).get("rawData", [[]])[fork]
    idle_watts = idle_watts or {}
    per_iter_jop: dict[str, list[float]] = {}
    per_iter_j: dict[str, list[float]] = {}
    for d in _domains(sec, prefix):
        col = domain_column(d)
        jop = sec[f"{prefix}.{d}.J_per_op"]["rawData"][fork]
        j = sec.get(f"{prefix}.{d}.J", {}).get("rawData", [[]])[fork]
        per_iter_jop[d], per_iter_j[d] = jop, j
        row[f"{col}_J_op"] = _median(jop)
        if j and window and len(j) == len(window):
            row[f"{col}_W"] = _median([a / w if w else np.nan for a, w in zip(j, window)])
        else:
            row[f"{col}_W"] = float("nan")
        iw = idle_watts.get(d)
        row[f"{col}_idle_W"] = float(iw) if iw is not None else float("nan")
        row[f"{col}_J_op_active"] = row[f"{col}_J_op"] - row[f"{col}_idle_W"] * row["ms_op"] / 1000.0

    prim = PRIMARY_DOMAIN[platform]
    pc = domain_column(prim)
    row["primary_domain"] = prim
    for suffix in ("J_op", "W", "idle_W", "J_op_active"):
        row[f"primary_{suffix}"] = row.get(f"{pc}_{suffix}", float("nan"))
    pj = per_iter_j.get(prim) or []
    med = _median(pj)
    if not pj or not np.isfinite(med):
        row["regime_flag"] = False
    elif med == 0:
        row["regime_flag"] = bool(any(x != 0 for x in pj))
    else:
        row["regime_flag"] = bool(any(abs(x - med) / abs(med) > REGIME_TOL for x in pj))

    for key, val in sec.items():
        if key.startswith("freq."):
            name = "freq_" + re.sub(r"[^0-9a-zA-Z]+", "_", key[len("freq."):])
            row[name] = _median(val.get("rawData", [[]])[fork] if fork < len(val.get("rawData", [])) else [])

    if platform == "mac":
        if all(d in per_iter_jop for d in MEM_DOMAINS):
            sums = [sum(v) for v in zip(*(per_iter_jop[d] for d in MEM_DOMAINS))]
            row["mem_J_op"] = _median(sums)
            row["mem_W"] = sum(row[f"{domain_column(d)}_W"] for d in MEM_DOMAINS)
            row["mem_idle_W"] = sum(row[f"{domain_column(d)}_idle_W"] for d in MEM_DOMAINS)
            row["mem_J_op_active"] = row["mem_J_op"] - row["mem_idle_W"] * row["ms_op"] / 1000.0
        else:
            for c in ("mem_J_op", "mem_W", "mem_idle_W", "mem_J_op_active"):
                row[c] = float("nan")
        e, p = per_iter_j.get("ECPU"), per_iter_j.get("PCPU")
        if e and p:
            shares = [a / (a + b) if (a + b) > 0 else np.nan for a, b in zip(e, p)]
            row["ecpu_share"] = _median([s for s in shares if np.isfinite(s)])
        else:
            row["ecpu_share"] = float("nan")
    return row


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _as_bool(s) -> bool:
    return str(s).strip().lower() in {"true", "1", "yes", "y", "t"}


def _mismatch(batch_row: dict | None) -> bool:
    """True only when the batch's latest row says agree = False; empty agree (interrupted batch,
    no end baseline) is unknown and not treated as a mismatch."""
    if batch_row is None:
        return False
    v = str(batch_row.get("agree") or "").strip().lower()
    return v in {"false", "0", "no", "n", "f"}


def _unverified(batch_row: dict | None) -> bool:
    """True when the batch execution has no agree verdict (no end baseline, or no batches.csv
    row at all): the runner re-queues such runs once, so a remaining one is reported, not hidden."""
    return batch_row is None or str(batch_row.get("agree") or "").strip() == ""


def _int_or_na(s):
    s = "" if s is None else str(s).strip()
    if s == "" or s.lower() in {"none", "nan", "na"}:
        return pd.NA
    return int(float(s))


def _latest(rows: list[dict], key: str) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for i, r in enumerate(rows):
        try:
            att = int(float(r.get("attempt") or 0))
        except ValueError:
            att = 0
        k = r[key]
        cur = best.get(k)
        if cur is None or (att, i) >= (cur["_att"], cur["_i"]):
            best[k] = {**r, "_att": att, "_i": i}
    return best


def _idle_watts(batch_dir: Path) -> dict | None:
    for name in ("idle-start.json", "idle-end.json"):
        f = batch_dir / name
        if f.exists():
            try:
                with open(f) as fh:
                    return json.load(fh).get("watts")
            except (OSError, json.JSONDecodeError):
                continue
    return None


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df["p"] = df["p"].astype("Int64")
    for c in ("fork_index", "order"):
        if c in df.columns:
            df[c] = df[c].astype("Int64")
    for c in ("regime_flag", "idle_mismatch", "idle_unverified"):
        if c in df.columns:
            df[c] = df[c].astype(bool)
    lead = ["run_id", "platform", "campaign", "construct", "p", "workload", "restriction",
            "fork_index", "order", "batch", "seed", "n_iter", "ms_op", "primary_domain",
            "primary_J_op", "primary_W", "primary_idle_W", "primary_J_op_active",
            "regime_flag", "idle_mismatch", "idle_unverified"]
    lead = [c for c in lead if c in df.columns]
    return df[lead + [c for c in df.columns if c not in lead]]


def load_campaign(directory) -> pd.DataFrame:
    """Load results/<platform>/<campaign>/ into one row per run whose latest status is ok."""
    d = Path(directory)
    schedule = {r["run_id"]: r for r in _read_csv(d / "schedule.csv")}
    progress = _latest(_read_csv(d / "progress.csv"), "run_id") if (d / "progress.csv").exists() else {}
    batches = _latest(_read_csv(d / "batches.csv"), "batch") if (d / "batches.csv").exists() else {}
    dir_platform = d.parent.name if d.parent.name in ("intel", "mac") else None
    idle_cache: dict[str, dict | None] = {}
    rows = []
    for run_id, prog in progress.items():
        if prog.get("status", "").strip() != "ok":
            continue
        sch = schedule.get(run_id)
        if sch is None:
            warnings.warn(f"{run_id}: in progress.csv but not in schedule.csv; skipped")
            continue
        f = d / "runs" / f"{run_id}.json"
        if not f.exists():
            warnings.warn(f"{run_id}: status ok but {f} is missing; skipped")
            continue
        with open(f) as fh:
            data = json.load(fh)
        if not data:
            warnings.warn(f"{run_id}: empty JMH JSON; skipped")
            continue
        bench = data[0]
        strategy = bench.get("params", {}).get("strategy")
        if strategy and strategy != sch["construct"]:
            raise ValueError(f"{run_id}: JSON strategy {strategy} != schedule {sch['construct']}")
        # The idle baseline belongs to the batch EXECUTION of the latest ok row (e.g. b05-2),
        # not the planned batch in schedule.csv.
        batch = (prog.get("batch") or sch.get("batch") or "").strip()
        if batch not in idle_cache:
            idle_cache[batch] = _idle_watts(d / "batches" / batch)
        m = _fork_metrics(bench, 0, idle_cache[batch], dir_platform)
        if dir_platform and m["platform"] != dir_platform:
            warnings.warn(f"{run_id}: metric prefix says {m['platform']}, directory says {dir_platform}")
        b = batches.get(batch)
        construct = sch["construct"]
        rows.append({
            "run_id": run_id,
            "campaign": d.name,
            "construct": construct,
            "p": pd.NA if construct in NO_P else _int_or_na(sch.get("p")),
            "workload": WORKLOAD_ALIAS.get(sch["workload"], sch["workload"]),
            "restriction": sch.get("restriction", ""),
            "fork_index": _int_or_na(sch.get("fork_index")),
            "order": _int_or_na(sch.get("order")),
            "batch": batch,
            "seed": sch.get("seed", ""),
            "idle_mismatch": _mismatch(b),
            "idle_unverified": _unverified(b),
            **m,
        })
    return _finish(pd.DataFrame(rows))


def load_pilot(json_path, idle_json=None, platform: str | None = None) -> pd.DataFrame:
    """Load the A2 pilot layout: one JMH JSON, several forks per benchmark entry in rawData.

    workloadType IO is mapped to SLEEP; every fork becomes one run row with fork_index 1..n.
    """
    with open(json_path) as fh:
        data = json.load(fh)
    idle = None
    if idle_json:
        with open(idle_json) as fh:
            idle = json.load(fh).get("watts")
    restriction_default = {"intel": "unpinned", "mac": "DEFAULT"}
    rows = []
    order = 0
    for bench in data:
        params = bench.get("params", {})
        construct = params["strategy"]
        workload = WORKLOAD_ALIAS.get(params.get("workloadType"), params.get("workloadType"))
        p = pd.NA if construct in NO_P else _int_or_na(params.get("parallelism"))
        for k in range(len(bench["primaryMetric"]["rawData"])):
            order += 1
            m = _fork_metrics(bench, k, idle, platform)
            if platform and m["platform"] != platform:
                warnings.warn(f"--platform {platform} but metrics say {m['platform']}")
            plat = m["platform"]
            rows.append({
                "run_id": "-".join(["pilot", construct] + ([] if p is pd.NA else [str(p)]) + [workload, f"f{k + 1}"]),
                "campaign": Path(json_path).stem,
                "construct": construct,
                "p": p,
                "workload": workload,
                "restriction": restriction_default[plat],
                "fork_index": k + 1,
                "order": order,
                "batch": "pilot",
                "seed": "",
                "idle_mismatch": False,
                "idle_unverified": False,
                **m,
            })
    return _finish(pd.DataFrame(rows))
