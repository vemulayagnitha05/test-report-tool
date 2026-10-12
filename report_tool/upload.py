"""
Everything the web app does with uploaded files, kept here (no FastAPI needed)
so it can be tested without starting a server.
"""
import html
import math
import os
import re
import tempfile
import threading

from report_tool.loader import load_results
from report_tool.report import build_report

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 20
ALLOWED = {".csv", ".xml"}

# matplotlib's pyplot keeps global state, so only build one report at a time
_REPORT_LOCK = threading.Lock()


def safe_name(filename, index):
    """keep only the last part of the name and remove odd characters"""
    name = re.split(r"[\\/]", filename or "")[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return name or f"upload_{index}"


def check_settings(title, cpk_min, flaky_min_builds):
    if not math.isfinite(cpk_min) or cpk_min <= 0:
        raise ValueError("Cpk threshold must be a number greater than zero.")
    if flaky_min_builds < 1:
        raise ValueError("Minimum flaky builds must be at least 1.")
    return (title or "").strip()[:200] or "Test Report"


def add_footer(page, warnings):
    """adds the input warnings and a link back to the form. Warnings are escaped."""
    block = ""
    if warnings:
        items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
        block += ("<div style='max-width:960px;margin:14px auto;padding:12px 20px;background:#fff7df;"
                  "border:1px solid #eed38a;border-radius:8px;font-family:system-ui'>"
                  f"<strong>Input warnings</strong><ul>{items}</ul></div>")
    block += ("<p style='max-width:960px;margin:18px auto;font:14px system-ui'>"
              "<a href='/'>&larr; Generate another report</a></p>")
    return page.replace("</body>", block + "</body>")


def error_page(message):
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Error</title></head><body>"
            "<div style='max-width:760px;margin:60px auto;font-family:system-ui'>"
            "<h1>Could not generate report</h1>"
            f"<p>{html.escape(message)}</p><p><a href='/'>Try again</a></p></div></body></html>")


def report_from_uploads(uploads, title="Test Report", cpk_min=1.33, flaky_min_builds=3):
    """
    uploads: list of (original_filename, bytes).
    Returns the finished HTML page. Raises ValueError with a readable message for bad input.
    """
    title = check_settings(title, cpk_min, flaky_min_builds)
    if not uploads:
        raise ValueError("No files supplied.")
    if len(uploads) > MAX_FILES:
        raise ValueError(f"Too many files (the limit is {MAX_FILES}).")

    with tempfile.TemporaryDirectory() as folder:
        paths = []
        names = []
        for index, (filename, data) in enumerate(uploads):
            name = safe_name(filename, index)
            if os.path.splitext(name)[1].lower() not in ALLOWED:
                raise ValueError(f"Unsupported file type: {name}. Use .csv or .xml")
            if len(data) > MAX_FILE_BYTES:
                raise ValueError(f"{name}: file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
            if name in names:  # same name twice: keep both, but as separate builds
                name = f"{index}_{name}"
            names.append(name)
            path = os.path.join(folder, name)
            with open(path, "wb") as f:
                f.write(data)
            paths.append(path)

        with _REPORT_LOCK:
            df, warnings = load_results(paths)
            page = build_report(df, title=title, sources=names, cpk_min=cpk_min,
                                flaky_min_builds=flaky_min_builds)

    return add_footer(page, warnings)
