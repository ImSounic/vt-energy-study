import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vtenergy.load import load_campaign, load_pilot  # noqa: E402

REPO = ROOT.parent


def _metric(vals):
    return {"rawData": [list(vals)]}


def mac_run(strategy, workload, ms, cpu_j, ecpu_j, pcpu_j, mem_j, window=5.0, ops=None):
    """One-fork JMH entry with ioreport metrics. ms: 5 ms/op values; *_j: 5 J per iteration."""
    ops = ops or [window * 1000 / m for m in ms]
    sec = {"ioreport.window_s": _metric([window] * 5)}

    def add(dom, joules):
        sec[f"ioreport.{dom}.J"] = _metric(joules)
        sec[f"ioreport.{dom}.J_per_op"] = _metric([j / o for j, o in zip(joules, ops)])

    add("CPU_Energy", cpu_j)
    add("ECPU", ecpu_j)
    add("PCPU", pcpu_j)
    for dom in ("DRAM", "AMCC", "DCS"):
        add(dom, mem_j)
    add("GPU", [0.0] * 5)
    return [{"params": {"strategy": strategy, "parallelism": "8", "workloadType": workload},
             "primaryMetric": {"rawData": [list(ms)], "scoreUnit": "ms/op"},
             "secondaryMetrics": sec}]


def _dump(obj, fh):
    with fh:
        json.dump(obj, fh)


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


class LoadCampaignTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "results" / "mac" / "main"
        (self.dir / "runs").mkdir(parents=True)
        write_csv(self.dir / "schedule.csv",
                  ["run_id", "order", "batch", "construct", "p", "workload", "restriction", "fork_index", "seed"],
                  [["r0001", 1, "b01", "VIRTUAL_THREADS", 8, "SLEEP", "DEFAULT", 1, 42],
                   ["r0002", 2, "b01", "PLATFORM_THREADS", "", "CPU", "DEFAULT", 3, 42],
                   ["r0003", 3, "b01", "FIXED_POOL", 4, "CPU", "BACKGROUND", 2, 42],
                   ["r0004", 4, "b01", "FORK_JOIN", 16, "CPU", "DEFAULT", 1, 42]])
        # r0001: failed then ok in the re-run batch b01-2; r0002 ok in b01; r0003 failed only;
        # r0004 ok then discarded -> not loaded.
        write_csv(self.dir / "progress.csv",
                  ["run_id", "attempt", "status", "batch", "start_utc", "end_utc", "exit_code"],
                  [["r0001", 1, "failed", "b01", "", "", 1],
                   ["r0002", 1, "ok", "b01", "", "", 0],
                   ["r0003", 1, "failed", "b01", "", "", 1],
                   ["r0004", 1, "ok", "b01", "", "", 0],
                   ["r0004", 2, "discarded", "b01", "", "", ""],
                   ["r0001", 2, "ok", "b01-2", "", "", 0]])
        write_csv(self.dir / "batches.csv",
                  ["batch", "attempt", "primary_domain", "idle_start_W", "idle_end_W", "agree"],
                  [["b01", 1, "CPU_Energy", 0.03, 0.03, "True"],
                   ["b01-2", 1, "CPU_Energy", 0.02, 0.05, "False"]])
        idle1 = {"CPU_Energy": 0.02, "ECPU": 0.015, "PCPU": 0.005, "DRAM": 0.05, "AMCC": 0.1, "DCS": 0.02}
        idle2 = {k: v * 2 for k, v in idle1.items()}
        for b, w in (("b01", idle1), ("b01-2", idle2)):
            (self.dir / "batches" / b).mkdir(parents=True)
        # b01 has only an end baseline (fallback); b01-2 has a start baseline.
        _dump({"seconds": 60.0, "watts": idle1, "frozen": []}, open(self.dir / "batches/b01/idle-end.json", "w"))
        _dump({"seconds": 60.0, "watts": idle2, "frozen": []}, open(self.dir / "batches/b01-2/idle-start.json", "w"))
        # r0001: one iteration of CPU J deviates by 50 % -> regime flag
        _dump(mac_run("VIRTUAL_THREADS", "SLEEP", [12, 12, 13, 12, 12], [1, 1, 1.5, 1, 1],
                          [0.75, 0.75, 1.0, 0.75, 0.75], [0.25, 0.25, 0.5, 0.25, 0.25], [0.2] * 5),
                  open(self.dir / "runs/r0001.json", "w"))
        _dump(mac_run("PLATFORM_THREADS", "CPU", [150, 151, 149, 150, 152], [55, 56, 55, 54, 55],
                          [5, 5, 5, 5, 5], [50, 51, 50, 49, 50], [1.0] * 5),
                  open(self.dir / "runs/r0002.json", "w"))
        _dump(mac_run("FORK_JOIN", "CPU", [150] * 5, [55] * 5, [5] * 5, [50] * 5, [1.0] * 5),
                  open(self.dir / "runs/r0004.json", "w"))
        self.df = load_campaign(self.dir).set_index("run_id")

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_latest_ok_runs(self):
        self.assertEqual(sorted(self.df.index), ["r0001", "r0002"])

    def test_metadata(self):
        r = self.df.loc["r0001"]
        self.assertEqual(r["platform"], "mac")
        self.assertEqual(r["campaign"], "main")
        self.assertEqual(r["construct"], "VIRTUAL_THREADS")
        self.assertEqual(r["p"], 8)
        self.assertEqual(r["batch"], "b01-2")
        self.assertEqual(r["fork_index"], 1)
        self.assertTrue(pd.isna(self.df.loc["r0002", "p"]))
        self.assertEqual(str(self.df["p"].dtype), "Int64")

    def test_medians_power_and_idle(self):
        r = self.df.loc["r0002"]
        self.assertEqual(r["ms_op"], 150)
        ops = [5000 / m for m in [150, 151, 149, 150, 152]]
        self.assertAlmostEqual(r["cpu_J_op"], np.median([j / o for j, o in zip([55, 56, 55, 54, 55], ops)]))
        self.assertAlmostEqual(r["primary_J_op"], r["cpu_J_op"])
        self.assertAlmostEqual(r["primary_W"], 11.0)
        self.assertAlmostEqual(r["primary_idle_W"], 0.02)  # end baseline fallback in b01
        self.assertAlmostEqual(r["primary_J_op_active"], r["primary_J_op"] - 0.02 * 0.150)
        self.assertAlmostEqual(r["ecpu_share"], 5 / 55, places=3)
        self.assertFalse(r["regime_flag"])
        self.assertFalse(r["idle_mismatch"])

    def test_mac_memory_columns_and_flags(self):
        r = self.df.loc["r0001"]
        self.assertAlmostEqual(r["primary_idle_W"], 0.04)  # b01-2 start baseline
        ops = 5000 / 12
        self.assertAlmostEqual(r["mem_J_op"], 3 * 0.2 / ops)
        self.assertAlmostEqual(r["mem_idle_W"], 2 * (0.05 + 0.1 + 0.02))
        self.assertAlmostEqual(r["mem_J_op_active"], r["mem_J_op"] - r["mem_idle_W"] * 0.012)
        self.assertTrue(r["regime_flag"])
        self.assertTrue(r["idle_mismatch"])
        for c in ("ecpu_J_op", "pcpu_J_op", "dram_J_op", "amcc_J_op", "dcs_J_op", "gpu_J_op", "cpu_W"):
            self.assertIn(c, self.df.columns)

    def test_empty_agree_is_not_a_mismatch(self):
        write_csv(self.dir / "batches.csv",
                  ["batch", "attempt", "primary_domain", "idle_start_W", "idle_end_W", "agree"],
                  [["b01", 1, "CPU_Energy", 0.03, "", ""], ["b01-2", 1, "CPU_Energy", 0.02, "", ""]])
        df = load_campaign(self.dir)
        self.assertFalse(df["idle_mismatch"].any())


class LoadIntelAndNoEnergyTest(unittest.TestCase):
    def test_intel_rapl_freq_and_no_energy(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "intel" / "smoke"
            (d / "runs").mkdir(parents=True)
            write_csv(d / "schedule.csv",
                      ["run_id", "order", "batch", "construct", "p", "workload", "restriction", "fork_index", "seed"],
                      [["a", 1, "b01", "SEQUENTIAL", "", "CPU", "2E", 1, 1],
                       ["b", 2, "b01", "VIRTUAL_THREADS", 4, "SOCKET", "unpinned", 1, 1]])
            write_csv(d / "progress.csv", ["run_id", "attempt", "status", "batch", "start_utc", "end_utc", "exit_code"],
                      [["a", 1, "ok", "b01", "", "", 0], ["b", 1, "ok", "b01", "", "", 0]])
            sec = {"rapl.window_s": _metric([5] * 5),
                   "freq.P_MHz": _metric([4000, 4100, 4000, 3900, 4000])}
            for dom, j in (("intel-rapl:0:package-0", 50), ("intel-rapl:0:0:core", 40),
                           ("intel-rapl:0:1:uncore", 1), ("intel-rapl:1:psys", 80)):
                sec[f"rapl.{dom}.J"] = _metric([j] * 5)
                sec[f"rapl.{dom}.J_per_op"] = _metric([j / 20] * 5)
            _dump([{"params": {"strategy": "SEQUENTIAL", "parallelism": "1", "workloadType": "CPU"},
                        "primaryMetric": {"rawData": [[250] * 5]}, "secondaryMetrics": sec}],
                      open(d / "runs/a.json", "w"))
            _dump([{"params": {"strategy": "VIRTUAL_THREADS", "parallelism": "4", "workloadType": "SOCKET"},
                        "primaryMetric": {"rawData": [[12] * 5]}, "secondaryMetrics": {}}],
                      open(d / "runs/b.json", "w"))
            df = load_campaign(d).set_index("run_id")
            a = df.loc["a"]
            self.assertEqual(a["platform"], "intel")
            self.assertAlmostEqual(a["pkg_J_op"], 2.5)
            self.assertAlmostEqual(a["primary_J_op"], 2.5)
            self.assertAlmostEqual(a["primary_W"], 10.0)
            self.assertTrue(np.isnan(a["primary_idle_W"]))  # no idle files
            self.assertEqual(a["freq_P_MHz"], 4000)
            self.assertEqual(a["restriction"], "2E")
            b = df.loc["b"]
            self.assertEqual(b["platform"], "intel")  # from the directory, no energy keys
            self.assertEqual(b["ms_op"], 12)
            self.assertTrue(np.isnan(b["primary_J_op"]))


class LoadPilotTest(unittest.TestCase):
    def test_intel_pilot(self):
        f = REPO / "results" / "pilot-intel" / "pilot.json"
        if not f.exists():
            self.skipTest("pilot data absent")
        df = load_pilot(f, REPO / "results" / "pilot-intel" / "idle-start.json", "intel")
        self.assertEqual(len(df), 24)
        self.assertEqual(set(df["workload"]), {"CPU", "SLEEP"})
        self.assertEqual(set(df["fork_index"]), {1, 2, 3})
        self.assertTrue(df.loc[df["construct"] == "PLATFORM_THREADS", "p"].isna().all())
        self.assertAlmostEqual(df["primary_idle_W"].iloc[0], 3.646894)
        pt = df[(df["construct"] == "PLATFORM_THREADS") & (df["workload"] == "CPU")]
        self.assertAlmostEqual(pt["primary_J_op"].median(), 2.338, places=2)  # report Table "pilot"


if __name__ == "__main__":
    unittest.main()
