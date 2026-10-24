import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vtenergy import P_LEVELS, WORKLOADS  # noqa: E402
from vtenergy import hypotheses as H  # noqa: E402

FAST = H.Opts(n_boot=400, n_boot_eps=200)
CELLS = [("SEQUENTIAL", None), ("PLATFORM_THREADS", None)] + [
    (c, p) for c in ("FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS") for p in P_LEVELS]
JITTER = 0.002 * np.linspace(-1, 1, 10)  # the same 10 per-fork offsets in every cell


def synth(platform="mac", value=lambda c, p, w: 1.0, forks=10, restrictions=None, workloads=WORKLOADS):
    """One row per fork; every cell gets value * (1 + JITTER[fork]). Blocking measures positive."""
    restrictions = restrictions or [H.DEFAULT_RESTRICTION[platform]]
    rows, order = [], 0
    for r in restrictions:
        for w in workloads:
            for c, p in CELLS:
                v = value(c, p, w)
                for k in range(forks):
                    order += 1
                    x = v * (1 + JITTER[k % len(JITTER)])
                    rows.append({"run_id": f"{r}-{w}-{c}-{p}-{k}", "platform": platform, "campaign": "t",
                                 "construct": c, "p": p, "workload": w, "restriction": r,
                                 "fork_index": k + 1, "order": order, "ms_op": 100 * x,
                                 "primary_J_op": x, "primary_J_op_active": x, "mem_J_op": x,
                                 "mem_J_op_active": x, "ecpu_share": 0.3 * x, "regime_flag": False,
                                 "idle_mismatch": False})
    df = pd.DataFrame(rows)
    df["p"] = df["p"].astype("Int64")
    return df


def vt_lowest(c, p, w):
    return 0.5 if c == "VIRTUAL_THREADS" else 1.0 + 0.1 * P_LEVELS.index(p) if p else 1.0


class VTClearlyLowestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = synth("mac", vt_lowest)

    def test_h0_2_2_rejects_with_smallest_p(self):
        t = H.h0_2_2(self.df, opts=FAST)
        iu = t[t["test"] == "IU"]
        self.assertEqual(len(iu), 7 + 1 + 1)  # 7 p on CPU, p = 256 on SLEEP and SOCKET
        self.assertTrue((iu["decision"] == "reject").all())
        s = t[t["test"] == "IU smallest p"].set_index("workload")
        self.assertEqual(s.loc["CPU", "p"], 1)
        self.assertEqual(s.loc["SLEEP", "p"], 256)
        self.assertTrue((s["decision"] == "reject").all())
        comps = t[t["test"].str.startswith("MW one-sided")]
        self.assertTrue((comps["effect"] == -1.0).all())

    def test_holm_within_workload_for_iu(self):
        t = H.h0_2_2(self.df, opts=FAST)
        iu = t[(t["test"] == "IU") & (t["workload"] == "CPU")]
        np.testing.assert_allclose(iu["p_holm"], np.minimum(1, 7 * iu["p_raw"]), rtol=1e-9)
        iu_s = t[(t["test"] == "IU") & (t["workload"] == "SLEEP")]
        np.testing.assert_allclose(iu_s["p_holm"], iu_s["p_raw"])

    def test_main_and_h0_2_1_reject(self):
        m = H.main_family(self.df, opts=FAST)
        kw = m[m["test"] == "KW"]
        self.assertEqual(len(kw), 3)
        self.assertTrue((kw["decision"] == "reject").all())
        self.assertIn("SEQ | PT | FP_8 | FJ_8 | VT_8", kw["comparison"].iloc[0])
        self.assertEqual(m[m["test"] == "any workload"]["decision"].iloc[0], "reject")
        t = H.h0_2_1(self.df, opts=FAST)
        self.assertEqual((t["test"] == "KW").sum(), 21)
        dunn = t[t["test"] == "Dunn"]
        self.assertEqual(len(dunn), 21 * 4)
        self.assertTrue(dunn["comparison"].str.startswith("VT_").all())

    def test_main_uses_p16_on_intel(self):
        m = H.main_family(synth("intel", vt_lowest), opts=FAST)
        self.assertIn("VT_16", m[m["test"] == "KW"]["comparison"].iloc[0])

    def test_h0_1_2_split_mac(self):
        t = H.h0_1_2(self.df, opts=FAST)
        mw = t[t["test"] == "MW"]
        self.assertEqual(len(mw), 3)
        self.assertTrue(mw["comparison"].str.startswith("SEQ vs VT_").all())
        self.assertTrue((mw["decision"] == "reject").all())
        self.assertIn("n=5,5", mw["note"].iloc[0])

    def test_h0_1_2_intel_needs_confirm_then_uses_it(self):
        df = synth("intel", vt_lowest)
        t = H.h0_1_2(df, opts=FAST)
        self.assertTrue((t["decision"] == "skipped").all())
        cells = H.select_best_configs(df)
        self.assertEqual(len(cells), 6)
        self.assertEqual(set(cells["restriction"]), {"unpinned"})
        conf = df.merge(cells[["construct", "p", "workload"]], on=["construct", "p", "workload"])
        conf = conf[conf["fork_index"] <= 5]
        t = H.h0_1_2(df, confirm_df=conf, opts=FAST)
        mw = t[t["test"] == "MW"]
        self.assertEqual(len(mw), 3)
        self.assertTrue((mw["decision"] == "reject").all())
        self.assertIn("A3-D6", mw["note"].iloc[0])

    def test_select_best_cli_csv(self):
        from vtenergy.select_best import cells_csv
        text = cells_csv(synth("intel", vt_lowest))
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "construct,p,workload,restriction")
        self.assertIn("SEQUENTIAL,,CPU,unpinned", lines)
        self.assertIn("VIRTUAL_THREADS,1,CPU,unpinned", lines)

    def test_h0_1_3_spearman(self):
        t = H.h0_1_3(self.df, opts=FAST)
        self.assertEqual(t["test"].iloc[0], "Spearman")
        self.assertAlmostEqual(t["statistic"].iloc[0], 1.0)  # ms_op proportional to J/op
        self.assertIn("23 cells", t["note"].iloc[0])


class AllEqualTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        df = synth("mac", restrictions=["DEFAULT", "BACKGROUND"])
        exp2 = df["construct"].isin(["SEQUENTIAL", "PLATFORM_THREADS"]) | df["p"].isin([4, 16]).fillna(False)
        cls.df = df[(df["restriction"] == "DEFAULT") | exp2]
        cls.t = H.run_all(cls.df, opts=FAST)

    def test_nothing_rejects(self):
        self.assertFalse((self.t["decision"] == "reject").any(),
                         self.t[self.t["decision"] == "reject"][["family", "test", "comparison"]])

    def test_tost_reports_equivalence(self):
        tost = self.t[self.t["test"] == "TOST"]
        self.assertGreater(len(tost), 100)
        self.assertTrue((tost["decision"] == "equivalent").all())
        fams = set(tost["family"])
        self.assertTrue({"H0-1.1", "H0-1.2", "H0-2.1", "H0-3.1", "Memory"} <= fams, fams)

    def test_family_sizes_match_report_table(self):
        t = self.t
        self.assertEqual(((t["family"] == "H0-1.1") & (t["test"] == "KW across p")).sum(), 9)
        self.assertEqual(((t["family"] == "H0-3.1") & (t["test"] == "MW")).sum(), 24)
        self.assertEqual(((t["family"] == "H0-3.2") & (t["test"] == "KW")).sum(), 6)
        self.assertEqual(((t["family"] == "H0-1.2") & (t["test"] == "MW")).sum(), 3)
        mem = t[t["family"] == "Memory"]
        self.assertEqual(set(mem["workload"]), {"SLEEP", "SOCKET"})
        self.assertEqual((mem["test"] == "H0-1.1 KW across p").sum(), 6)
        self.assertEqual((mem["test"] == "H0-2.1 KW").sum(), 14)
        self.assertEqual((mem["test"] == "H0-2.2 IU").sum(), 2)

    def test_columns(self):
        self.assertEqual(list(self.t.columns), H.ROW_COLS)

    def test_time_penalty_zero(self):
        tp = self.t[self.t["test"] == "time penalty"]
        self.assertEqual(len(tp), 24)
        np.testing.assert_allclose(tp["effect"], 0.0, atol=1e-9)


class IntelPlacementTest(unittest.TestCase):
    def test_h0_3_1_intel_and_figures(self):
        import tempfile
        from vtenergy import figures
        df = synth("intel", restrictions=["unpinned", "2P", "2E", "2LPE"], forks=5)
        exp2 = df["construct"].isin(["SEQUENTIAL", "PLATFORM_THREADS"]) | df["p"].isin([4, 16]).fillna(False)
        df = df[(df["restriction"] == "unpinned") | exp2]
        t = H.h0_3_1(df, opts=FAST)
        self.assertEqual((t["test"] == "MW").sum(), 48)
        self.assertEqual((t["test"] == "descriptive").sum(), 24)
        self.assertTrue(t[t["test"] == "MW"]["comparison"].str.contains(" vs 2P").all())
        with tempfile.TemporaryDirectory() as out:
            made = figures.all_figures(df, "intel", out)
            self.assertEqual(sorted(p.name for p in made),
                             ["energy_vs_time_cpu.pdf", "lambda.pdf", "placement.pdf"])
            mac = synth("mac", restrictions=["DEFAULT", "BACKGROUND"], forks=3)
            mac["ecpu_J_op"], mac["pcpu_J_op"] = 0.3 * mac["primary_J_op"], 0.7 * mac["primary_J_op"]
            made = figures.all_figures(mac, "mac", out)
            self.assertIn("cluster_split.pdf", [p.name for p in made])


class RobustnessTest(unittest.TestCase):
    def test_missing_cells_are_skipped_not_crashing(self):
        df = synth("intel", workloads=["CPU"], forks=3)
        df = df[df["construct"].isin(["PLATFORM_THREADS", "VIRTUAL_THREADS"]) & df["p"].isin([8]).fillna(True)]
        t = H.run_all(df, opts=FAST)
        self.assertGreater((t["decision"] == "skipped").sum(), 10)
        self.assertTrue(t["note"].fillna("").str.len().gt(0)[t["decision"] == "skipped"].all())

    def test_empty_frame(self):
        df = synth("mac").iloc[0:0]
        t = H.run_all(df, platform="mac", opts=FAST)
        self.assertTrue(len(t) > 0)
        self.assertTrue(set(t["decision"]) <= {"skipped", "not rejected", ""})

    def test_floor_ratio(self):
        df = pd.DataFrame({"construct": ["FIXED_POOL", "SEQUENTIAL", "VIRTUAL_THREADS", "FORK_JOIN"],
                           "p": pd.array([8, pd.NA, 8, 256], dtype="Int64"),
                           "workload": ["SLEEP", "SOCKET", "SLEEP", "CPU"],
                           "ms_op": [330.0, 2560.0, 11.0, 5.0]})
        fr = H.floor_ratio(df, {"SLEEP": 10.0, "SOCKET": 10.0})
        self.assertAlmostEqual(fr.iloc[0], 330 / 320)
        self.assertAlmostEqual(fr.iloc[1], 1.0)
        self.assertTrue(np.isnan(fr.iloc[2]) and np.isnan(fr.iloc[3]))

    def test_blocking_detection_limit(self):
        df = synth("intel", workloads=["SLEEP"])
        vt = df["construct"] == "VIRTUAL_THREADS"
        df.loc[vt, "primary_J_op_active"] = np.tile(np.linspace(-0.01, 0.01, 10), vt.sum() // 10)
        t = H.blocking(df, opts=FAST)
        dl = t[t["test"] == "detection limit"].set_index("comparison")
        self.assertEqual(dl.loc["VT_256", "decision"], "below detection limit")
        self.assertEqual(dl.loc["PT", "decision"], "detected")
        self.assertEqual((t["test"] == "floor ratio").sum(), 7 + 7 + 1)

    def test_bdl_cells_skip_tost(self):
        df = synth("mac")
        vt = (df["construct"] == "VIRTUAL_THREADS") & (df["workload"] != "CPU")
        df.loc[vt, "primary_J_op_active"] = np.tile(np.linspace(-0.01, 0.01, 10), vt.sum() // 10)
        t = H.h0_1_1(df, opts=FAST)
        tost = t[(t["test"] == "TOST") & (t["workload"] == "SLEEP") & t["comparison"].str.startswith("VT_")]
        self.assertTrue(len(tost) > 0)
        self.assertTrue((tost["decision"] == "skipped").all())

    def test_ax7_detects_drift(self):
        df = synth("mac", workloads=["CPU"])
        df["order"] = np.random.default_rng(0).permutation(len(df)) + 1
        df["primary_J_op"] = df["primary_J_op"] * (1 + 1e-3 * df["order"])
        t = H.ax7_drift(df, opts=FAST)
        row = t[t["workload"] == "all"].iloc[0]
        self.assertGreater(row["statistic"], 0.5)
        self.assertEqual(row["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
