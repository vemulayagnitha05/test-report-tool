"""
Tests for web_app.py itself. They need FastAPI and httpx (pip install -r requirements.txt -r requirements-dev.txt)
and are skipped if those are missing.
"""
import os
import unittest

try:
    from fastapi.testclient import TestClient
    from web_app import app
    HAVE_WEB = True
except Exception:  # not installed
    HAVE_WEB = False

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample_results.csv")
XML = b"""<?xml version="1.0"?><testsuites><testsuite name="p" timestamp="2026-02-01T10:00:00">
<testcase classname="t.a" name="ok" time="0.1"/></testsuite></testsuites>"""


def upload(*files, **fields):
    return {"files": [("files", (name, data, "application/octet-stream")) for name, data in files],
            "data": fields}


@unittest.skipUnless(HAVE_WEB, "fastapi/httpx not installed")
class WebTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def post(self, *files, **fields):
        u = upload(*files, **fields)
        return self.client.post("/report", files=u["files"], data=u["data"])

    def test_home_and_health(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn("Test Report Tool", self.client.get("/").text)
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_report_from_csv(self):
        with open(SAMPLE, "rb") as f:
            response = self.post(("sample_results.csv", f.read()), title="Demo")
        self.assertEqual(response.status_code, 200)
        self.assertIn("data:image/png;base64", response.text)

    def test_xml_builds_keep_their_file_names(self):
        response = self.post(("run1.xml", XML), ("run2.xml", XML))
        self.assertEqual(response.status_code, 200)
        self.assertIn("run1", response.text)
        self.assertIn("run2", response.text)

    def test_wrong_file_type_gives_400(self):
        self.assertEqual(self.post(("notes.txt", b"hi")).status_code, 400)

    def test_broken_xml_gives_400_not_500(self):
        self.assertEqual(self.post(("x.xml", b"<testsuites><testcase")).status_code, 400)

    def test_error_text_is_escaped(self):
        csv = b"test_name,suite,build,timestamp,status,duration_ms\nt,s,b,2026-01-01,<img src=x>,5\n"
        response = self.post(("x.csv", csv))
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("<img", response.text)

    def test_bad_cpk_gives_400(self):
        self.assertEqual(self.post(("a.xml", XML), cpk_min="0").status_code, 400)


if __name__ == "__main__":
    unittest.main()
