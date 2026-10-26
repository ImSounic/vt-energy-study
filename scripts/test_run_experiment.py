"""Unit tests for the pure parts of run_experiment.py (standard library only).

Run: python3 -m unittest discover -s scripts -p 'test_run_experiment.py' -v
"""
import collections
import tempfile
import unittest
from pathlib import Path

import run_experiment as rx


class CellsTest(unittest.TestCase):
    def test_full_intel_has_141_cells(self):
        cells = rx.cells("intel", "full")
        self.assertEqual(len(cells), 141)
        self.assertEqual(len(set(cells)), 141)
        by_restriction = collections.Counter(c.restriction for c in cells)
        self.assertEqual(by_restriction, {"unpinned": 69, "2P": 24, "2E": 24, "2LPE": 24})

    def test_full_mac_has_93_cells(self):
        cells = rx.cells("mac", "full")
        self.assertEqual(len(cells), 93)
        by_restriction = collections.Counter(c.restriction for c in cells)
        self.assertEqual(by_restriction, {"DEFAULT": 69, "BACKGROUND": 24})

    def test_experiment1_has_23_cells_per_workload(self):
        cells = [c for c in rx.cells("mac", "full") if c.restriction == "DEFAULT"]
        per_workload = collections.Counter(c.workload for c in cells)
        self.assertEqual(per_workload, {"CPU": 23, "SLEEP": 23, "SOCKET": 23})

    def test_experiment2_cells(self):
        cells = [c for c in rx.cells("mac", "full") if c.restriction == "BACKGROUND" and c.workload == "CPU"]
        self.assertEqual(sorted((c.construct, c.p) for c in cells), sorted([
            ("SEQUENTIAL", None), ("PLATFORM_THREADS", None),
            ("FIXED_POOL", 4), ("FIXED_POOL", 16), ("FORK_JOIN", 4), ("FORK_JOIN", 16),
            ("VIRTUAL_THREADS", 4), ("VIRTUAL_THREADS", 16)]))

    def test_seq_and_pt_have_no_concurrency_level(self):
        for c in rx.cells("intel", "full"):
            if c.construct in ("SEQUENTIAL", "PLATFORM_THREADS"):
                self.assertIsNone(c.p)
            else:
                self.assertIn(c.p, rx.LEVELS)

    def test_cells_file_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cells.csv"
            path.write_text("construct,p,workload,restriction\n"
                            "SEQUENTIAL,,CPU,unpinned\nFIXED_POOL,16,SLEEP,unpinned\n")
            self.assertEqual(rx.cells_from_file(path), [
                rx.Cell("SEQUENTIAL", None, "CPU", "unpinned"),
                rx.Cell("FIXED_POOL", 16, "SLEEP", "unpinned")])

    def test_cells_file_accepts_the_persistent_controls(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cells.csv"
            path.write_text("construct,p,workload,restriction\n"
                            "FIXED_POOL_PERSISTENT,256,SLEEP,DEFAULT\nFORK_JOIN_PERSISTENT,16,SOCKET,DEFAULT\n")
            self.assertEqual(rx.cells_from_file(path), [
                rx.Cell("FIXED_POOL_PERSISTENT", 256, "SLEEP", "DEFAULT"),
                rx.Cell("FORK_JOIN_PERSISTENT", 16, "SOCKET", "DEFAULT")])

    def test_cells_file_rejects_bad_cells(self):
        for row in ["FIXED_POOL_PERSISTANT,16,CPU,DEFAULT", "FORK_JOIN_PERSISTENT,,CPU,DEFAULT",
                    "SEQUENTIAL,4,CPU,DEFAULT", "FIXED_POOL,16,IDLE,DEFAULT", "FIXED_POOL,16,mixed,DEFAULT"]:
            with tempfile.TemporaryDirectory() as d, self.subTest(row=row):
                path = Path(d) / "cells.csv"
                path.write_text("construct,p,workload,restriction\n" + row + "\n")
                with self.assertRaises(ValueError):
                    rx.cells_from_file(path)

    def test_control_cells_file(self):
        cells = rx.cells_from_file(rx.REPO / "results" / "mac" / "control-cells.csv")
        self.assertEqual(len(cells), 28)
        self.assertEqual(len(set(cells)), 28)
        self.assertTrue(all(c.restriction == "DEFAULT" for c in cells))
        by_construct = collections.Counter((c.construct, c.p) for c in cells if c.workload != "MIXED")
        self.assertEqual(by_construct, {
            ("FIXED_POOL_PERSISTENT", 16): 3, ("FIXED_POOL_PERSISTENT", 256): 3,
            ("FORK_JOIN_PERSISTENT", 16): 3, ("FORK_JOIN_PERSISTENT", 256): 3,
            ("FIXED_POOL", 256): 3, ("FORK_JOIN", 256): 3, ("VIRTUAL_THREADS", 256): 3})
        self.assertEqual(sorted((c.construct, c.p) for c in cells if c.workload == "MIXED"), sorted([
            ("VIRTUAL_THREADS", 256), ("VIRTUAL_THREADS", 16), ("PLATFORM_THREADS", None),
            ("FIXED_POOL", 256), ("FORK_JOIN", 256),
            ("FIXED_POOL_PERSISTENT", 256), ("FORK_JOIN_PERSISTENT", 256)]))

    def test_mixed_op_time_has_burst_and_wait(self):
        burst, wait = rx.MIXED_BURST_S["mac"], rx.SLEEP_D_S["mac"]
        self.assertAlmostEqual(rx.op_seconds(rx.Cell("FIXED_POOL", 256, "MIXED", "DEFAULT"), "mac"),
                               max(256 * burst / 10, burst + wait))
        self.assertAlmostEqual(rx.op_seconds(rx.Cell("FIXED_POOL", 16, "MIXED", "DEFAULT"), "mac"),
                               16 * (burst + wait))


class ScheduleTest(unittest.TestCase):
    def test_intel_full_has_705_runs_in_batches_of_at_most_40(self):
        runs = rx.schedule(rx.cells("intel", "full"), forks=5, seed=1)
        self.assertEqual(len(runs), 705)
        sizes = collections.Counter(r.batch for r in runs)
        self.assertEqual(len(sizes), 18)
        self.assertTrue(all(n <= 40 for n in sizes.values()))

    def test_every_cell_gets_fork_indices_1_to_n(self):
        runs = rx.schedule(rx.cells("mac", "full"), forks=10, seed=7)
        self.assertEqual(len(runs), 930)
        forks = collections.defaultdict(list)
        for r in runs:
            forks[r.cell].append(r.fork_index)
        self.assertTrue(all(sorted(v) == list(range(1, 11)) for v in forks.values()))

    def test_shuffle_is_seeded_and_random(self):
        cells = rx.cells("intel", "full")
        a = rx.schedule(cells, forks=5, seed=42)
        b = rx.schedule(cells, forks=5, seed=42)
        c = rx.schedule(cells, forks=5, seed=43)
        self.assertEqual(a, b)
        self.assertNotEqual([r.cell for r in a], [r.cell for r in c])
        # not in cell order: the first 10 runs come from more than one cell
        self.assertGreater(len({r.cell for r in a[:10]}), 1)

    def test_run_ids_are_unique_and_ordered(self):
        runs = rx.schedule(rx.cells("intel", "full"), forks=5, seed=1)
        self.assertEqual(len({r.run_id for r in runs}), len(runs))
        self.assertEqual([r.order for r in runs], list(range(len(runs))))
        self.assertTrue(runs[0].run_id.startswith("0000_"))

    def test_schedule_csv_round_trip(self):
        runs = rx.schedule(rx.cells("intel", "pilot"), forks=3, seed=5)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "schedule.csv"
            rx.write_schedule(path, runs, seed=5)
            self.assertEqual(rx.read_schedule(path), runs)


class TopologyTest(unittest.TestCase):
    def test_expand_ranges(self):
        self.assertEqual(rx.expand_cpus("0-3,5,14-15"), [0, 1, 2, 3, 5, 14, 15])
        self.assertEqual(rx.expand_cpus(""), [])

    def test_pinned_arms_take_first_two_cores_of_each_class(self):
        arms = rx.pinned_arms("0-5", "6-13", "14-15")
        self.assertEqual(arms, {"2P": "0,1", "2E": "6,7", "2LPE": "14,15"})

    def test_server_core_is_last_e_core(self):
        self.assertEqual(rx.server_core("6-13"), "13")


class JmhCommandTest(unittest.TestCase):
    CTX = dict(java="/jdk/bin/java", jar="/repo/benchmarks.jar", out_json="/out/r.json",
               socket_port=47000, arms={"2P": "0,1", "2E": "6,7", "2LPE": "14,15"})

    def cmd(self, cell, platform="intel", **kw):
        ctx = dict(self.CTX, **kw)
        return rx.jmh_command(cell, platform, **ctx)

    def value_after(self, argv, flag):
        return argv[argv.index(flag) + 1]

    def test_vt_sets_carriers_with_jvm_args_append(self):
        argv = self.cmd(rx.Cell("VIRTUAL_THREADS", 8, "SLEEP", "unpinned"))
        self.assertNotIn("-jvmArgs", argv)
        self.assertEqual(self.value_after(argv, "-jvmArgsAppend"),
                         "-Djdk.virtualThreadScheduler.parallelism=8 -Djdk.virtualThreadScheduler.maxPoolSize=8")
        self.assertIn("parallelism=8", argv)

    def test_socket_passes_port_merged_with_carriers(self):
        argv = self.cmd(rx.Cell("VIRTUAL_THREADS", 4, "SOCKET", "unpinned"))
        self.assertEqual(self.value_after(argv, "-jvmArgsAppend"),
                         "-Djdk.virtualThreadScheduler.parallelism=4 -Djdk.virtualThreadScheduler.maxPoolSize=4"
                         " -Dvtenergy.socket.port=47000")

    def test_seq_runs_with_placeholder_parallelism_and_no_jvm_args(self):
        argv = self.cmd(rx.Cell("SEQUENTIAL", None, "SLEEP", "unpinned"))
        self.assertIn("parallelism=1", argv)
        self.assertNotIn("-jvmArgsAppend", argv)

    def test_intel_cpu_heat_soaks_for_60_s(self):
        argv = self.cmd(rx.Cell("FIXED_POOL", 16, "CPU", "unpinned"))
        self.assertEqual((self.value_after(argv, "-wi"), self.value_after(argv, "-w")), ("12", "5s"))

    def test_other_cells_warm_up_5_x_1_s(self):
        for cell, platform in [(rx.Cell("FIXED_POOL", 16, "SLEEP", "unpinned"), "intel"),
                               (rx.Cell("FIXED_POOL", 16, "CPU", "DEFAULT"), "mac")]:
            argv = self.cmd(cell, platform)
            self.assertEqual((self.value_after(argv, "-wi"), self.value_after(argv, "-w")), ("5", "1s"))

    def test_measurement_settings(self):
        argv = self.cmd(rx.Cell("FORK_JOIN", 2, "SOCKET", "unpinned"))
        for flag, value in [("-f", "1"), ("-i", "5"), ("-r", "5s"), ("-rf", "json"), ("-rff", "/out/r.json")]:
            self.assertEqual(self.value_after(argv, flag), value)

    def test_profilers(self):
        self.assertEqual(self.value_after(self.cmd(rx.Cell("SEQUENTIAL", None, "CPU", "unpinned")), "-prof"),
                         "nl.utwente.gsd.energy.RaplProfiler")
        self.assertEqual(self.value_after(self.cmd(rx.Cell("SEQUENTIAL", None, "CPU", "DEFAULT"), "mac"), "-prof"),
                         "nl.utwente.gsd.energy.IoReportProfiler")
        self.assertNotIn("-prof", self.cmd(rx.Cell("SEQUENTIAL", None, "CPU", "unpinned"), mode="none"))
        argv = self.cmd(rx.Cell("SEQUENTIAL", None, "CPU", "unpinned"), mode="profile", profile_dir="/out/jfr")
        self.assertEqual(self.value_after(argv, "-prof"), "jfr:dir=/out/jfr")

    def test_intel_pinning_wraps_with_taskset(self):
        argv = self.cmd(rx.Cell("VIRTUAL_THREADS", 4, "CPU", "2E"))
        self.assertEqual(argv[:3], ["taskset", "-c", "6,7"])
        self.assertEqual(argv[3], "/jdk/bin/java")
        self.assertEqual(self.cmd(rx.Cell("VIRTUAL_THREADS", 4, "CPU", "unpinned"))[0], "/jdk/bin/java")

    def test_persistent_control_passes_its_strategy_and_no_carrier_flags(self):
        argv = self.cmd(rx.Cell("FORK_JOIN_PERSISTENT", 256, "SLEEP", "DEFAULT"), "mac")
        self.assertIn("strategy=FORK_JOIN_PERSISTENT", argv)
        self.assertIn("parallelism=256", argv)
        self.assertIn("workloadType=SLEEP", argv)
        self.assertNotIn("-jvmArgsAppend", argv)
        self.assertEqual(self.value_after(argv, "-prof"), "nl.utwente.gsd.energy.IoReportProfiler")
        argv = self.cmd(rx.Cell("FIXED_POOL_PERSISTENT", 16, "SOCKET", "DEFAULT"), "mac")
        self.assertEqual(self.value_after(argv, "-jvmArgsAppend"), "-Dvtenergy.socket.port=47000")

    def test_mixed_passes_its_workload_and_needs_no_server(self):
        argv = self.cmd(rx.Cell("FIXED_POOL_PERSISTENT", 256, "MIXED", "DEFAULT"), "mac")
        self.assertIn("workloadType=MIXED", argv)
        self.assertNotIn("-jvmArgsAppend", argv)

    def test_mac_background_uses_taskpolicy_wrapper(self):
        argv = self.cmd(rx.Cell("FIXED_POOL", 4, "CPU", "BACKGROUND"), "mac")
        self.assertTrue(self.value_after(argv, "-jvm").endswith("scripts/mac/bg-java.sh"))
        self.assertNotIn("-jvm", self.cmd(rx.Cell("FIXED_POOL", 4, "CPU", "DEFAULT"), "mac"))


class IdleAgreementTest(unittest.TestCase):
    def test_relative_tolerance(self):
        self.assertTrue(rx.idle_agrees(3.65, 3.70, rel=0.10, abs_=0.0))
        self.assertFalse(rx.idle_agrees(3.65, 14.99, rel=0.10, abs_=0.0))

    def test_absolute_floor_for_mac(self):
        self.assertTrue(rx.idle_agrees(0.0296, 0.0202, rel=0.10, abs_=0.010))
        self.assertFalse(rx.idle_agrees(0.0296, 0.0202, rel=0.10, abs_=0.0))
        self.assertFalse(rx.idle_agrees(0.020, 0.184, rel=0.10, abs_=0.010))


class ProgressTest(unittest.TestCase):
    def test_latest_status_wins(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "progress.csv"
            rx.append_progress(path, dict(run_id="a", attempt=1, status="failed", batch="b01"))
            rx.append_progress(path, dict(run_id="a", attempt=2, status="ok", batch="b01-2"))
            rx.append_progress(path, dict(run_id="b", attempt=1, status="ok", batch="b01"))
            rx.append_progress(path, dict(run_id="b", attempt=2, status="discarded", batch="b01"))
            self.assertEqual(rx.latest_status(path), {"a": ("ok", 2), "b": ("discarded", 2)})

    def test_missing_progress_file_means_nothing_done(self):
        self.assertEqual(rx.latest_status(Path("/nonexistent/progress.csv")), {})


class RequeueTest(unittest.TestCase):
    def history(self, *rows):
        h = {}
        for run_id, status, attempt, batch in rows:
            h.setdefault(run_id, []).append((status, attempt, batch))
        return h

    def test_runs_of_disagreeing_or_unverified_batches_are_requeued(self):
        batches = [{"batch": "b01", "agree": "True"}, {"batch": "b02", "agree": "False"},
                   {"batch": "b03", "agree": ""}]
        h = self.history(("a", "ok", 1, "b01"), ("b", "ok", 1, "b02"), ("c", "failed", 1, "b02"),
                         ("d", "ok", 1, "b03"), ("e", "ok", 1, "b04"))  # b04: killed, no batches.csv row
        self.assertEqual(rx.requeue_candidates(batches, h), {"b02": ["b"], "b03": ["d"], "b04": ["e"]})

    def test_each_run_is_requeued_at_most_once(self):
        batches = [{"batch": "b02", "agree": "False"}, {"batch": "b02-r1", "agree": "False"}]
        h = self.history(("b", "ok", 1, "b02"), ("b", "discarded", 1, "b02"), ("b", "ok", 2, "b02-r1"))
        self.assertEqual(rx.requeue_candidates(batches, h), {})

    def test_discarded_run_that_reran_in_a_normal_batch_is_not_requeued_again(self):
        batches = [{"batch": "b02", "agree": "False"}, {"batch": "b02-2", "agree": "False"}]
        h = self.history(("b", "ok", 1, "b02"), ("b", "discarded", 1, "b02"), ("b", "ok", 2, "b02-2"))
        self.assertEqual(rx.requeue_candidates(batches, h), {})

    def test_retry_executions_are_not_requeued(self):
        h = self.history(("a", "failed", 1, "b01"), ("a", "ok", 2, "retry01"))
        self.assertEqual(rx.requeue_candidates([{"batch": "retry01", "agree": "False"}], h), {})

    def test_failed_runs_are_retried_once(self):
        h = self.history(("a", "failed", 1, "b01"), ("b", "timeout", 1, "b01"), ("b", "failed", 2, "retry01"),
                         ("c", "ok", 1, "b01"), ("d", "failed", 1, "b01"), ("d", "ok", 2, "b01-2"))
        self.assertEqual(rx.failed_once(h), ["a"])

    def test_chunks(self):
        self.assertEqual([len(c) for c in rx.chunks(list(range(95)), 40)], [40, 40, 15])
        self.assertEqual(rx.chunks([], 40), [])


class TornLineTest(unittest.TestCase):
    def test_append_after_torn_line_keeps_file_parseable(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "progress.csv"
            rx.append_progress(path, dict(run_id="a", attempt=1, status="ok", batch="b01"))
            with open(path, "a") as f:
                f.write("b,1,o")  # power loss mid-write
            rx.append_progress(path, dict(run_id="c", attempt=1, status="ok", batch="b01"))
            self.assertEqual(rx.latest_status(path), {"a": ("ok", 1), "c": ("ok", 1)})


class EstimateTest(unittest.TestCase):
    def test_mac_full_fits_15_h(self):
        runs = rx.schedule(rx.cells("mac", "full"), forks=10, seed=1)
        self.assertLess(rx.estimate_seconds(runs, "mac") / 3600, 15)

    def test_intel_full_fits_15_h(self):
        runs = rx.schedule(rx.cells("intel", "full"), forks=5, seed=1)
        hours = rx.estimate_seconds(runs, "intel") / 3600
        self.assertGreater(hours, 10)
        self.assertLess(hours, 15)

    def test_slow_cells_take_longer(self):
        seq = rx.run_seconds(rx.Cell("SEQUENTIAL", None, "SLEEP", "unpinned"), "intel")
        vt = rx.run_seconds(rx.Cell("VIRTUAL_THREADS", 256, "SLEEP", "unpinned"), "intel")
        self.assertGreater(seq, vt)


if __name__ == "__main__":
    unittest.main()
