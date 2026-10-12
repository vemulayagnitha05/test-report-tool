# Test Report Tool

A small Python project I built to practice working with test results, data analysis, statistics, and charts.

The tool takes test results from **CSV files or JUnit XML files** and turns them into an HTML report. The report shows things I would normally want to check after a few test runs:

- overall pass rate
- pass rate by build and suite
- tests that fail often
- possible flaky tests
- slow tests and duration outliers
- measurements and limit checks
- Cpk for measurements where limits are available
- a short list of findings

I also added a small FastAPI page so the project can be tried in a browser instead of only from the command line.

## Live Demo

The project is deployed on Render:

https://test-report-tool.onrender.com

The free deployment may take a little time to wake up after being inactive.

## Why I made it

I wanted a project that combined Python, Pandas, statistics, visualization, testing, and automated reporting. Those are all areas I am interested in for test/automation work.

The main goal was to build something useful enough to demonstrate the complete flow:

**test results -> analysis -> charts -> report**

## Try it locally

Create a virtual environment and install the dependencies:

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Mac/Linux:

```bash
source venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
```

### Command line

Create the example data:

```bash
python make_sample_data.py
```

Generate a report:

```bash
python -m report_tool.cli data/sample_results.csv -o output/report.html
```

JUnit XML files can also be passed as separate builds:

```bash
python -m report_tool.cli run1.xml run2.xml run3.xml -o output/report.html
```

### Browser version

Start the local web app:

```bash
uvicorn web_app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Upload a CSV or one or more JUnit XML files and generate a report.

## Running the tests

The project has 61 automated tests (the web tests need `pip install -r requirements-dev.txt`):

```bash
python -m unittest discover -s tests -t .
```

The tests cover the input handling, calculations, flaky-test detection, Cpk calculations, report generation, and the web-related validation.

## Input data

### CSV

The CSV format includes:

| Column | Required | Meaning |
|---|---|---|
| `test_name` | Yes | Test name |
| `suite` | Yes | Test group |
| `build` | Yes | Build/version |
| `timestamp` | Yes | Test time |
| `status` | Yes | pass, fail, error or skip |
| `duration_ms` | Yes | Test duration |
| `measurement` | No | Numeric measurement |
| `lower_limit` | No | Lower measurement limit |
| `upper_limit` | No | Upper measurement limit |
| `unit` | No | Measurement unit |

For JUnit XML, the test class is used as the suite and the XML filename is used as the build name.

## A few of the rules

I kept the analysis fairly simple and explainable rather than trying to make it look more advanced than it is.

- **Pass rate:** passed / (passed + failed + errors). Skipped tests are left out.
- **Flaky test:** a test is flaky in a build if it both passed and failed in that same build. It is reported when this happens in at least 3 different builds by default (and the test ran at least twice in each of those builds).
- **Suite regression:** a suite is flagged when its pass rate drops by at least 10 percentage points.
- **Slow test:** a run is flagged when it is above the IQR-based limit for that test. At least 8 runs are needed.
- **Cpk:** calculated when there are enough measurements and at least one process limit is available.

The Cpk minimum and the minimum number of builds for a flaky test can be changed from the command line (`--cpk-min`, `--flaky-min-builds`) or the web form. The suite-regression threshold (10 points) and the slow-test settings (IQR rule, 8 runs) are fixed in the code.

## Sample data

The included `data/sample_results.csv` is **synthetic**.

I deliberately put a few problems into it so that I could check whether the analysis finds them:

- a regression in one build
- two flaky tests
- measurements with poor Cpk

So the findings in the included sample report are **not real production results**. They are there to demonstrate and test the tool.

## What I learned / what I would improve

This project also showed me that small statistical datasets can be misleading. For example, with only a few runs per build, it is easy for a single failure to make a test look flaky. That is why I made the minimum number of builds configurable.

Cpk also needs some care. This implementation pools measurements across builds, so a trend or drift between builds can make the process look worse. I would like to add a per-build measurement trend chart next.

Other ideas I would work on later:

- measurement trends by build
- comparing two builds side by side
- Excel export
- support for more test-result formats
- better handling of very large result files

## Deployment

The project includes a small FastAPI app and a `render.yaml` file for deployment on Render.

The app has:

```text
GET /       -> upload page
POST /report -> generate report
GET /health -> deployment health check
```

Uploaded files are processed for the request and temporary files are removed afterwards. I would **not** upload confidential company test results to a public demo.

## Project structure

```text
report_tool/       analysis and report code
tests/             automated tests
data/              synthetic example data
output/            example generated report
make_sample_data.py
web_app.py         FastAPI web interface
render.yaml        Render deployment configuration
```

## Limitations

This is a student/portfolio project, not a production test-management system.

The statistics are descriptive and are intended to help spot possible problems. They are not a replacement for proper statistical analysis.

The JUnit examples I tested were small and hand-written, so different JUnit producers may have slightly different XML structures.

I tested the project with the dependency versions in the development environment; I have not tested every older version allowed by the dependency ranges.

## Portfolio note

I built this project to demonstrate Python, test automation, data analysis, statistics, and reporting. The sample data is synthetic. When possible, I would also run it against real JUnit output from projects I own and describe those results separately.
