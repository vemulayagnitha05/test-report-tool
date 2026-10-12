import io

import matplotlib
matplotlib.use("Agg")  # no window, just make image files
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from report_tool.analysis import pass_rate_by, top_failures

GREEN = "#2e8b57"
RED = "#c0392b"
BLUE = "#3b6ea5"


def to_png(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def chart_pass_rate_by_build(df):
    table = pass_rate_by(df, "build")
    fig, ax = plt.subplots(figsize=(7, 3.4))
    colors = [GREEN if r >= 95 else (BLUE if r >= 85 else RED) for r in table["pass_rate"]]
    bars = ax.bar(table.index, table["pass_rate"], color=colors)
    for bar, value in zip(bars, table["pass_rate"]):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 1, f"{value:.0f}%", ha="center", fontsize=9)
    ax.set_ylim(0, 110)
    ax.set_ylabel("pass rate (%)")
    ax.set_title("Pass rate per build")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    return to_png(fig)


def chart_pass_rate_by_suite(df):
    table = pass_rate_by(df, "suite").sort_values("pass_rate")
    fig, ax = plt.subplots(figsize=(7, 0.6 * len(table) + 1.6))
    colors = [GREEN if r >= 95 else (BLUE if r >= 85 else RED) for r in table["pass_rate"]]
    ax.barh(table.index, table["pass_rate"], color=colors)
    for y, value in enumerate(table["pass_rate"]):
        ax.text(value + 1, y, f"{value:.0f}%", va="center", fontsize=9)
    ax.set_xlim(0, 110)
    ax.set_xlabel("pass rate (%)")
    ax.set_title("Pass rate per suite")
    return to_png(fig)


def chart_top_failures(df, n=8):
    table = top_failures(df, n).iloc[::-1]
    if table.empty:
        return None
    fig, ax = plt.subplots(figsize=(7, 0.5 * len(table) + 1.6))
    ax.barh(table["test_name"], table["fail"], color=RED, label="failed")
    ax.barh(table["test_name"], table["error"], left=table["fail"], color="#e69f00", label="error")
    ax.set_xlabel("number of runs")
    ax.set_title("Tests with the most failures")
    ax.legend(loc="lower right")
    return to_png(fig)


def chart_duration_by_suite(df):
    d = df[df["duration_ms"].notna()]
    names = sorted(d["suite"].unique())
    if not names:
        return None
    data = [d[d["suite"] == n]["duration_ms"] for n in names]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.boxplot(data, flierprops={"markersize": 3})
    ax.set_xticklabels(names)
    ax.set_ylabel("duration (ms)")
    ax.set_title("Test duration per suite")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    return to_png(fig)


def chart_measurements(df, table, max_plots=6):
    """one histogram per measured test, with the limits drawn as red lines"""
    names = list(table["test_name"])[:max_plots]
    if not names:
        return None
    cols = 2 if len(names) > 1 else 1
    rows = (len(names) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(7, 2.6 * rows), squeeze=False)

    for i, name in enumerate(names):
        ax = axes[i // cols][i % cols]
        values = df[df["test_name"] == name]["measurement"].dropna()
        row = table[table["test_name"] == name].iloc[0]
        ax.hist(values, bins=20, color=BLUE, alpha=0.85)
        for limit in (row["lower_limit"], row["upper_limit"]):
            if limit == limit:  # not NaN
                ax.axvline(limit, color=RED, linestyle="--")
        ax.axvline(values.mean(), color="black", linewidth=1)
        unit = f" ({row['unit']})" if row["unit"] else ""
        ax.set_title(f"{name}{unit}", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    for j in range(len(names), rows * cols):
        axes[j // cols][j % cols].axis("off")
    fig.tight_layout()
    return to_png(fig)
