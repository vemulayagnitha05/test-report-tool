import os
import time
import unittest

from report_tool.loader import load_results
from report_tool.upload import (MAX_FILE_BYTES, MAX_FILES, add_footer, error_page,
                                report_from_uploads, safe_name)

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample_results.csv")

XML = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" timestamp="2026-02-01T10:00:00">
  <testcase classname="tests.a" name="test_ok" time="0.25"/>
  <testcase classname="tests.a" name="test_bad" time="1.5"><failure message="x">trace</failure></testcase>
</testsuite></testsuites>"""

BOMB = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">
<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>
<testsuites><testsuite name="&lol2;"><testcase name="a" time="1"/></testsuite></testsuites>"""

CSV_HEADER = b"test_name,suite,build,timestamp,status,duration_ms\n"


class SafeNameTests(unittest.TestCase):
    def test_removes_folders(self):
        self.assertEqual(safe_name("../../etc/passwd.csv", 0), "passwd.csv")
        self.assertEqual(safe_name("C:\\Users\\me\\run1.xml", 0), "run1.xml")

    def test_removes_odd_characters(self):
        self.assertEqual(safe_name("<script>.csv", 0), "_script_.csv")

    def test_empty_name(self):
        self.assertEqual(safe_name("", 3), "upload_3")
        self.assertEqual(safe_name("..", 2), "upload_2")


class BuildNameBugTests(unittest.TestCase):
    """the bug: uploaded XML files used to get random tmp names as build names"""

    def test_original_file_names_become_builds(self):
        page = report_from_uploads([("run1.xml", XML), ("run2.xml", XML)])
        self.assertIn("run1", page)
        self.assertIn("run2", page)
        self.assertNotIn("tmp", page.replace("tmp_", ""))

    def test_same_name_twice_keeps_both(self):
        page = report_from_uploads([("a.xml", XML), ("a.xml", XML)])
        self.assertIn(">a<", page)
        self.assertIn("1_a", page)


class ValidationTests(unittest.TestCase):
    def test_unsupported_type(self):
        with self.assertRaises(ValueError):
            report_from_uploads([("notes.txt", b"hello")])

    def test_no_files(self):
        with self.assertRaises(ValueError):
            report_from_uploads([])

    def test_too_many_files(self):
        with self.assertRaises(ValueError):
            report_from_uploads([(f"r{i}.xml", XML) for i in range(MAX_FILES + 1)])

    def test_file_too_big(self):
        with self.assertRaises(ValueError) as ctx:
            report_from_uploads([("big.csv", b"x" * (MAX_FILE_BYTES + 1))])
        self.assertIn("larger", str(ctx.exception))

    def test_bad_settings(self):
        for cpk in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                report_from_uploads([("a.xml", XML)], cpk_min=cpk)
        with self.assertRaises(ValueError):
            report_from_uploads([("a.xml", XML)], flaky_min_builds=0)

    def test_title_is_escaped_and_shortened(self):
        page = report_from_uploads([("a.xml", XML)], title="<b>x</b>" + "y" * 500)
        self.assertNotIn("<b>x</b>", page)
        self.assertNotIn("y" * 250, page)


class BadInputTests(unittest.TestCase):
    """every kind of broken upload must become a ValueError (a friendly 400), never a crash"""

    def test_truncated_xml(self):
        with self.assertRaises(ValueError) as ctx:
            report_from_uploads([("broken.xml", b"<testsuites><testsuite name='x'><testcase name='a'")])
        self.assertIn("not valid XML", str(ctx.exception))

    def test_xml_with_entities_is_refused_quickly(self):
        start = time.time()
        with self.assertRaises(ValueError) as ctx:
            report_from_uploads([("bomb.xml", BOMB)])
        self.assertIn("DOCTYPE", str(ctx.exception))
        self.assertLess(time.time() - start, 2)

    def test_lowercase_doctype_also_refused(self):
        with self.assertRaises(ValueError):
            report_from_uploads([("x.xml", b"<?xml version='1.0'?><!doctype a><a/>")])

    def test_xml_not_utf8(self):
        with self.assertRaises(ValueError):
            report_from_uploads([("x.xml", b"<?xml version='1.0'?><a>\xff\xfe</a>")])

    def test_xml_without_testcases(self):
        with self.assertRaises(ValueError):
            report_from_uploads([("x.xml", b"<testsuites></testsuites>")])

    def test_empty_csv(self):
        with self.assertRaises(ValueError):
            report_from_uploads([("x.csv", b"")])

    def test_csv_not_utf8(self):
        with self.assertRaises(ValueError):
            report_from_uploads([("x.csv", b"test_name,suite\n\xff\xfe,x\n")])

    def test_csv_with_wrong_columns(self):
        with self.assertRaises(ValueError):
            report_from_uploads([("x.csv", b"a,b\n1,2\n")])


class EscapingTests(unittest.TestCase):
    def test_error_page_escapes(self):
        page = error_page("Unknown status: <img src=x onerror=alert(1)>")
        self.assertNotIn("<img", page)
        self.assertIn("&lt;img", page)

    def test_warnings_are_escaped(self):
        page = add_footer("<html><body>report</body></html>", ["<script>bad()</script>"])
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Generate another report", page)

    def test_hostile_status_value_ends_up_escaped(self):
        csv = CSV_HEADER + b"t,s,b,2026-01-01,<img src=x onerror=alert(1)>,5\n"
        with self.assertRaises(ValueError) as ctx:
            report_from_uploads([("x.csv", csv)])
        self.assertIn("<img", str(ctx.exception))          # the loader message has it...
        self.assertNotIn("<img", error_page(str(ctx.exception)))  # ...the page must not

    def test_warning_from_bad_rows_shows_real_file_name(self):
        csv = CSV_HEADER + b"t,s,b,not-a-date,pass,5\nt,s,b,2026-01-01,pass,5\n"
        page = report_from_uploads([("my results.csv", csv)])
        self.assertIn("my results.csv", page)
        self.assertIn("invalid timestamp", page)


class EndToEndTests(unittest.TestCase):
    def test_sample_csv(self):
        with open(SAMPLE, "rb") as f:
            page = report_from_uploads([("sample_results.csv", f.read())], title="Demo")
        self.assertIn("data:image/png;base64", page)
        self.assertIn("multi_stream", page)
        self.assertIn("Generate another report", page)

    def test_temp_files_are_removed(self):
        import tempfile
        before = set(os.listdir(tempfile.gettempdir()))
        report_from_uploads([("a.xml", XML)])
        try:
            report_from_uploads([("a.xml", b"<broken")])
        except ValueError:
            pass
        self.assertEqual(set(os.listdir(tempfile.gettempdir())) - before, set())

    def test_loader_still_works_with_plain_paths(self):
        df, _ = load_results([SAMPLE])
        self.assertEqual(len(df), 378)


if __name__ == "__main__":
    unittest.main()
