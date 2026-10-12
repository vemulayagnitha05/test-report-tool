import numpy as np
import pandas as pd

EXEC = ["pass", "fail", "error"]


def executed(df):
    """rows that really ran (skipped tests are not counted in pass rates)"""
    return df[df["status"] != "skip"]


def build_order(df):
    return list(df.groupby("build")["timestamp"].min().sort_values().index)


def overall_summary(df):
    ex = executed(df)
    runs = len(ex)
    passed = int((ex["status"] == "pass").sum())
    return {
        "runs": runs,
        "passed": passed,
        "failed": int((ex["status"] == "fail").sum()),
        "errors": int((ex["status"] == "error").sum()),
        "skipped": int((df["status"] == "skip").sum()),
        "pass_rate": 100 * passed / runs if runs else float("nan"),
        "tests": int(df["test_name"].nunique()),
        "suites": int(df["suite"].nunique()),
        "builds": int(df["build"].nunique()),
        "first": df["timestamp"].min(),
        "last": df["timestamp"].max(),
    }


def pass_rate_by(df, col):
    """table with pass/fail/error counts and pass rate for each value of col (suite or build)"""
    ex = executed(df)
    table = pd.crosstab(ex[col], ex["status"]).reindex(columns=EXEC, fill_value=0)
    table["runs"] = table[EXEC].sum(axis=1)
    table["pass_rate"] = 100 * table["pass"] / table["runs"]
    if col == "build":
        order = [b for b in build_order(df) if b in table.index]
        table = table.reindex(order)
    return table


def top_failures(df, n=10):
    ex = executed(df)
    table = pd.crosstab([ex["suite"], ex["test_name"]], ex["status"]).reindex(columns=EXEC, fill_value=0)
    table["runs"] = table[EXEC].sum(axis=1)
    table["bad"] = table["fail"] + table["error"]
    table["fail_rate"] = 100 * table["bad"] / table["runs"]
    table = table[table["bad"] > 0].sort_values(["bad", "fail_rate"], ascending=False).head(n)
    return table.reset_index()


def flaky_tests(df, min_builds=3):
    """
    A test is flaky in a build if it both passed and failed in the SAME build.
    (A test that fails every time in a build is broken, not flaky.)
    One unlucky failure should not count, so a test is only reported when this
    happened in at least `min_builds` different builds.
    """
    ex = executed(df).copy()
    ex["is_pass"] = ex["status"] == "pass"
    per = ex.groupby(["test_name", "build"])["is_pass"].agg(["min", "max", "size"]).reset_index()
    per["comparable"] = per["size"] >= 2
    per["mixed"] = per["comparable"] & per["max"].astype(bool) & ~per["min"].astype(bool)

    result = per.groupby("test_name").agg(
        builds_compared=("comparable", "sum"),
        builds_flaky=("mixed", "sum"),
    ).reset_index()
    result = result[result["builds_flaky"] >= min_builds].copy()
    result["flaky_rate"] = 100 * result["builds_flaky"] / result["builds_compared"]

    suites = ex.drop_duplicates("test_name").set_index("test_name")["suite"]
    result.insert(0, "suite", result["test_name"].map(suites))
    return result.sort_values(["flaky_rate", "builds_flaky"], ascending=False).reset_index(drop=True)


def iqr_outliers(values, k=1.5, min_count=8):
    """True for values far outside the box (IQR rule). Needs enough values to mean anything."""
    values = pd.Series(values)
    clean = values.dropna()
    if len(clean) < min_count:
        return pd.Series(False, index=values.index)
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    spread = q3 - q1
    return (values < q1 - k * spread) | (values > q3 + k * spread)


def duration_by_suite(df):
    d = df[df["duration_ms"].notna()]
    g = d.groupby("suite")["duration_ms"]
    table = pd.DataFrame({
        "runs": g.size(),
        "mean_ms": g.mean(),
        "median_ms": g.median(),
        "p95_ms": g.quantile(0.95),
        "max_ms": g.max(),
    })
    return table.reset_index()


def slowest_tests(df, n=8):
    d = df[df["duration_ms"].notna()]
    g = d.groupby(["suite", "test_name"])["duration_ms"]
    table = pd.DataFrame({"runs": g.size(), "mean_ms": g.mean(), "max_ms": g.max()})
    return table.sort_values("mean_ms", ascending=False).head(n).reset_index()


def duration_outliers(df):
    """runs that were much slower than usual for the same test"""
    d = df[df["duration_ms"].notna()].copy()
    d["outlier"] = False
    for name, group in d.groupby("test_name"):
        d.loc[group.index, "outlier"] = iqr_outliers(group["duration_ms"]).values
    g = d.groupby("test_name")
    table = pd.DataFrame({
        "runs": g.size(),
        "outlier_runs": g["outlier"].sum(),
        "median_ms": g["duration_ms"].median(),
        "max_ms": g["duration_ms"].max(),
    })
    table = table[table["outlier_runs"] > 0].sort_values("outlier_runs", ascending=False)
    return table.reset_index()


def cpk(mean, std, lower, upper):
    """process capability. one-sided limits are fine (the missing side is ignored)"""
    if pd.isna(std) or std == 0:
        return float("nan")
    values = []
    if not pd.isna(upper):
        values.append((upper - mean) / (3 * std))
    if not pd.isna(lower):
        values.append((mean - lower) / (3 * std))
    return min(values) if values else float("nan")


def cpk_rating(value, cpk_min):
    if pd.isna(value):
        return "n/a"
    if value < 1.0:
        return "not capable"
    if value < cpk_min:
        return "marginal"
    return "capable"


def first_value(series):
    series = series.dropna()
    return series.iloc[0] if len(series) else float("nan")


def measurement_table(df, cpk_min=1.33):
    columns = ["test_name", "unit", "n", "mean", "std", "min", "max", "lower_limit",
               "upper_limit", "out_of_limits", "cpk", "rating"]
    m = df[df["measurement"].notna()]
    rows = []
    for name, g in m.groupby("test_name"):
        lower = first_value(g["lower_limit"])
        upper = first_value(g["upper_limit"])
        values = g["measurement"]
        below = (values < lower).sum() if not pd.isna(lower) else 0
        above = (values > upper).sum() if not pd.isna(upper) else 0
        std = values.std(ddof=1) if len(values) > 1 else float("nan")
        value = cpk(values.mean(), std, lower, upper) if len(values) >= 5 else float("nan")
        unit = g["unit"].dropna()
        rows.append({
            "test_name": name,
            "unit": unit.iloc[0] if len(unit) else "",
            "n": len(values),
            "mean": values.mean(),
            "std": std,
            "min": values.min(),
            "max": values.max(),
            "lower_limit": lower,
            "upper_limit": upper,
            "out_of_limits": int(below + above),
            "cpk": value,
            "rating": cpk_rating(value, cpk_min),
        })
    return pd.DataFrame(rows, columns=columns)


def suite_drops(df, threshold=10.0):
    """suites whose pass rate fell by at least `threshold` points between two builds in a row"""
    ex = executed(df)
    if ex["build"].nunique() < 2:
        return []
    rate = (ex.assign(p=(ex["status"] == "pass") * 100.0)
              .groupby(["suite", "build"])["p"].mean().unstack("build"))
    rate = rate[[b for b in build_order(df) if b in rate.columns]]

    drops = []
    for suite, row in rate.iterrows():
        diff = row.diff()
        if diff.notna().any() and diff.min() <= -threshold:
            where = list(row.index).index(diff.idxmin())
            drops.append({
                "suite": suite,
                "from_build": row.index[where - 1],
                "to_build": row.index[where],
                "from_rate": row.iloc[where - 1],
                "to_rate": row.iloc[where],
            })
    return drops


def make_insights(df, cpk_min=1.33, flaky_min_builds=3):
    """short sentences for the top of the report. each is (level, text)"""
    notes = []
    s = overall_summary(df)
    notes.append(("info", f"{s['runs']} test runs across {s['tests']} tests, overall pass rate {s['pass_rate']:.1f}%."))

    by_build = pass_rate_by(df, "build")
    if len(by_build) >= 2:
        prev, last = by_build.iloc[-2], by_build.iloc[-1]
        change = last["pass_rate"] - prev["pass_rate"]
        names = f"{by_build.index[-2]} to {by_build.index[-1]}"
        if change <= -5:
            notes.append(("bad", f"Pass rate fell by {abs(change):.1f} points in the latest build ({names})."))
        elif change >= 5:
            notes.append(("ok", f"Pass rate improved by {change:.1f} points in the latest build ({names})."))

    for d in suite_drops(df):
        notes.append(("bad", f"Suite '{d['suite']}' dropped from {d['from_rate']:.0f}% to {d['to_rate']:.0f}% "
                             f"between {d['from_build']} and {d['to_build']}."))

    flaky = flaky_tests(df, flaky_min_builds)
    if len(flaky):
        worst = flaky.iloc[0]
        notes.append(("warn", f"{len(flaky)} flaky test(s). Worst: '{worst['test_name']}' mixed pass/fail in "
                              f"{int(worst['builds_flaky'])} of {int(worst['builds_compared'])} builds."))

    top = top_failures(df, n=1)
    if len(top):
        t = top.iloc[0]
        notes.append(("warn", f"Most failing test: '{t['test_name']}' ({int(t['bad'])} of {int(t['runs'])} runs failed)."))

    meas = measurement_table(df, cpk_min)
    for _, r in meas.iterrows():
        if r["rating"] == "not capable":
            notes.append(("bad", f"'{r['test_name']}' is not capable (Cpk {r['cpk']:.2f})."))
        elif r["rating"] == "marginal":
            notes.append(("warn", f"'{r['test_name']}' is marginal (Cpk {r['cpk']:.2f}, wanted {cpk_min})."))
        if r["out_of_limits"] > 0:
            notes.append(("warn", f"'{r['test_name']}' had {r['out_of_limits']} measurement(s) outside the limits."))

    slow = duration_outliers(df)
    if len(slow):
        notes.append(("info", f"{int(slow['outlier_runs'].sum())} unusually slow run(s) in {len(slow)} test(s)."))

    if all(level in ("info", "ok") for level, _ in notes):
        notes.append(("ok", "No obvious problems found."))
    return notes
