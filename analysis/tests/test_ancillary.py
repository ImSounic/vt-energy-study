import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from vtenergy import ancillary

SAMPLE = """Machine model: Mac16,10
*** Sampled system activity (Thu Oct  1 15:27:47 2026 +0200) (1004.46ms elapsed) ***
**** Processor usage ****
E-Cluster HW active frequency: 2892 MHz
E-Cluster HW active residency:  99.50% (900 MHz: 6.1%)
P-Cluster HW active frequency: 0 MHz
P-Cluster HW active residency:   0.00% (912 MHz:  84%)
CPU Power: 1500 mW
**** Thermal pressure ****
Current pressure level: Nominal
*** Sampled system activity (Thu Oct  1 15:27:48 2026 +0200) (995.54ms elapsed) ***
E-Cluster HW active residency:  98.50% (900 MHz: 6.1%)
CPU Power: 2500 mW
"""
START = dt.datetime(2026, 10, 1, 15, 27, 47, tzinfo=dt.timezone(dt.timedelta(hours=2))).timestamp()


class PowermetricsTest(unittest.TestCase):
    def test_parse_samples(self):
        s = ancillary.parse_powermetrics(SAMPLE)
        self.assertEqual(len(s), 2)
        self.assertEqual(s[0]["cpu_mW"], 1500)
        self.assertAlmostEqual(s[0]["elapsed"], 1.00446)
        self.assertEqual(s[0]["e_residency"], 99.5)
        self.assertEqual(s[0]["p_residency"], 0.0)
        self.assertEqual(s[0]["e_MHz"], 2892)
        self.assertEqual(s[1]["end"] - s[0]["end"], 1.0)

    def test_window(self):
        s = ancillary.parse_powermetrics(SAMPLE)
        self.assertEqual(len(ancillary.window(s, START + 0.5, 0.2)), 1)


class Ax3Ax4Test(unittest.TestCase):
    def test_ax3_compares_ioreport_with_powermetrics(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "powermetrics.txt").write_text(SAMPLE)
            Path(d, "k1.json").write_text(json.dumps(
                {"threads": 1, "seconds": 1.0, "ops": 10, "start_epoch_ms": int(START * 1000),
                 "watts": {"CPU_Energy": 2.0}}))
            (row,) = ancillary.ax3(d)
        self.assertEqual(row["samples"], 2)
        self.assertAlmostEqual(row["powermetrics_W"], (1.5 * 1.00446 + 2.5 * 0.99554) / 2.0, places=6)
        self.assertAlmostEqual(row["ratio"], 2.0 / row["powermetrics_W"])

    def test_ax4_linear_fit(self):
        with tempfile.TemporaryDirectory() as d:
            for k in range(4):
                Path(d, f"k{k}.json").write_text(json.dumps(
                    {"threads": k, "seconds": 20.0, "ops": 100 * k, "start_epoch_ms": 0,
                     "watts": {"intel-rapl:0:package-0": 3.0 + 2.0 * k}}))
            rows = ancillary.ax4(d)
        self.assertEqual([r["threads"] for r in rows[:4]], [0, 1, 2, 3])
        self.assertIn("slope=2.0000", rows[-1]["W"])
        self.assertIn("R2=1.0000", rows[-1]["fit_W"])


if __name__ == "__main__":
    unittest.main()
