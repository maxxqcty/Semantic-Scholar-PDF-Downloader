# Design: `ssdl` Package Restructure

Date: 2026-10-13
Status: approved in conversation (structure + command name), pending plan review

## Intent

Turn a single-file script (`downloader.py`, 1,093 lines) into an installable
Python package so the tool can be installed once from this folder and then run
from anywhere as a command:

```bash
ssdl --query "machine learning healthcare" --max-results 20
```

Today the user must run `python downloader.py ...` from the right folder and
install `requests` / `openpyxl` by hand. The restructure fixes that and splits
the file into units small enough to read on one screen.

## Goals

- `pip install -e .` (or `pip install -e ".[dev]"`) from the repo root installs
  the package, its dependencies, and an `ssdl` console command.
- Code split by responsibility into a flat `ssdl/` package at the repo root.
- Automated tests that prove the moved code behaves exactly as before.
- `.gitignore` so runtime output never gets committed.
- README updated so every documented command has actually been run.

## Non-goals / anti-goals

- **Not publishing to PyPI.** Folder-local install only, for now. No version
  classifiers, no long-description polish, no release process.
- **No behavior changes to the CLI.** Same flag names, same defaults, same
  filename format, same Excel columns, same retry/rate-limit behavior. This is
  a move, not a rewrite.
- **No new features** (no progress bars, no config files, no async, no API-key
  support).
- **No `src/` layout and no `python -m ssdl` shim** — YAGNI for a personal tool.
- **The original `downloader.py` is deleted** once its code has moved, not kept
  as a shim. One entry point only; the rewritten README teaches `ssdl`. The
  "no behavior changes" non-goal refers to the tool's observable behavior, not
  to preserving a second invocation path.

## Constraints

- `requires-python >= 3.9` (README promises 3.9+), so: no `X | None`
  annotations, no `tomllib`.
- Runtime dependencies: exactly `requests` and `openpyxl`. Dev extra: `pytest`.
  Tests must not add another mocking library — fake session/response objects
  are written by hand.
- Tests must never touch the network.
- Console script: `ssdl = "ssdl.cli:main"`.
- Version `3.0.0` (matches the existing `ResearchPDFDownloader/3.0` User-Agent).

## Decisions

### 1. Layout — flat package at repo root

```text
semantic-scholar-pdf-downloader/
├── pyproject.toml          metadata, deps, [project.scripts]
├── README.md
├── .gitignore              papers/, *.part, caches, build artifacts
├── ssdl/
│   ├── __init__.py         __version__ = "3.0.0"
│   ├── cli.py              argparse + main loop         (was main())
│   ├── search.py           create_session(), search_papers(), API_URL, FIELDS
│   ├── download.py         safe_filename(), file_hash(), download_pdf()
│   └── excel.py            create_excel()
├── tests/
│   ├── test_package.py
│   ├── test_download.py    (safe_filename, file_hash, download_pdf)
│   ├── test_search.py
│   ├── test_excel.py
│   └── test_cli.py
└── papers/                 runtime output, gitignored
```

Split by responsibility, not by technical layer: each module is one job.

### 2. Default output directory anchors to the project root

`downloader.py` currently resolves its default output with
`Path(__file__).resolve().parent`, i.e. the script's folder. After the move,
`__file__` lives in `ssdl/cli.py`, so a naive copy would put `papers/` inside
the package directory — a regression.

Decision: `main()` computes `Path(__file__).resolve().parent.parent` at call
time (not at import time, so tests can monkeypatch `ssdl.cli.__file__`).
Under an editable install this resolves to the repo root, preserving today's
documented promise: "output defaults next to the script, regardless of your
current terminal directory." An absolute `--output` is used as-is, as today.

Trade-off accepted: a future non-editable/PyPI install would anchor into
site-packages. Out of scope now; switching to CWD-relative is the noted
follow-up when publishing.

### 3. Dead query parameter removed

`search_papers()` sends `"openAccessPdf": ""` as a query parameter. It is not a
documented Semantic Scholar search parameter; the field is already requested
via `fields`. Drop it. Open-access filtering stays client-side via
`paper.get("openAccessPdf")`.

### 4. Tests are the verification

The project has no tests. Since the whole point is "the move changed nothing,"
tests are the checkable result for each task:

- `safe_filename` / `file_hash`: pure-function cases (Windows forbidden
  characters, whitespace collapse, 150-char cap, trailing dot/space, `None`
  title, known-content hash).
- `search_papers`: scripted fake session — 200, 429 with/without `Retry-After`,
  500 then 200, connection error then 200, non-retryable 404, limit clamped to
  100. `time.sleep` monkeypatched to record waits instead of sleeping.
- `download_pdf`: fake streamed response — HTML body rejected, `%PDF` magic
  accepted despite an odd content-type, empty body rejected, 429 with
  `Retry-After`, no `.part` file left behind after success or failure.
- `create_excel`: write to `tmp_path`, reload with `openpyxl.load_workbook`,
  assert headers, row count, freeze panes, hyperlinks, empty-records case.
- `cli.main(argv)`: `--help`, invalid-argument exits, and a full mocked run
  (one page, one paper without a PDF URL, one with) asserting the filename
  format, the Excel row, dedupe-by-hash deletion, and the anchored output path.

`main()` gains an `argv` parameter (`main(argv=None)`, forwarded to
`parse_args`) purely so tests can drive it without subprocesses.

### 5. README is rewritten last, from verified commands

The README currently names the folder `research-downloader/` (wrong) and tells
users to `pip install requests openpyxl` (replaced by `pip install -e .`). The
structure section, installation, usage, examples, troubleshooting, and the
implementation note about path anchoring are all updated.

Verification is by **scaled-down smoke runs**: every documented command is
executed with its exact syntax but tiny values (`--max-results 1`, output
redirected to a temp directory inside the repo), plus `ssdl --help`. The heavy
example values (`--max-results 200`, `--output "D:\Research\..."`) stay in the
README as illustrations and are never executed literally — doing so would mean
hours of API traffic, guaranteed rate-limit storms, and files written outside
the repo.

## What's left to the builder

Writing the plan, then the code: exact test names and assertions, commit
boundaries per task, and the wording of the README changes.
