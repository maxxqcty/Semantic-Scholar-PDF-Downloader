# `ssdl` Package Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-file `downloader.py` script into an installable `ssdl/` package with an `ssdl` console command, tests proving the moved code behaves identically, and a README rewritten from verified commands.

**Architecture:** Flat package `ssdl/` at the repo root, split by responsibility (`cli`, `search`, `download`, `excel`), installed with `pip install -e .` via `pyproject.toml`. Existing function bodies move verbatim; only three things change — `main()` gains an `argv` parameter, the default-output anchor becomes `Path(__file__).resolve().parent.parent`, and the dead `openAccessPdf=""` query parameter is dropped. Tests use hand-written fake sessions/responses, never the network.

**Tech Stack:** Python 3.9+, `requests`, `openpyxl`, setuptools (`pyproject.toml`), `pytest` (dev extra).

**Spec:** `docs/superpowers/specs/2026-10-13-ssdl-package-restructure-design.md`

## Global Constraints

- `requires-python >= 3.9`: no `X | None` annotations, no `tomllib`.
- Runtime dependencies: exactly `requests` and `openpyxl`. Dev extra: exactly `pytest`. No mocking library — fakes are written by hand. Tests never touch the network.
- Console script: `ssdl = "ssdl.cli:main"`. Version `3.0.0` in both `pyproject.toml` and `ssdl/__init__.py`.
- Layout: flat `ssdl/` package at repo root. No `src/`, no `python -m ssdl` shim.
- CLI flags and defaults unchanged: `--query` (required), `--max-results 50`, `--output papers`, `--prefix ""`, `--page-size 100`, `--delay 2`, `--search-delay 3`.
- Filename format unchanged: `NN - [prefix - ] Title [paperId[:12]].pdf`.
- Excel columns unchanged, in order: Number, Title, Authors, Year, Venue, DOI, Paper URL, PDF URL, SHA256, Filename.
- Default output anchors to the project root via `Path(__file__).resolve().parent.parent`, computed **inside** `main()` (not at module import) so tests can monkeypatch `ssdl.cli.__file__`.
- Every test command is run from the repo root as `python -m pytest ...`.
- README documents only commands that were run; heavy example values are never executed literally.
- `downloader.py` is deleted in the final task, together with the README rewrite that stops referencing it.

## Review Focus

1. **Server returns an HTML page with HTTP 200 instead of a PDF** — must be rejected, no file left on disk, not counted toward the target. Pinned by `test_rejects_html_response` in Task 5.
2. **Two different search results serve identical PDF bytes** — second must be deleted, and it must not consume a download number (third paper becomes `02`). Pinned by `test_duplicate_content_is_skipped_and_numbering_continues` in Task 6.
3. **HTTP 429 carrying `Retry-After`** — must wait exactly the server's value, not a guessed backoff. Pinned by `test_respects_retry_after_header_on_429` in Task 3 and `test_honors_retry_after_on_429` in Task 5.
4. **Default output path after the move** — must land at the repo root, never inside the `ssdl/` package directory. Pinned by `test_default_output_anchors_to_project_root` in Task 6.
5. **Interrupted or failed download** — no `.part` file and no half-written `.pdf` may survive. Pinned by `test_cleans_up_part_file_on_request_error` and `test_rejects_empty_response` in Task 5.

---

### Task 1: Packaging skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `ssdl/__init__.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: installed distribution `semantic-scholar-pdf-downloader` version `3.0.0`; module `ssdl` exposing `__version__: str`. Editable install supplies `requests`, `openpyxl`, `pytest` for all later tasks.

- [ ] **Step 1: Write the failing test**

`tests/test_package.py`:

```python
from importlib.metadata import version

import ssdl


def test_version_matches_installed_metadata():
    assert ssdl.__version__ == version("semantic-scholar-pdf-downloader")


def test_version_is_pinned():
    assert ssdl.__version__ == "3.0.0"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pip install pytest` (only if pytest is missing), then `python -m pytest tests/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ssdl'`

- [ ] **Step 3: Create `pyproject.toml`, `ssdl/__init__.py`, `.gitignore`**

`pyproject.toml` exactly as given (no `[project.scripts]` yet — that arrives with `cli.py` in Task 6):

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "semantic-scholar-pdf-downloader"
version = "3.0.0"
description = "Download open-access research PDFs from Semantic Scholar."
readme = "README.md"
requires-python = ">=3.9"
dependencies = [
    "requests>=2.28",
    "openpyxl>=3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[tool.setuptools]
packages = ["ssdl"]
```

`ssdl/__init__.py`:

```python
__version__ = "3.0.0"
```

`.gitignore`:

```gitignore
# Runtime output
papers/
*.part

# Python
__pycache__/
*.py[cod]
*.egg-info/
build/
dist/
.venv/
.pytest_cache/
```

- [ ] **Step 4: Install the package in editable mode**

Run: `python -m pip install -e ".[dev]"`
Expected: ends with `Successfully installed ... semantic-scholar-pdf-downloader-3.0.0 ...` (plus `requests`, `openpyxl`, `pytest` if they were missing)

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_package.py -v`
Expected: PASS, 2 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore ssdl/__init__.py tests/test_package.py
git commit -m "feat: add packaging skeleton for ssdl package"
```

---

### Task 2: `safe_filename` and `file_hash`

**Files:**
- Create: `ssdl/download.py`
- Test: `tests/test_download.py`

**Interfaces:**
- Consumes: package `ssdl` from Task 1.
- Produces:
  - `safe_filename(text: str | None, max_length: int = 150) -> str` — filename-safe string (annotation written as `Optional[str]` for the 3.9 floor).
  - `file_hash(path) -> str` — SHA-256 hex digest, streams the file in 1 MB chunks.
  - Module imports `hashlib`, `re`. Task 5 adds `download_pdf` to this same module.

If Python cannot find the new module, re-run `python -m pip install -e ".[dev]"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_download.py`:

```python
import hashlib
import os

from ssdl.download import file_hash, safe_filename


def test_strips_windows_forbidden_characters():
    assert safe_filename('A<B>C:D"E/F\\G|H?I*J') == "ABCDEFGHIJ"


def test_collapses_whitespace_and_strips():
    assert safe_filename("  Deep   Learning\t2024  ") == "Deep Learning 2024"


def test_caps_length_at_150():
    assert len(safe_filename("x" * 500)) == 150


def test_strips_trailing_dots_and_spaces():
    assert safe_filename("Quarterly Results...") == "Quarterly Results"


def test_falls_back_to_untitled_for_empty_input():
    assert safe_filename("") == "Untitled"
    assert safe_filename(None) == "Untitled"


def test_file_hash_matches_known_digest(tmp_path):
    target = tmp_path / "known.pdf"
    target.write_bytes(b"%PDF-1.4 test")
    expected = hashlib.sha256(b"%PDF-1.4 test").hexdigest()
    assert file_hash(target) == expected
    assert os.path.getsize(target) == 13
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_download.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ssdl.download'`

- [ ] **Step 3: Create `ssdl/download.py` with the two functions moved verbatim**

Copy `safe_filename` (from `downloader.py` lines 28–43) and `file_hash` (lines 46–60) into `ssdl/download.py` unchanged, keeping their docstrings. Top of file:

```python
import hashlib
import re
```

No behavior edits — the tests above pin the current behavior.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_download.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add ssdl/download.py tests/test_download.py
git commit -m "feat: move safe_filename and file_hash into ssdl.download"
```

---

### Task 3: Search session and `search_papers`

**Files:**
- Create: `ssdl/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: package `ssdl` from Task 1; `requests` from Task 1's install.
- Produces:
  - `API_URL: str` = `"https://api.semanticscholar.org/graph/v1/paper/search"`
  - `FIELDS: str` — comma-joined request fields, unchanged.
  - `create_session() -> requests.Session`
  - `search_papers(query, offset, limit, session, max_retries=7) -> dict`
  - Module-level `import time` (tests monkeypatch `time.sleep` through it).
  - **Change:** the `openAccessPdf` key is removed from the query `params` dict (the field stays in `FIELDS`).

- [ ] **Step 1: Write the failing tests**

`tests/test_search.py` — fake transport first, then the tests:

```python
import pytest
import requests

from ssdl import search


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Scripted session: each item is a response or an exception to raise."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr(search.time, "sleep", recorded.append)
    return recorded


def test_returns_payload_and_sends_expected_params(sleeps):
    payload = {"data": [{"paperId": "x"}], "total": 1, "next": None}
    session = FakeSession([FakeResponse(200, payload)])

    result = search.search_papers("query", offset=100, limit=50, session=session)

    assert result == payload
    params = session.calls[0]["params"]
    assert params["query"] == "query"
    assert params["offset"] == 100
    assert params["fields"] == search.FIELDS
    assert "openAccessPdf" not in params


def test_limit_is_clamped_to_100(sleeps):
    session = FakeSession([FakeResponse(200, {"data": []})])

    search.search_papers("q", offset=0, limit=500, session=session)

    assert session.calls[0]["params"]["limit"] == 100


def test_respects_retry_after_header_on_429(sleeps):
    payload = {"data": [], "total": 0}
    session = FakeSession([
        FakeResponse(429, headers={"Retry-After": "7"}),
        FakeResponse(200, payload),
    ])

    assert search.search_papers("q", 0, 10, session) == payload
    assert sleeps == [7.0]


def test_exponential_backoff_on_429_without_retry_after(sleeps):
    session = FakeSession([
        FakeResponse(429),
        FakeResponse(429),
        FakeResponse(200, {"data": []}),
    ])

    search.search_papers("q", 0, 10, session)

    assert sleeps == [5.0, 10.0]


def test_retries_server_error_then_succeeds(sleeps):
    session = FakeSession([
        FakeResponse(500),
        FakeResponse(200, {"data": []}),
    ])

    assert search.search_papers("q", 0, 10, session) == {"data": []}
    assert sleeps == [1.0]


def test_retries_connection_error(sleeps):
    session = FakeSession([
        requests.ConnectionError("reset"),
        FakeResponse(200, {"data": []}),
    ])

    assert search.search_papers("q", 0, 10, session) == {"data": []}
    assert sleeps == [1.0]


def test_raises_runtime_error_when_retries_exhausted(sleeps):
    session = FakeSession([FakeResponse(429), FakeResponse(429)])

    with pytest.raises(RuntimeError, match="search failed after 2 attempts"):
        search.search_papers("q", 0, 10, session, max_retries=2)


def test_non_retryable_status_raises(sleeps):
    session = FakeSession([FakeResponse(404)])

    with pytest.raises(requests.HTTPError):
        search.search_papers("q", 0, 10, session)


def test_create_session_sets_headers():
    session = search.create_session()
    assert "ResearchPDFDownloader/3.0" in session.headers["User-Agent"]
    assert session.headers["Accept"] == "application/json"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ssdl.search'`

- [ ] **Step 3: Create `ssdl/search.py` with `API_URL`, `FIELDS`, `create_session`, `search_papers`**

Move `API_URL`, `FIELDS` (lines 14–25), `create_session` (lines 63–80), and `search_papers` (lines 83–215) from `downloader.py` verbatim, then delete the `openAccessPdf` entry from the `params` dict in `search_papers` together with the comment block above it. Keep `import time` at module level.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_search.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add ssdl/search.py tests/test_search.py
git commit -m "feat: move search logic into ssdl.search, drop dead query param"
```

---

### Task 4: Excel metadata writer

**Files:**
- Create: `ssdl/excel.py`
- Test: `tests/test_excel.py`

**Interfaces:**
- Consumes: package `ssdl` from Task 1; `openpyxl` from Task 1's install.
- Produces: `create_excel(excel_path, records: list) -> None` — writes the workbook at `excel_path`, overwriting any existing file. Each record is a `dict` with keys `number, title, authors, year, venue, doi, paper_url, pdf_url, sha256, filename` (defined by Task 6's `main()` loop).

- [ ] **Step 1: Write the failing tests**

`tests/test_excel.py`:

```python
from openpyxl import load_workbook

from ssdl.excel import create_excel

HEADERS = [
    "Number", "Title", "Authors", "Year", "Venue",
    "DOI", "Paper URL", "PDF URL", "SHA256", "Filename",
]

RECORD = {
    "number": 1,
    "title": "Deep Learning",
    "authors": "A. Author, B. Author",
    "year": 2024,
    "venue": "NeurIPS",
    "doi": "10.1/xyz",
    "paper_url": "https://www.semanticscholar.org/paper/abc",
    "pdf_url": "https://example.org/abc.pdf",
    "sha256": "deadbeef",
    "filename": "01 - Deep Learning [abc].pdf",
}


def test_writes_headers_and_record_row(tmp_path):
    path = tmp_path / "papers.xlsx"

    create_excel(path, [RECORD])

    ws = load_workbook(path).active
    assert ws.title == "Downloaded Papers"
    assert [ws.cell(row=1, column=i + 1).value for i in range(10)] == HEADERS
    assert [ws.cell(row=2, column=i + 1).value for i in range(10)] == list(RECORD.values())


def test_empty_records_writes_header_only(tmp_path):
    path = tmp_path / "papers.xlsx"

    create_excel(path, [])

    ws = load_workbook(path).active
    assert ws.max_row == 1
    assert ws.cell(row=1, column=1).value == "Number"


def test_freezes_header_and_links_urls(tmp_path):
    path = tmp_path / "papers.xlsx"

    create_excel(path, [RECORD])

    ws = load_workbook(path).active
    assert ws.freeze_panes == "A2"
    assert ws.cell(row=2, column=7).hyperlink.target == RECORD["paper_url"]
    assert ws.cell(row=2, column=8).hyperlink.target == RECORD["pdf_url"]


def test_empty_urls_get_no_hyperlink(tmp_path):
    path = tmp_path / "papers.xlsx"
    record = dict(RECORD, paper_url="", pdf_url="")

    create_excel(path, [record])

    ws = load_workbook(path).active
    assert ws.cell(row=2, column=7).hyperlink is None
    assert ws.cell(row=2, column=8).hyperlink is None


def test_overwrites_previous_workbook(tmp_path):
    path = tmp_path / "papers.xlsx"
    create_excel(path, [RECORD])

    create_excel(path, [])

    ws = load_workbook(path).active
    assert ws.max_row == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_excel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ssdl.excel'`

- [ ] **Step 3: Create `ssdl/excel.py` with `create_excel` moved verbatim**

Move `create_excel` (lines 371–463) from `downloader.py` unchanged — headers, freeze panes, hyperlink loop, column widths, `workbook.save(excel_path)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_excel.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add ssdl/excel.py tests/test_excel.py
git commit -m "feat: move Excel metadata writer into ssdl.excel"
```

---

### Task 5: `download_pdf`

**Files:**
- Modify: `ssdl/download.py` (append `download_pdf`)
- Test: `tests/test_download.py` (extend)

**Interfaces:**
- Consumes: `ssdl.download.file_hash`, `ssdl.download.safe_filename` already in place (Task 2); `requests` from Task 1.
- Produces: `download_pdf(url, destination, session, max_retries=4) -> tuple` returning `(success: bool, message: str)`. On success `destination` holds the exact response bytes and no `.part` file remains; on failure nothing is left on disk. Uses `.part` + atomic rename, validates content-type or `%PDF` magic, honors `Retry-After` on 429/5xx.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_download.py` (imports at top become `hashlib`, `os`, `pytest`, `requests`, plus `from ssdl.download import download_pdf, file_hash, safe_filename`):

```python
class FakeStreamResponse:
    """Progressive stream: iter_content resumes where the last call stopped."""

    def __init__(self, status_code, body=b"", content_type="", headers=None,
                 fail_after=None):
        self.status_code = status_code
        self.body = body
        self.headers = {"content-type": content_type}
        if headers:
            self.headers.update(headers)
        self.fail_after = fail_after
        self.pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        if self.fail_after is not None and self.pos >= self.fail_after:
            raise requests.ConnectionError("connection reset mid-stream")
        while self.pos < len(self.body):
            end = min(self.pos + chunk_size, len(self.body))
            chunk = self.body[self.pos:end]
            self.pos = end
            yield chunk


class FakeStreamSession:
    def __init__(self, script):
        self.script = list(script)

    def get(self, url, timeout=None, stream=False, allow_redirects=True):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_success_writes_file_and_removes_part(tmp_path):
    destination = tmp_path / "paper.pdf"
    body = b"%PDF-1.4 hello world"
    session = FakeStreamSession([
        FakeStreamResponse(200, body, content_type="application/pdf"),
    ])

    assert download_pdf("https://x/p.pdf", destination, session) == (True, "Downloaded")
    assert destination.read_bytes() == body
    assert list(tmp_path.glob("*.part")) == []


def test_accepts_pdf_magic_despite_odd_content_type(tmp_path):
    destination = tmp_path / "paper.pdf"
    session = FakeStreamSession([
        FakeStreamResponse(200, b"%PDF-1.4", content_type="application/octet-stream"),
    ])

    assert download_pdf("https://x/p.pdf", destination, session)[0] is True
    assert destination.exists()


def test_rejects_html_response(tmp_path):
    destination = tmp_path / "paper.pdf"
    session = FakeStreamSession([
        FakeStreamResponse(200, b"<html>login required</html>", content_type="text/html"),
    ])

    ok, message = download_pdf("https://x/p.pdf", destination, session)
    assert ok is False
    assert message.startswith("Response is not a PDF")
    assert "text/html" in message
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_rejects_empty_response(tmp_path):
    destination = tmp_path / "paper.pdf"
    session = FakeStreamSession([FakeStreamResponse(200, b"", content_type="application/pdf")])

    assert download_pdf("https://x/p.pdf", destination, session) == (False, "Empty response")
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_honors_retry_after_on_429(tmp_path, monkeypatch):
    waits = []
    monkeypatch.setattr("ssdl.download.time.sleep", waits.append)
    destination = tmp_path / "paper.pdf"
    session = FakeStreamSession([
        FakeStreamResponse(429, headers={"Retry-After": "9"}),
        FakeStreamResponse(200, b"%PDF-1.4 ok", content_type="application/pdf"),
    ])

    assert download_pdf("https://x/p.pdf", destination, session)[0] is True
    assert waits == [9.0]
    assert destination.read_bytes() == b"%PDF-1.4 ok"


def test_cleans_up_part_file_on_request_error(tmp_path):
    destination = tmp_path / "paper.pdf"
    session = FakeStreamSession([
        FakeStreamResponse(200, b"%PDF-1.4", content_type="application/pdf", fail_after=5),
    ])

    ok, message = download_pdf("https://x/p.pdf", destination, session, max_retries=1)
    assert ok is False
    assert "connection reset" in message
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_download.py -v`
Expected: 6 old tests PASS, 6 new tests FAIL with `ImportError: cannot import name 'download_pdf'`

- [ ] **Step 3: Append `download_pdf` to `ssdl/download.py` moved verbatim**

Move `download_pdf` (lines 218–368) from `downloader.py` unchanged. Add `import time` and `import requests` at the top of `ssdl/download.py`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_download.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add ssdl/download.py tests/test_download.py
git commit -m "feat: move download_pdf with .part and validation logic into ssdl.download"
```

---

### Task 6: CLI entry point

**Files:**
- Create: `ssdl/cli.py`
- Modify: `pyproject.toml` (add `[project.scripts]`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `create_session`, `search_papers` from `ssdl.search`; `download_pdf`, `file_hash`, `safe_filename` from `ssdl.download`; `create_excel` from `ssdl.excel`.
- Produces:
  - `main(argv=None) -> None`, taking `argv: Optional[Sequence[str]]`, forwarded to `parser.parse_args(argv)`. Validation errors exit via `parser.error` (`SystemExit(2)`); `--help` exits `SystemExit(0)`.
  - Console script `ssdl` → `ssdl.cli:main`.
  - `search_papers`, `download_pdf`, and `create_session` are imported **by name** into `ssdl.cli` so tests can monkeypatch `ssdl.cli.search_papers` etc.
  - Record dict keys: `number, title, authors, year, venue, doi, paper_url, pdf_url, sha256, filename` (consumed by `create_excel`, Task 4).

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
import hashlib

import pytest
from openpyxl import load_workbook

from ssdl import cli


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "usage:" in output
    assert "--query" in output


def test_missing_query_is_rejected():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


@pytest.mark.parametrize("extra", [["--max-results", "0"], ["--page-size", "0"],
                                   ["--page-size", "101"], ["--delay", "-1"],
                                   ["--search-delay", "-1"]])
def test_invalid_arguments_are_rejected(extra):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--query", "q"] + extra)
    assert exc.value.code == 2


def _stub(monkeypatch, page):
    monkeypatch.setattr(cli, "create_session", lambda: object())
    monkeypatch.setattr(cli, "search_papers", lambda **kwargs: page)


def _fake_download(url, destination):
    destination.write_bytes(b"%PDF-1.4 fake")
    return True, "Downloaded"


def test_full_run_writes_pdf_and_excel(tmp_path, monkeypatch):
    _stub(monkeypatch, {
        "data": [
            {"paperId": "aaa11122233344455", "title": "No Open Access"},
            {
                "paperId": "abcdef1234567890",
                "title": "Deep Learning",
                "authors": [{"name": "A. Author"}],
                "year": 2024,
                "venue": "NeurIPS",
                "externalIds": {"DOI": "10.1/xyz"},
                "url": "https://www.semanticscholar.org/paper/abcdef",
                "openAccessPdf": {"url": "https://example.org/paper.pdf"},
            },
        ],
        "total": 2,
        "next": None,
    })
    monkeypatch.setattr(
        cli, "download_pdf",
        lambda url, destination, session, max_retries=4: _fake_download(url, destination),
    )

    out = tmp_path / "out"
    cli.main(["--query", "q", "--max-results", "1", "--output", str(out),
              "--delay", "0", "--search-delay", "0"])

    assert [p.name for p in out.glob("*.pdf")] == ["01 - Deep Learning [abcdef123456].pdf"]

    ws = load_workbook(out / "papers.xlsx").active
    assert ws.max_row == 2
    assert ws.cell(row=2, column=1).value == 1
    assert ws.cell(row=2, column=2).value == "Deep Learning"
    assert ws.cell(row=2, column=9).value == hashlib.sha256(b"%PDF-1.4 fake").hexdigest()
    assert ws.cell(row=2, column=10).value == "01 - Deep Learning [abcdef123456].pdf"


def test_duplicate_content_is_skipped_and_numbering_continues(tmp_path, monkeypatch):
    def paper(pid, title):
        return {"paperId": pid, "title": title,
                "openAccessPdf": {"url": f"https://example.org/{pid}.pdf"}}

    _stub(monkeypatch, {
        "data": [paper("111111111111aaaa", "First"),
                 paper("222222222222bbbb", "Second"),
                 paper("333333333333cccc", "Third")],
        "total": 3,
        "next": None,
    })
    bodies = [b"%PDF-1.4 same", b"%PDF-1.4 same", b"%PDF-1.4 other"]

    def fake_download(url, destination, session, max_retries=4):
        destination.write_bytes(bodies.pop(0))
        return True, "Downloaded"

    monkeypatch.setattr(cli, "download_pdf", fake_download)

    out = tmp_path / "out"
    cli.main(["--query", "q", "--max-results", "2", "--output", str(out),
              "--delay", "0", "--search-delay", "0"])

    names = sorted(p.name for p in out.glob("*.pdf"))
    assert names == ["01 - First [111111111111].pdf",
                     "02 - Third [333333333333].pdf"]

    ws = load_workbook(out / "papers.xlsx").active
    assert ws.max_row == 3
    assert ws.cell(row=3, column=1).value == 2
    assert ws.cell(row=3, column=2).value == "Third"


def test_default_output_anchors_to_project_root(tmp_path, monkeypatch):
    fake_root = tmp_path / "proj"
    fake_pkg = fake_root / "ssdl"
    fake_pkg.mkdir(parents=True)
    monkeypatch.setattr(cli, "__file__", str(fake_pkg / "cli.py"))
    _stub(monkeypatch, {"data": [], "total": 0, "next": None})

    cli.main(["--query", "q", "--delay", "0", "--search-delay", "0"])

    assert (fake_root / "papers" / "papers.xlsx").is_file()
    assert list(fake_pkg.iterdir()) == []


def test_absolute_output_is_used_as_is(tmp_path, monkeypatch):
    _stub(monkeypatch, {"data": [], "total": 0, "next": None})
    out = tmp_path / "elsewhere"

    cli.main(["--query", "q", "--output", str(out), "--delay", "0", "--search-delay", "0"])

    assert (out / "papers.xlsx").is_file()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ssdl.cli'`

- [ ] **Step 3: Create `ssdl/cli.py`**

- Move `main()` (lines 466–1089) and its `argparse` setup verbatim, with exactly three edits:
  1. Signature becomes `def main(argv=None):` and the parse call becomes `args = parser.parse_args(argv)`.
  2. Output anchor: `script_dir = Path(__file__).resolve().parent.parent` (was `.parent`) — computed inside `main()`, as written.
  3. Add `if __name__ == "__main__": main()` at the bottom.
- Imports at top of file: `from ssdl.download import download_pdf, file_hash, safe_filename`, `from ssdl.search import create_session, search_papers`, `from ssdl.excel import create_excel`, plus `argparse`, `time`, `pathlib.Path` as used. `requests` stays imported (it is caught by name in `main()`).

- [ ] **Step 4: Declare the console script and reinstall**

Add to `pyproject.toml`, directly under the `[project.optional-dependencies]` block:

```toml
[project.scripts]
ssdl = "ssdl.cli:main"
```

Run: `python -m pip install -e ".[dev]"` then `ssdl --help`
Expected: prints usage starting with `usage: ssdl [-h] --query QUERY` (if `ssdl` is not recognized, reopen the shell and retry; verify with `python -c "from ssdl.cli import main; main(['--help'])"`)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS, all tests across Tasks 1–6 (40 total — the plan originally predicted 45; Task 2's six tests live inside Task 5's `tests/test_download.py`, so they were counted twice)

- [ ] **Step 6: Commit**

```bash
git add ssdl/cli.py pyproject.toml tests/test_cli.py
git commit -m "feat: add ssdl CLI entry point with anchored default output"
```

---

### Task 7: README rewrite, script removal, smoke verification

**Files:**
- Modify: `README.md`
- Delete: `downloader.py`

**Interfaces:**
- Consumes: the `ssdl` command installed in Task 6.
- Produces: a README whose every command has been executed (scaled down where noted), and a repo with exactly one entry point.

- [ ] **Step 1: Rewrite `README.md`**

Section by section, keeping the document's tone and tables:

- **Project Structure** — replace the `research-downloader/` tree with the real layout: `pyproject.toml`, `README.md`, `.gitignore`, `ssdl/` (with its five files), `tests/`, and `papers/` marked as auto-created and gitignored.
- **Installation** — replace `pip install requests openpyxl` with `python -m pip install -e .` (and `python -m pip install -e ".[dev]"` for development). Keep the "Add Python to PATH" guidance.
- **Basic Usage / Examples / Recommended Workflow / PowerShell + Linux blocks** — every `python downloader.py` becomes `ssdl`. Heavy example values stay exactly as they are (illustrative, never executed).
- **Output Directory** — default resolves to the project folder (next to `pyproject.toml`), regardless of terminal directory; the implementation note becomes "`ssdl/cli.py` must resolve its default output path with `Path(__file__).resolve().parent.parent`". Keep the absolute/relative custom-output examples.
- **Command-Line Options, Filenames & Metadata, Edge Cases, Responsible Use** — unchanged in substance; drop the stale `python downloader.py --help` line for `ssdl --help`.
- **Troubleshooting** — replace `ModuleNotFoundError` rows with "re-run `python -m pip install -e .`"; drop `'python' is not recognized` → keep as-is; add a `ssdl is not recognized` row ("reopen the terminal after installing, or check the Python Scripts directory is on PATH").
- **Add a Development section** — `python -m pip install -e ".[dev]"`, `python -m pytest`, no network needed for tests.

- [ ] **Step 2: Delete the original script**

Run: `git rm downloader.py`

- [ ] **Step 3: Confirm no stale references remain**

Run: `grep -rn "downloader.py\|research-downloader" README.md docs/ || echo CLEAN`
Expected: `CLEAN` (the two spec files under `docs/superpowers/specs/` are historical records of this migration — if grep hits them, leave those hits and confirm `README.md` itself is clean)

- [ ] **Step 4: Run the scaled-down smoke commands from the README**

Run each, from the repo root:

```powershell
ssdl --help
ssdl --query "machine learning healthcare" --max-results 1 --output .smoke-verify --delay 0 --search-delay 0
ssdl --query "machine learning healthcare" --max-results 1 --prefix "Smoke" --output .smoke-verify --delay 0 --search-delay 0
ssdl `
    --query "machine learning healthcare" `
    --max-results 1 `
    --output .smoke-verify `
    --prefix "Smoke"
```

Expected: `--help` prints usage; each real run creates `.smoke-verify\papers.xlsx` and 0–2 `*.pdf` files whose names start `01 - `. A rate-limit wait is acceptable evidence that retry handling works; a specific download count is **not** required. Then clean up: `Remove-Item -Recurse .smoke-verify`.

- [ ] **Step 5: Run the full test suite one last time**

Run: `python -m pytest tests/ -v`
Expected: PASS, 40 passed

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for the ssdl command, remove downloader.py"
git status --short
Expected: empty (no smoke artifacts, no stray files)
```
