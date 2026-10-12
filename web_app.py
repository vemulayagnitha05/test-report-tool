from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from report_tool.upload import MAX_FILE_BYTES, error_page, report_from_uploads

app = FastAPI(title="Test Report Tool", version="0.1.0")

HOME = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test Report Tool</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f6f7f9;color:#20252b;margin:0}
.wrap{max-width:820px;margin:0 auto;padding:42px 20px}
.card{background:#fff;border:1px solid #e1e5e9;border-radius:12px;padding:30px}
h1{margin:0 0 8px;font-size:32px}
.lead{color:#59636e;line-height:1.55;margin-top:0}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:24px 0}
.field{display:flex;flex-direction:column;gap:7px}.full{grid-column:1/-1}
label{font-weight:600;font-size:14px}
input{padding:10px;border:1px solid #cbd2d9;border-radius:7px;background:white;font:inherit}
button{margin-top:6px;padding:11px 16px;border:0;border-radius:7px;background:#20252b;color:white;font-weight:600;cursor:pointer}
.note{margin-top:20px;padding:12px 14px;background:#f7f8fa;border:1px solid #e3e6e9;border-radius:8px;color:#59636e;font-size:13px;line-height:1.5}
.footer{margin-top:18px;color:#727b84;font-size:13px}
@media(max-width:650px){.grid{grid-template-columns:1fr}.full{grid-column:auto}h1{font-size:28px}}
</style>
</head>
<body>
<main class="wrap">
<section class="card">
<h1>Test Report Tool</h1>
<p class="lead">
A small project for analysing test results. Upload CSV or JUnit XML files and
the tool will generate a report with pass rates, failures, possible flaky tests,
durations, measurements and Cpk.
</p>
<form action="/report" method="post" enctype="multipart/form-data">
<div class="grid">
<div class="field full">
<label for="files">Test result files</label>
<input id="files" name="files" type="file" accept=".csv,.xml" multiple required>
<small>Use CSV or JUnit XML (max 10 MB per file). Each XML file is treated as one build.</small>
</div>
<div class="field">
<label for="title">Report title</label>
<input id="title" name="title" type="text" value="Test Report">
</div>
<div class="field">
<label for="cpk">Minimum Cpk</label>
<input id="cpk" name="cpk_min" type="number" step="0.01" min="0" value="1.33">
</div>
<div class="field">
<label for="flaky">Minimum builds for flaky test</label>
<input id="flaky" name="flaky_min_builds" type="number" min="1" value="3">
</div>
</div>
<button type="submit">Generate report</button>
</form>
<div class="note">
<strong>Demo data:</strong> the repository includes synthetic sample results with a few
problems planted on purpose. Please don't upload confidential test results to this public demo.
</div>
<div class="footer">Built as a Python portfolio project using Pandas, Matplotlib and FastAPI.</div>
</section>
</main>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HOME


@app.get("/health")
def health():
    return {"status": "ok"}


# This is a normal "def" (not "async def") on purpose: building a report is slow, CPU-heavy work,
# and FastAPI runs normal functions in a worker thread so other requests are not blocked.
@app.post("/report", response_class=HTMLResponse)
def report(
    files: list[UploadFile] = File(...),
    title: str = Form("Test Report"),
    cpk_min: float = Form(1.33),
    flaky_min_builds: int = Form(3),
):
    try:
        uploads = []
        for upload in files:
            # read at most one byte more than the limit, so a huge file is never loaded into memory
            data = upload.file.read(MAX_FILE_BYTES + 1)
            uploads.append((upload.filename or "", data))
        page = report_from_uploads(uploads, title, cpk_min, flaky_min_builds)
        return HTMLResponse(page)
    except (ValueError, OSError) as exc:
        return HTMLResponse(error_page(str(exc)), status_code=400)
