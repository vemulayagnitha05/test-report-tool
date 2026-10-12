import argparse
import os

from report_tool.loader import load_results
from report_tool.report import build_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make an HTML report from test results (.csv or JUnit .xml)")
    parser.add_argument("inputs", nargs="+", help="one or more result files")
    parser.add_argument("-o", "--output", default="output/report.html")
    parser.add_argument("--title", default="Test Report")
    parser.add_argument("--cpk-min", type=float, default=1.33, help="Cpk needed to count as capable")
    parser.add_argument("--flaky-min-builds", type=int, default=3,
                        help="a test is flaky if it had mixed results in at least this many builds")
    args = parser.parse_args(argv)

    try:
        df, warnings = load_results(args.inputs)
    except (ValueError, OSError) as e:
        print("Error:", e)
        return 1

    for w in warnings:
        print("Warning:", w)

    sources = [os.path.basename(p) for p in args.inputs]
    page = build_report(df, args.title, sources, args.cpk_min, args.flaky_min_builds)

    folder = os.path.dirname(args.output)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Read {len(df)} rows. Report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
