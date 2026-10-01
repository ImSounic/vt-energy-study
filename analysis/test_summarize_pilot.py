import unittest

from summarize_pilot import summarise


def row(strategy, ms, jop, joules, window):
    return {
        "params": {"strategy": strategy, "workloadType": "IO", "parallelism": "8"},
        "primaryMetric": {"rawData": ms},
        "secondaryMetrics": {
            "ioreport.CPU_Energy.J_per_op": {"rawData": jop},
            "ioreport.CPU_Energy.J": {"rawData": joules},
            "ioreport.window_s": {"rawData": window},
        },
    }


class SummariseTest(unittest.TestCase):
    def test_fork_medians_power_and_idle_subtraction(self):
        r = row("VIRTUAL_THREADS",
                ms=[[10.0, 12.0, 11.0], [11.0, 11.0, 11.0]],
                jop=[[0.2, 0.2, 0.2], [0.4, 0.4, 0.4]],
                joules=[[5.0, 5.0, 5.0], [5.0, 5.0, 5.0]],
                window=[[5.0, 5.0, 5.0], [5.0, 5.0, 5.0]])
        (out,) = summarise([r], idle_watts=1.0)
        self.assertAlmostEqual(out["ms_per_op"], 11.0)
        self.assertAlmostEqual(out["J_per_op"], 0.3)
        self.assertAlmostEqual(out["W"], 1.0)
        self.assertAlmostEqual(out["J_per_op_active"], 0.3 - 1.0 * 0.011)


if __name__ == "__main__":
    unittest.main()
