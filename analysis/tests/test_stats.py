import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vtenergy import stats as S  # noqa: E402


class CliffsDeltaTest(unittest.TestCase):
    def test_disjoint_samples_are_plus_minus_one(self):
        self.assertEqual(S.cliffs_delta([5, 6, 7], [1, 2, 3]), 1.0)
        self.assertEqual(S.cliffs_delta([1, 2, 3], [5, 6, 7]), -1.0)

    def test_identical_samples_are_zero(self):
        self.assertEqual(S.cliffs_delta([1, 2, 3], [1, 2, 3]), 0.0)

    def test_known_partial_overlap(self):
        # pairs: a=2 vs b={1,3}: +1,-1 ; a=4 vs b={1,3}: +1,+1  -> 2/4
        self.assertAlmostEqual(S.cliffs_delta([2, 4], [1, 3]), 0.5)

    def test_ci_brackets_estimate(self):
        rng = np.random.default_rng(1)
        a, b = rng.normal(1, 1, 20), rng.normal(0, 1, 20)
        d, lo, hi = S.cliffs_delta_ci(a, b, n_boot=2000)
        self.assertLessEqual(lo, d)
        self.assertGreaterEqual(hi, d)


class EpsilonSquaredTest(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(S.epsilon_squared(9.0, 10), 1.0)
        self.assertAlmostEqual(S.epsilon_squared(4.5, 10), 0.5)
        self.assertTrue(np.isnan(S.epsilon_squared(1.0, 1)))

    def test_ci_runs(self):
        e, lo, hi = S.epsilon_squared_ci([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]], n_boot=300)
        self.assertGreater(e, 0.8)
        self.assertTrue(lo <= hi)


class HolmTest(unittest.TestCase):
    def test_known_answer(self):
        np.testing.assert_allclose(S.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])

    def test_capped_and_monotone(self):
        adj = S.holm([0.5, 0.6, 0.001, 0.9])
        self.assertEqual(max(adj), 1.0)
        order = np.argsort([0.5, 0.6, 0.001, 0.9])
        self.assertTrue(np.all(np.diff(np.asarray(adj)[order]) >= 0))

    def test_nan_is_ignored(self):
        adj = S.holm([0.01, float("nan"), 0.02])
        self.assertTrue(np.isnan(adj[1]))
        np.testing.assert_allclose([adj[0], adj[2]], [0.02, 0.02])


class BootstrapTest(unittest.TestCase):
    def test_median_ci_of_constant_sample(self):
        lo, hi = S.bootstrap_ci(np.median, [3.0] * 10, n_boot=500)
        self.assertEqual((lo, hi), (3.0, 3.0))

    def test_vectorized_matches_loop(self):
        x = np.arange(12.0)
        a = S.bootstrap_ci(np.median, x, n_boot=500, seed=3)
        b = S.bootstrap_ci(lambda X: np.median(X, axis=1), x, n_boot=500, seed=3, vectorized=True)
        np.testing.assert_allclose(a, b)

    def test_deterministic_for_seed(self):
        x = np.random.default_rng(0).normal(size=15)
        self.assertEqual(S.bootstrap_ci(np.mean, x, n_boot=300, seed=7),
                         S.bootstrap_ci(np.mean, x, n_boot=300, seed=7))

    def test_ratio_of_medians(self):
        r, lo, hi = S.ratio_of_medians_ci([2.0, 2.0, 2.0], [1.0, 1.0, 1.0], n_boot=200)
        self.assertEqual((r, lo, hi), (2.0, 2.0, 2.0))


class TostTest(unittest.TestCase):
    def setUp(self):
        self.base = 1.0 + 0.001 * np.linspace(-1, 1, 10)

    def test_identical_tight_samples_are_equivalent(self):
        t = S.tost_ratio(self.base, self.base.copy())
        self.assertTrue(t["equivalent"])
        self.assertAlmostEqual(t["ratio"], 1.0)

    def test_twenty_percent_shift_is_not_equivalent(self):
        t = S.tost_ratio(self.base * 1.2, self.base)
        self.assertFalse(t["equivalent"])
        self.assertAlmostEqual(t["ratio"], 1.2, places=6)

    def test_wide_samples_are_not_equivalent(self):
        rng = np.random.default_rng(0)
        t = S.tost_ratio(rng.normal(1, 0.3, 10), rng.normal(1, 0.3, 10))
        self.assertFalse(t["equivalent"])


class DetectionLimitTest(unittest.TestCase):
    def test_noise_around_zero_is_below_limit(self):
        self.assertTrue(S.below_detection_limit([-0.02, 0.01, -0.01, 0.02, 0.0, 0.015, -0.015]))

    def test_clearly_positive_is_detected(self):
        self.assertFalse(S.below_detection_limit([1.0, 1.1, 0.9, 1.05, 0.95]))


class TestsTest(unittest.TestCase):
    def test_kruskal_separated_and_tied(self):
        H, p = S.kruskal([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        self.assertLess(p, 0.05)
        self.assertEqual(S.kruskal([[1, 1], [1, 1]]), (0.0, 1.0))
        self.assertTrue(np.isnan(S.kruskal([[1, 2, 3], []])[1]))

    def test_mann_whitney_exact_minimum(self):
        U, p = S.mann_whitney([1, 2, 3, 4, 5], [6, 7, 8, 9, 10], "less")
        self.assertEqual(U, 0.0)
        self.assertAlmostEqual(p, 1 / 252)
        _, p2 = S.mann_whitney([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
        self.assertAlmostEqual(p2, 2 / 252)

    def test_mann_whitney_two_vs_three_cannot_reject(self):
        # A3-D6: with a 2 vs 3 split the minimum two-sided p is 0.2
        _, p = S.mann_whitney([1, 2], [3, 4, 5])
        self.assertAlmostEqual(p, 0.2)

    def test_spearman(self):
        rho, p = S.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        self.assertAlmostEqual(rho, 1.0)
        self.assertTrue(np.isnan(S.spearman([1, 1, 1], [1, 2, 3])[0]))

    def test_dunn_holm_matrix(self):
        df = pd.DataFrame({"v": list(range(1, 6)) + list(range(11, 16)) + list(range(21, 26)),
                           "g": ["a"] * 5 + ["b"] * 5 + ["c"] * 5})
        m = S.dunn(df, "v", "g")
        self.assertEqual(sorted(m.index), ["a", "b", "c"])
        self.assertLess(m.loc["a", "c"], 0.05)
        raw = S.dunn(df, "v", "g", p_adjust=None)
        self.assertLessEqual(raw.loc["a", "b"], m.loc["a", "b"])


class PowerTest(unittest.TestCase):
    def test_power_increases_with_n(self):
        p5 = S.mw_power(0.10, 5, sims=1000)
        p10 = S.mw_power(0.10, 10, sims=1000)
        p20 = S.mw_power(0.10, 20, sims=1000)
        self.assertLess(p5, p10)
        self.assertLess(p10, p20)

    def test_tiny_cv_gives_full_power_and_huge_cv_low_power(self):
        self.assertEqual(S.mw_power(0.005, 10, sims=500), 1.0)
        self.assertLess(S.mw_power(2.0, 10, sims=500), 0.2)


class CellSummaryTest(unittest.TestCase):
    def test_summary_values(self):
        df = pd.DataFrame({"construct": ["A"] * 4 + ["B"] * 2, "v": [1.0, 2.0, 3.0, 4.0, 5.0, 5.0]})
        s = S.cell_summary(df, "v", by=["construct"]).set_index("construct")
        self.assertEqual(s.loc["A", "median"], 2.5)
        self.assertEqual(s.loc["A", "iqr"], 1.5)
        self.assertAlmostEqual(s.loc["A", "cv"], np.std([1, 2, 3, 4], ddof=1) / 2.5)
        self.assertEqual(s.loc["A", "n"], 4)
        self.assertEqual(s.loc["B", "cv"], 0.0)


if __name__ == "__main__":
    unittest.main()
