import base64
import html

import pandas as pd

from report_tool import analysis, charts

CSS = """
body { font-family: Arial, Helvetica, sans-serif; margin: 0; background: #f4f5f7; color: #222; }
.page { max-width: 960px; margin: 0 auto; padding: 24px; }
h1 { margin-bottom: 4px; }
h2 { margin-top: 36px; border-bottom: 2px solid #ddd; padding-bottom: 4px; }
.sub { color: #666; margin-top: 0; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }
.card { background: white; border-radius: 8px; padding: 12px 18px; min-width: 120px; box-shadow: 0 1px 3px rgba(0,0,0,.12); }
.card .num { font-size: 26px; font-weight: bold; }
.card .lab { color: #666; font-size: 13px; }
ul.notes { list-style: none; padding: 0; }
ul.notes li { background: white; margin: 6px 0; padding: 8px 12px; border-left: 5px solid #999; border-radius: 4px; }
li.bad { border-color: #c0392b; } li.warn { border-color: #e69f00; }
li.ok { border-color: #2e8b57; } li.info { border-color: #3b6ea5; }
table.table { border-collapse: collapse; width: 100%; background: white; font-size: 14px; }
table.table th, table.table td { padding: 6px 10px; border-bottom: 1px solid #e3e3e3; text-align: right; }
table.table th:first-child, table.table td:first-child { text-align: left; }
img { max-width: 100%; background: white; border-radius: 6px; margin: 8px 0; }
.small { color: #666; font-size: 13px; }
@media print { body { background: white; } .card, ul.notes li { box-shadow: none; } }
"""


def image_tag(png, alt):
    if png is None:
        return ""
    data = base64.b64encode(png).decode("ascii")
    return f'<img alt="{html.escape(alt)}" src="data:image/png;base64,{data}">'


def table_html(df, rename=None):
    df = df.copy()
    if rename:
        df = df.rename(columns=rename)
    return df.to_html(index=False, classes="table", border=0, na_rep="-",
                      float_format=lambda x: f"{x:,.2f}")


def card(number, label):
    return f'<div class="card"><div class="num">{number}</div><div class="lab">{html.escape(label)}</div></div>'


def build_report(df, title="Test Report", sources=None, cpk_min=1.33, flaky_min_builds=3):
    s = analysis.overall_summary(df)
    by_build = analysis.pass_rate_by(df, "build")
    by_suite = analysis.pass_rate_by(df, "suite")
    failures = analysis.top_failures(df)
    flaky = analysis.flaky_tests(df, flaky_min_builds)
    dur_suite = analysis.duration_by_suite(df)
    slowest = analysis.slowest_tests(df)
    slow_runs = analysis.duration_outliers(df)
    meas = analysis.measurement_table(df, cpk_min)
    notes = analysis.make_insights(df, cpk_min, flaky_min_builds)

    p = []
    p.append(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>")
    p.append(f"<style>{CSS}</style></head><body><div class='page'>")
    p.append(f"<h1>{html.escape(title)}</h1>")
    dates = f"{s['first']:%Y-%m-%d} to {s['last']:%Y-%m-%d}"
    p.append(f"<p class='sub'>Data from {dates}. Source: {html.escape(', '.join(sources or ['unknown']))}</p>")

    p.append("<div class='cards'>")
    p.append(card(f"{s['pass_rate']:.1f}%", "pass rate"))
    p.append(card(s["runs"], "test runs"))
    p.append(card(s["passed"], "passed"))
    p.append(card(s["failed"], "failed"))
    p.append(card(s["errors"], "errors"))
    p.append(card(s["skipped"], "skipped"))
    p.append(card(s["builds"], "builds"))
    p.append("</div>")

    p.append("<h2>Key findings</h2><ul class='notes'>")
    for level, text in notes:
        p.append(f"<li class='{level}'>{html.escape(text)}</li>")
    p.append("</ul>")

    names = {"pass_rate": "pass rate %", "pass": "passed", "fail": "failed"}
    p.append("<h2>Pass rate per build</h2>")
    p.append(image_tag(charts.chart_pass_rate_by_build(df), "pass rate per build"))
    p.append(table_html(by_build.reset_index(), names))

    p.append("<h2>Pass rate per suite</h2>")
    p.append(image_tag(charts.chart_pass_rate_by_suite(df), "pass rate per suite"))
    p.append(table_html(by_suite.sort_values("pass_rate").reset_index(), names))

    p.append("<h2>Failures</h2>")
    if len(failures):
        p.append(image_tag(charts.chart_top_failures(df), "top failing tests"))
        p.append(table_html(failures, {"fail": "failed", "bad": "failed + errors", "fail_rate": "fail rate %"}))
    else:
        p.append("<p>No failing tests.</p>")

    p.append("<h2>Flaky tests</h2>")
    if len(flaky):
        p.append(f"<p class='small'>Flaky = passed and failed in the same build, in at least "
                 f"{flaky_min_builds} different builds.</p>")
        p.append(table_html(flaky, {"flaky_rate": "flaky rate %"}))
    else:
        p.append(f"<p>No flaky tests found (a test needs mixed results in at least {flaky_min_builds} builds, "
                 f"with at least two runs of it per build).</p>")

    p.append("<h2>Durations</h2>")
    p.append(image_tag(charts.chart_duration_by_suite(df), "duration per suite"))
    p.append(table_html(dur_suite))
    p.append("<h3>Slowest tests</h3>")
    p.append(table_html(slowest))
    if len(slow_runs):
        p.append("<h3>Tests with unusually slow runs</h3>")
        p.append("<p class='small'>A run counts as unusually slow if it is far above the middle 50% "
                 "of runs of the same test (IQR rule).</p>")
        p.append(table_html(slow_runs))

    p.append("<h2>Measurements</h2>")
    if len(meas):
        p.append(image_tag(charts.chart_measurements(df, meas), "measurement histograms"))
        p.append(table_html(meas, {"out_of_limits": "outside limits"}))
        p.append(f"<p class='small'>Cpk = distance from the mean to the nearest limit, divided by 3 standard "
                 f"deviations. Rating: below 1.0 not capable, below {cpk_min} marginal, otherwise capable. "
                 f"Needs at least 5 measurements. It assumes the values are roughly normal and stable, so "
                 f"look at the histogram too.</p>")
    else:
        p.append("<p>No measurement data in this input.</p>")

    p.append("<h2>Notes</h2><ul class='small'>")
    p.append("<li>Pass rate = passed / (passed + failed + errors). Skipped tests are not counted.</li>")
    p.append("<li>Statistics are descriptive. A few runs per build is not enough to prove a trend.</li>")
    p.append("</ul></div></body></html>")
    return "\n".join(p)
