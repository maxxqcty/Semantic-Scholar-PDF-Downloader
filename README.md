# 📄 Semantic Scholar Open-Access PDF Downloader

A Python command-line tool for searching [Semantic Scholar](https://www.semanticscholar.org/) and downloading openly accessible research papers as PDF files — complete with metadata tracking, duplicate detection, and rate-limit handling.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-Responsible--Use-lightgrey)
![Status](https://img.shields.io/badge/status-stable-brightgreen)

The downloader searches Semantic Scholar, checks whether a paper has an open-access PDF URL, downloads the PDF, verifies that the response is actually a PDF, detects duplicate files, and records metadata for successful downloads in an Excel spreadsheet.

---

## Table of Contents

- [Features](#-features)
- [Requirements](#-requirements)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Basic Usage](#-basic-usage)
- [Command-Line Options](#-command-line-options)
- [Output Directory](#-output-directory)
- [Filenames & Metadata](#-filenames--metadata)
- [How It Handles Edge Cases](#-how-it-handles-edge-cases)
- [Examples](#-examples)
- [Recommended Workflow](#-recommended-workflow)
- [Troubleshooting](#-troubleshooting)
- [Responsible Use](#-responsible-use)

---

## ✨ Features

| Category | What it does |
|---|---|
| **Search** | Queries Semantic Scholar and paginates automatically until enough PDFs are found |
| **Download** | Fetches openly accessible PDFs, using `.part` temp files to avoid partial/corrupt output |
| **Validation** | Confirms each response is a real PDF (via content-type or `%PDF` signature) |
| **Deduplication** | Hashes every PDF with SHA-256 and skips exact duplicates |
| **Resilience** | Handles HTTP `429`, retries `500/502/503/504` with exponential backoff, respects `Retry-After` |
| **Metadata** | Logs title, authors, year, venue, DOI, URLs, hash, and filename to an Excel file after every success |
| **Naming** | Sequential numbering + optional custom prefix + paper ID in every filename |
| **Portability** | Runs from any working directory; output defaults next to the script |

---

## 📋 Requirements

- **Python** 3.9 or newer
- Internet access
- Packages: `requests`, `openpyxl`

---

## 📁 Project Structure

```text
research-downloader/
├── downloader.py
├── README.md
└── papers/                                          ← created automatically
    ├── 01 - Machine Learning in Healthcare [...].pdf
    ├── 02 - Deep Learning in Healthcare [...].pdf
    ├── 03 - Artificial Intelligence in Medicine [...].pdf
    └── papers.xlsx
```

> You don't need to create the `papers/` directory manually — it's generated on first run.

> **Implementation note:** `downloader.py` must resolve its default output path with `Path(__file__).resolve().parent`, so that the "run from any directory" behavior described below matches reality.

---

## ⚙️ Installation

### 1. Install Python

Download from [python.org/downloads](https://www.python.org/downloads/). On Windows, check **"Add Python to PATH"** during setup.

Verify:

```bash
python --version
# Python 3.12.5
```

If `python` doesn't work, try `python3 --version`.

### 2. Install dependencies

```bash
pip install requests openpyxl
```

If `pip` isn't recognized:

```bash
python -m pip install requests openpyxl      # Windows
python3 -m pip install requests openpyxl      # Linux / macOS
```

---

## 🚀 Basic Usage

```bash
python downloader.py --query "machine learning healthcare"
```

By default this attempts to download **50 successful, unique PDFs** into `papers/` (created next to `downloader.py`).

Want fewer papers?

```bash
python downloader.py --query "machine learning healthcare" --max-results 20
```

> `--max-results` counts **successful, unique** downloads — not search results examined. The tool keeps paging through results until it hits that target or runs out of results.

---

## 🎛️ Command-Line Options

| Option | Description | Default |
|---|---|---|
| `--query` | Research query **(required)** | — |
| `--max-results` | Number of successful unique PDFs to download | `50` |
| `--output` | Directory for PDFs and `papers.xlsx` | `papers` |
| `--prefix` | Optional prefix for filenames | *(none)* |
| `--page-size` | Search results requested per API call (max `100`) | `100` |
| `--delay` | Seconds between PDF downloads | `2` |
| `--search-delay` | Seconds between search-page requests | `3` |

See full help anytime:

```bash
python downloader.py --help
```

---

## 📂 Output Directory

**Default** — relative to `downloader.py`, regardless of your current terminal directory:

```bash
python downloader.py --query "machine learning healthcare"
# → D:\ResearchTool\papers\
```

**Custom (relative or absolute)**:

```bash
# Relative
python downloader.py --query "machine learning healthcare" --output "research"

# Absolute (Windows)
python downloader.py --query "machine learning healthcare" --output "D:\Research\Papers"

# Absolute (Linux/macOS)
python3 downloader.py --query "machine learning healthcare" --output "/home/user/research/papers"
```

---

## 🏷️ Filenames & Metadata

### Filename format

```text
NUMBER - PREFIX - TITLE [PAPER_ID].pdf
```

| Example | With `--prefix "Healthcare ML"` |
|---|---|
| `01 - Machine Learning in Healthcare [abc123].pdf` | `01 - Healthcare ML - Machine Learning in Healthcare [abc123].pdf` |

- **Numbering** reflects successful, unique downloads only — never the raw search-result position (skipped/failed/duplicate results don't consume a number).
- **Paper ID** (e.g. `[abc123456789]`) disambiguates similarly titled papers.

### Excel metadata (`papers.xlsx`)

Saved in the same directory as the PDFs, updated **after every successful download** (so an interrupted run still keeps everything completed so far).

| Column | Description |
|---|---|
| Number | Successful download order |
| Title | Paper title |
| Authors | Paper authors |
| Year | Publication year |
| Venue | Journal / conference |
| DOI | DOI, if available |
| Paper URL | Semantic Scholar page |
| PDF URL | Source URL for the download |
| SHA256 | Hash of the downloaded PDF |
| Filename | Actual filename on disk |

> Only successful, unique downloads appear here — no-PDF, failed, invalid, or duplicate results are excluded.

---

## 🛡️ How It Handles Edge Cases

<details>
<summary><strong>Duplicate detection</strong></summary>

Every PDF is hashed with SHA-256. If a later result produces the same hash as an earlier one, it's flagged as a duplicate and skipped — even if it came from a different search result.
</details>

<details>
<summary><strong>PDF validation</strong></summary>

A download only counts as successful if the response either reports a PDF content type or begins with the `%PDF` signature. Servers that return an HTML page instead of a file are rejected.
</details>

<details>
<summary><strong>Temporary files</strong></summary>

Downloads write to a `.part` file first (e.g. `01 - Paper.pdf.part`) and are only renamed once complete — so an interrupted download never masquerades as a finished PDF.
</details>

<details>
<summary><strong>Rate limiting (HTTP 429)</strong></summary>

The tool automatically waits and retries on `429`, and also retries transient `500/502/503/504` errors with exponential backoff (e.g. 2s → 4s → 8s → 16s...), honoring the server's `Retry-After` header when present.
</details>

<details>
<summary><strong>Search pagination</strong></summary>

Results are pulled in pages (default size `100`, adjustable via <code>--page-size</code>) until the target PDF count is hit, results run out, or the search fails permanently.
</details>

---

## 💡 Examples

```bash
# Basic search — 50 PDFs into ./papers
python downloader.py --query "machine learning healthcare"

# Grab just 10
python downloader.py --query "machine learning healthcare" --max-results 10

# Custom output directory
python downloader.py --query "machine learning healthcare" \
    --max-results 50 --output "D:\Research\Healthcare"

# Custom filename prefix
python downloader.py --query "machine learning healthcare" \
    --max-results 50 --prefix "Healthcare ML"

# Directory + prefix combined
python downloader.py --query "machine learning healthcare" \
    --max-results 100 --output "D:\Research\Healthcare" --prefix "Healthcare ML"

# Slow things down if you're hitting 429s
python downloader.py --query "machine learning healthcare" \
    --max-results 50 --delay 5 --search-delay 10

# Large literature search
python downloader.py --query "deep learning medical imaging" \
    --max-results 200 --output "D:\Research\Medical Imaging" --prefix "Medical Imaging"
```

**PowerShell** (multi-line with backtick):

```powershell
python downloader.py `
    --query "machine learning healthcare" `
    --max-results 50 `
    --output "D:\Research\Papers" `
    --prefix "Healthcare ML"
```

**Linux/macOS** (multi-line with backslash):

```bash
python3 downloader.py \
    --query "machine learning healthcare" \
    --max-results 50 \
    --output "/home/user/research"
```

---

## 🧭 Recommended Workflow

1. **Test the query** with a small batch to check relevance:
   ```bash
   python downloader.py --query "machine learning healthcare" --max-results 5
   ```
2. **Scale up** once results look right:
   ```bash
   python downloader.py --query "machine learning healthcare" --max-results 50
   ```
3. **Organize** with a descriptive output directory:
   ```bash
   --output "D:\Research\Machine Learning Healthcare"
   ```
4. **Label** with a descriptive prefix:
   ```bash
   --prefix "ML Healthcare"
   ```

---

## 🧩 Troubleshooting

| Problem | Fix |
|---|---|
| `'python' is not recognized` | Try `python3 --version`, or reinstall Python with "Add to PATH" checked |
| `pip` not recognized | Use `python -m pip install requests openpyxl` |
| `ModuleNotFoundError: requests` / `openpyxl` | `python -m pip install requests openpyxl` |
| Frequent `HTTP 429` | Increase delays: `--delay 5 --search-delay 10` |
| `Search failed permanently` | Check internet connection, firewall, and Semantic Scholar status; test with `--max-results 1` |
| Fewer files than requested | Normal — some results lack PDFs, fail, or are duplicates; the tool stops once search results are exhausted |
| Can't open/overwrite `papers.xlsx` | Close the file in Excel before running the tool again |

---

## 🔒 Responsible Use

This tool is built for **legitimate academic and research purposes**. It only downloads PDFs from URLs explicitly marked as open-access by the Semantic Scholar API — it does **not**:

- Bypass paywalls
- Circumvent authentication
- Defeat access controls
- Break website security
- Access restricted files

Users are responsible for complying with applicable copyright law, licensing terms, institutional policy, and the [Semantic Scholar API terms](https://api.semanticscholar.org/api-docs/).

**API used:** [`api.semanticscholar.org/graph/v1`](https://api.semanticscholar.org/graph/v1) · **Docs:** [api.semanticscholar.org/api-docs](https://api.semanticscholar.org/api-docs/) · **API key:** not required
