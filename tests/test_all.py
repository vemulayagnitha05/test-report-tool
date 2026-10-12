import os
import tempfile
import unittest

import pandas as pd

from report_tool import analysis
from report_tool.cli import main as cli_main
from report_tool.loader import clean_table, load_junit_xml, load_results
from report_tool.report import build_report

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample_results.csv")


def make_df(rows):
    """rows: (test_name, suite, build, day, status, duration_ms)"""
    df = pd.DataFrame(rows, columns=["test_name", "suite", "build", "day", "status", "duration_ms"])
    df["timestamp"] = pd.Timestamp("2026-01-01") + pd.to_timedelta(df["day"], unit="D")
    df["measurement"] = float("nan")
    df["lower_limit"] = float("nan")
    df["upper_limit"] = float("nan")
    df["unit"] = ""
    return df.drop(columns="day")


class LoaderTests(unittest.TestCase):
    def base(self, **changes):
        row = {"test_name": "t1", "suite": "s", "build": "b1", "timestamp": "2026-01-01 10:00",
               "status": "pass", "duration_ms": 10}
        row.update(changes)
        return pd.DataFrame([row])

    def test_missing_column(self):
        with self.assertRaises(ValueError) as ctx:
            clean_table(self.base().drop(columns=["suite"]))
        self.assertIn("suite", str(ctx.exception))

    def test_mixed_timezone_and_naive_timestamps(self):
        # a timezone-aware row and a naive row must load together and be comparable
        df = pd.concat([
            clean_table(self.base(timestamp="2026-01-01T10:00:00+00:00", build="b1"))[0],
            clean_table(self.base(timestamp="2026-01-02 10:00", build="b2"))[0],
        ], ignore_index=True)
        self.assertEqual(analysis.build_order(df), ["b1", "b2"])
        self.assertIsNone(df["timestamp"].dt.tz)

    def test_status_aliases(self):
        df, _ = clean_table(self.base(status="PASSED"))
        self.assertEqual(df.loc[0, "status"], "pass")

    def test_unknown_status(self):
        with self.assertRaises(ValueError):
            clean_table(self.base(status="maybe"))

    def test_bad_timestamp_dropped_with_warning(self):
        table = pd.concat([self.base(), self.base(timestamp="not a date")])
        df, warnings = clean_table(table)
        self.assertEqual(len(df), 1)
        self.assertEqual(len(warnings), 1)

    def test_negative_duration_warning(self):
        df, warnings = clean_table(self.base(duration_ms=-5))
        self.assertTrue(pd.isna(df.loc[0, "duration_ms"]))
        self.assertEqual(len(warnings), 1)

    def test_junit_xml(self):
        xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4" timestamp="2026-02-01T10:00:00">
  <testcase classname="tests.test_a" name="test_ok" time="0.250"/>
  <testcase classname="tests.test_a" name="test_bad" time="1.5"><failure message="x">trace</failure></testcase>
  <testcase classname="tests.test_b" name="test_err" time="0.1"><error message="y">trace</error></testcase>
  <testcase classname="tests.test_b" name="test_skip" time="0"><skipped message="z"/></testcase>
</testsuite></testsuites>"""
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "run42.xml")
            with open(path, "w") as f:
                f.write(xml)
            df, _ = load_junit_xml(path)
        self.assertEqual(list(df["status"]), ["pass", "fail", "error", "skip"])
        self.assertEqual(df.loc[0, "duration_ms"], 250)
        self.assertEqual(set(df["build"]), {"run42"})
        self.assertEqual(df.loc[0, "suite"], "tests.test_a")

    def test_unsupported_file_type(self):
        with self.assertRaises(ValueError):
            load_results(["results.txt"])


class AnalysisTests(unittest.TestCase):
    def test_pass_rate_ignores_skipped(self):
        df = make_df([("a", "s", "b1", 0, "pass", 1), ("b", "s", "b1", 0, "fail", 1),
                      ("c", "s", "b1", 0, "skip", 1)])
        table = analysis.pass_rate_by(df, "build")
        self.assertEqual(table.loc["b1", "runs"], 2)
        self.assertEqual(table.loc["b1", "pass_rate"], 50.0)
        self.assertEqual(analysis.overall_summary(df)["skipped"], 1)

    def test_builds_sorted_by_time_not_name(self):
        df = make_df([("a", "s", "zzz", 0, "pass", 1), ("a", "s", "aaa", 5, "pass", 1)])
        self.assertEqual(list(analysis.pass_rate_by(df, "build").index), ["zzz", "aaa"])

    def flaky_df(self, builds_with_flip):
        rows = []
        for i in range(4):
            build = f"b{i}"
            if i < builds_with_flip:
                rows += [("flip", "s", build, i, "pass", 1), ("flip", "s", build, i, "fail", 1)]
            else:
                rows += [("flip", "s", build, i, "pass", 1), ("flip", "s", build, i, "pass", 1)]
            rows += [("broken", "s", build, i, "fail", 1), ("broken", "s", build, i, "fail", 1)]
        return make_df(rows)

    def test_flaky_needs_mixed_results_in_enough_builds(self):
        result = analysis.flaky_tests(self.flaky_df(3), min_builds=3)
        self.assertEqual(list(result["test_name"]), ["flip"])
        self.assertEqual(result.loc[0, "builds_flaky"], 3)

    def test_one_unlucky_build_is_not_flaky(self):
        self.assertEqual(len(analysis.flaky_tests(self.flaky_df(1), min_builds=3)), 0)
        self.assertEqual(len(analysis.flaky_tests(self.flaky_df(1), min_builds=1)), 1)

    def test_always_failing_test_is_not_flaky(self):
        names = list(analysis.flaky_tests(self.flaky_df(4), min_builds=1)["test_name"])
        self.assertNotIn("broken", names)

    def test_iqr_outliers(self):
        values = [10, 11, 10, 12, 11, 10, 11, 12, 10, 11, 100]
        mask = analysis.iqr_outliers(values)
        self.assertEqual(list(mask).count(True), 1)
        self.assertTrue(mask.iloc[-1])

    def test_iqr_needs_enough_values(self):
        self.assertFalse(analysis.iqr_outliers([1, 2, 100]).any())

    def test_cpk_known_values(self):
        self.assertAlmostEqual(analysis.cpk(21, 0.8, 18, 24), 1.25)
        self.assertAlmostEqual(analysis.cpk(9, 1.0, float("nan"), 12), 1.0)  # one-sided
        self.assertTrue(pd.isna(analysis.cpk(5, 0, 1, 9)))  # no variation
        self.assertTrue(pd.isna(analysis.cpk(5, 1, float("nan"), float("nan"))))  # no limits

    def test_cpk_rating(self):
        self.assertEqual(analysis.cpk_rating(0.8, 1.33), "not capable")
        self.assertEqual(analysis.cpk_rating(1.2, 1.33), "marginal")
        self.assertEqual(analysis.cpk_rating(1.5, 1.33), "capable")
        self.assertEqual(analysis.cpk_rating(float("nan"), 1.33), "n/a")

    def measured_df(self, values):
        df = make_df([("m", "s", "b1", 0, "pass", 1)] * len(values))
        df["measurement"] = values
        df["lower_limit"] = 0.0
        df["upper_limit"] = 10.0
        return df

    def test_measurement_table_counts_out_of_limits(self):
        table = analysis.measurement_table(self.measured_df([5, 5.5, 4.5, 11, -1, 5]))
        self.assertEqual(table.loc[0, "out_of_limits"], 2)
        self.assertEqual(table.loc[0, "n"], 6)

    def test_too_few_measurements_gives_no_cpk(self):
        table = analysis.measurement_table(self.measured_df([5, 6, 4]))
        self.assertEqual(table.loc[0, "rating"], "n/a")

    def test_suite_drop_found(self):
        rows = []
        for build_number, fails in enumerate([0, 0, 5]):
            for i in range(10):
                rows.append((f"t{i}", "net", f"b{build_number}", build_number, "fail" if i < fails else "pass", 1))
        drops = analysis.suite_drops(make_df(rows), threshold=10)
        self.assertEqual(len(drops), 1)
        self.assertEqual(drops[0]["to_build"], "b2")
        self.assertEqual(drops[0]["to_rate"], 50.0)

    def test_insights_report_the_drop(self):
        rows = []
        for build_number, fails in enumerate([0, 6]):
            for i in range(10):
                rows.append((f"t{i}", "net", f"b{build_number}", build_number, "fail" if i < fails else "pass", 1))
        texts = [t for level, t in analysis.make_insights(make_df(rows)) if level == "bad"]
        self.assertTrue(any("dropped" in t for t in texts))
        self.assertTrue(any("fell" in t for t in texts))


class ReportTests(unittest.TestCase):
    def test_report_escapes_html(self):
        df = make_df([("<script>alert(1)</script>", "s", "b1", 0, "fail", 5),
                      ("ok", "s", "b1", 0, "pass", 5)])
        page = build_report(df, title="<b>My</b> report")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("<b>My</b>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_report_without_measurements(self):
        df = make_df([("a", "s", "b1", 0, "pass", 5), ("a", "s", "b2", 1, "pass", 5)])
        page = build_report(df)
        self.assertIn("No measurement data", page)
        self.assertIn("No failing tests", page)

    def test_single_build_works(self):
        df = make_df([("a", "s", "b1", 0, "pass", 5), ("b", "s", "b1", 0, "fail", 5)])
        self.assertIn("Pass rate per build", build_report(df))


class EndToEndTests(unittest.TestCase):
    def test_sample_data_report(self):
        with tempfile.TemporaryDirectory() as folder:
            out = os.path.join(folder, "sub", "report.html")
            code = cli_main([SAMPLE, "-o", out, "--title", "Test"])
            self.assertEqual(code, 0)
            with open(out, encoding="utf-8") as f:
                page = f.read()
        self.assertIn("data:image/png;base64", page)
        self.assertIn("throughput", page)

    def test_sample_data_finds_planted_problems(self):
        df, _ = load_results([SAMPLE])
        flaky = set(analysis.flaky_tests(df)["test_name"])
        self.assertEqual(flaky, {"multi_stream", "handover"})
        drops = analysis.suite_drops(df)
        self.assertEqual([(d["suite"], d["to_build"]) for d in drops], [("throughput", "build_104")])
        meas = analysis.measurement_table(df).set_index("test_name")
        self.assertEqual(meas.loc["latency_ms", "rating"], "not capable")

    def test_missing_file_returns_error_code(self):
        self.assertEqual(cli_main(["does_not_exist.csv", "-o", os.devnull]), 1)

    def test_bad_columns_return_error_code(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "bad.csv")
            with open(path, "w") as f:
                f.write("a,b\n1,2\n")
            self.assertEqual(cli_main([path, "-o", os.path.join(folder, "r.html")]), 1)


if __name__ == "__main__":
    unittest.main()
