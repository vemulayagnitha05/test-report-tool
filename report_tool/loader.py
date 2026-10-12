import os
import xml.etree.ElementTree as ET

import pandas as pd

REQUIRED = ["test_name", "suite", "build", "timestamp", "status", "duration_ms"]
OPTIONAL = ["measurement", "lower_limit", "upper_limit", "unit"]
NUMERIC = ["duration_ms", "measurement", "lower_limit", "upper_limit"]

STATUS_ALIASES = {
    "passed": "pass", "ok": "pass", "success": "pass",
    "failed": "fail", "failure": "fail",
    "skipped": "skip", "broken": "error",
}
VALID_STATUS = ["pass", "fail", "error", "skip"]


def clean_table(df):
    """check the columns, fix types. returns (dataframe, list of warnings)"""
    warnings = []
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(
            "Missing column(s): " + ", ".join(missing) + ". Found: " + ", ".join(df.columns)
        )

    for col in OPTIONAL:
        if col not in df.columns:
            df[col] = pd.NA
    if "unit" in df.columns:
        df["unit"] = df["unit"].astype("string")

    df["status"] = df["status"].astype(str).str.strip().str.lower().replace(STATUS_ALIASES)
    unknown = sorted(set(df["status"]) - set(VALID_STATUS))
    if unknown:
        raise ValueError("Unknown status value(s): " + ", ".join(unknown)
                         + ". Allowed: " + ", ".join(VALID_STATUS))

    # Convert everything to UTC and drop the timezone, so files with and without a timezone
    # (for example a CSV and a JUnit XML) can be mixed without comparison errors.
    # Timestamps without a timezone are treated as UTC.
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True, format="mixed").dt.tz_localize(None)
    bad_time = int(df["timestamp"].isna().sum())
    if bad_time:
        warnings.append(f"{bad_time} row(s) had an invalid timestamp and were dropped.")
        df = df[df["timestamp"].notna()]

    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    negative = int((df["duration_ms"] < 0).sum())
    if negative:
        warnings.append(f"{negative} row(s) had a negative duration (set to empty).")
        df.loc[df["duration_ms"] < 0, "duration_ms"] = float("nan")

    df["test_name"] = df["test_name"].astype(str).str.strip()
    df["suite"] = df["suite"].astype(str).str.strip()
    df["build"] = df["build"].astype(str).str.strip()

    if df.empty:
        raise ValueError("No usable rows found in the input.")
    return df.reset_index(drop=True), warnings


def load_csv(path):
    return clean_table(pd.read_csv(path))


def check_xml_is_safe(data):
    """
    JUnit files never need a DOCTYPE. "Entity expansion" attacks (billion laughs) need one,
    so files that have one are refused. (The defusedxml package is the more thorough option.)
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("XML file must be UTF-8 encoded.")
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise ValueError("XML files with DOCTYPE or ENTITY declarations are not accepted.")


def load_junit_xml(path):
    """reads a JUnit xml file (pytest --junitxml=file.xml). The file name becomes the build name."""
    name = os.path.basename(path)
    build = os.path.splitext(name)[0]
    file_time = pd.Timestamp(os.path.getmtime(path), unit="s")

    with open(path, "rb") as f:
        data = f.read()
    check_xml_is_safe(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"{name} is not valid XML: {e}")

    rows = []
    for suite_element in root.iter("testsuite"):
        suite_name = suite_element.get("name", "unknown")
        suite_time = suite_element.get("timestamp") or file_time
        for case in suite_element.findall("testcase"):
            status = "pass"
            if case.find("failure") is not None:
                status = "fail"
            elif case.find("error") is not None:
                status = "error"
            elif case.find("skipped") is not None:
                status = "skip"
            try:
                seconds = float(case.get("time", 0) or 0)
            except ValueError:
                seconds = float("nan")
            rows.append({
                "test_name": case.get("name", "unknown"),
                "suite": case.get("classname") or suite_name,
                "build": build,
                "timestamp": suite_time,
                "status": status,
                "duration_ms": seconds * 1000,
            })
    if not rows:
        raise ValueError(f"No <testcase> elements found in {name}")
    return clean_table(pd.DataFrame(rows))


def load_results(paths):
    """load one or more files (.csv or .xml) into one table"""
    tables = []
    warnings = []
    for path in paths:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            table, warn = load_csv(path)
        elif ext == ".xml":
            table, warn = load_junit_xml(path)
        else:
            raise ValueError(f"Unsupported file type: {path} (use .csv or .xml)")
        tables.append(table)
        warnings += [f"{os.path.basename(path)}: {w}" for w in warn]
    return pd.concat(tables, ignore_index=True), warnings
