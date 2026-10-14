#!/usr/bin/env python3

import argparse
import time
from pathlib import Path

import requests

from ssdl.download import download_pdf, file_hash, safe_filename
from ssdl.search import create_session, search_papers
from ssdl.excel import create_excel


def main(argv=None):

    parser = argparse.ArgumentParser(
        description=(
            "Download open-access research PDFs "
            "from Semantic Scholar."
        )
    )

    parser.add_argument(
        "--query",
        required=True,
        help="Research query.",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help=(
            "Number of successfully downloaded "
            "unique PDFs. Default: 50."
        ),
    )

    parser.add_argument(
        "--output",
        default="papers",
        help=(
            "Download directory. "
            "Default: papers"
        ),
    )

    parser.add_argument(
        "--prefix",
        default="",
        help=(
            "Optional prefix for PDF filenames. "
            "Example: --prefix 'ML Healthcare'"
        ),
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help=(
            "Number of search results per page. "
            "Maximum: 100. Default: 100."
        ),
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help=(
            "Seconds between PDF downloads. "
            "Default: 2."
        ),
    )

    parser.add_argument(
        "--search-delay",
        type=float,
        default=3.0,
        help=(
            "Seconds between search pages. "
            "Default: 3."
        ),
    )

    args = parser.parse_args(argv)

    if args.max_results <= 0:
        parser.error(
            "--max-results must be greater than 0"
        )

    if not 1 <= args.page_size <= 100:
        parser.error(
            "--page-size must be between 1 and 100"
        )

    if args.delay < 0:
        parser.error(
            "--delay cannot be negative"
        )

    if args.search_delay < 0:
        parser.error(
            "--search-delay cannot be negative"
        )

    # Convert the output directory to an absolute path.
    #
    # The package may be installed anywhere, so anchor
    # the default output directory to the project root
    # (the parent of the ssdl/ package directory),
    # never to the package directory itself.
    script_dir = Path(__file__).resolve().parent.parent

    output_path = Path(args.output)

    if output_path.is_absolute():
        output_dir = output_path
    else:
        output_dir = script_dir / output_path

    output_dir = output_dir.resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    excel_path = (
        output_dir / "papers.xlsx"
    )

    session = create_session()

    # Clean the optional filename prefix.
    #
    # An empty --prefix must stay empty. safe_filename
    # maps empty input to "Untitled", which is right for
    # a missing paper title but wrong for a prefix —
    # without this guard every filename reads
    # "01 - Untitled - Title [id].pdf".
    filename_prefix = (
        safe_filename(args.prefix)
        if args.prefix
        else ""
    )

    print("=" * 70)
    print(
        "Semantic Scholar Open-Access PDF Downloader"
    )
    print("=" * 70)
    print()

    print(
        f"Query:           {args.query}"
    )

    print(
        f"Target PDFs:     {args.max_results}"
    )

    print(
        f"Download folder: {output_dir}"
    )

    print(
        f"Excel file:      {excel_path}"
    )

    print(
        f"Filename prefix: "
        f"{filename_prefix or '(none)'}"
    )

    print(
        f"Page size:       {args.page_size}"
    )

    print(
        f"PDF delay:       {args.delay}s"
    )

    print(
        f"Search delay:    {args.search_delay}s"
    )

    print()

    print(
        "API key:         Not required"
    )

    print()

    downloaded_records = []

    # Hashes of successfully downloaded PDFs.
    seen_hashes = set()

    # Semantic Scholar paper IDs already processed.
    seen_paper_ids = set()

    offset = 0
    total_available = None

    while (
        len(downloaded_records)
        < args.max_results
    ):

        print("-" * 70)

        print(
            f"Searching results "
            f"{offset + 1}-"
            f"{offset + args.page_size}..."
        )

        try:

            result = search_papers(
                query=args.query,
                offset=offset,
                limit=args.page_size,
                session=session,
            )

        except requests.RequestException as exc:

            print()
            print(
                f"Search failed permanently: {exc}"
            )
            print()
            break

        except Exception as exc:

            print()
            print(
                f"Unexpected search error: {exc}"
            )
            print()
            break

        papers = result.get(
            "data",
            [],
        )

        total_available = result.get(
            "total"
        )

        next_offset = result.get(
            "next"
        )

        print(
            f"Received {len(papers)} results."
        )

        if total_available is not None:

            print(
                "Matching results reported by "
                f"Semantic Scholar: "
                f"{total_available:,}"
            )

        if not papers:

            print(
                "No more search results."
            )

            break

        for paper in papers:

            if (
                len(downloaded_records)
                >= args.max_results
            ):
                break

            paper_id = paper.get(
                "paperId"
            )

            # Avoid processing the same paper twice.
            if (
                paper_id
                and paper_id in seen_paper_ids
            ):
                continue

            if paper_id:
                seen_paper_ids.add(
                    paper_id
                )

            title = (
                paper.get("title")
                or "Untitled"
            )

            authors = ", ".join(
                author.get("name", "")
                for author in (
                    paper.get("authors")
                    or []
                )
                if author.get("name")
            )

            year = (
                paper.get("year")
                or ""
            )

            venue = (
                paper.get("venue")
                or ""
            )

            external_ids = (
                paper.get("externalIds")
                or {}
            )

            doi = external_ids.get(
                "DOI",
                "",
            )

            paper_url = paper.get(
                "url",
                "",
            )

            open_access = (
                paper.get("openAccessPdf")
                or {}
            )

            pdf_url = open_access.get(
                "url"
            )

            print()
            print(
                f"Current successful downloads: "
                f"{len(downloaded_records)}/"
                f"{args.max_results}"
            )

            print(
                f"Paper: {title}"
            )

            if not pdf_url:

                print(
                    "  No PDF URL. Skipping."
                )

                continue

            # The number is based only on successful
            # unique downloads.
            download_number = (
                len(downloaded_records) + 1
            )

            safe_title = safe_filename(
                title
            )

            # Build filename.
            #
            # Without prefix:
            # 01 - Paper Title [paperid].pdf
            #
            # With prefix:
            # 01 - ML Healthcare - Paper Title [paperid].pdf

            filename_parts = [
                f"{download_number:02d}",
            ]

            if filename_prefix:
                filename_parts.append(
                    filename_prefix
                )

            filename_parts.append(
                safe_title
            )

            filename = " - ".join(
                filename_parts
            )

            if paper_id:
                filename += (
                    f" [{paper_id[:12]}]"
                )

            filename += ".pdf"

            destination = (
                output_dir / filename
            )

            # Prevent overwriting an existing file.
            if destination.exists():

                counter = 2

                while True:

                    base_name = (
                        destination.stem
                    )

                    candidate = (
                        output_dir
                        / (
                            f"{base_name} "
                            f"({counter}).pdf"
                        )
                    )

                    if not candidate.exists():

                        destination = candidate
                        break

                    counter += 1

            print(
                f"  PDF URL: {pdf_url}"
            )

            success, message = download_pdf(
                url=pdf_url,
                destination=destination,
                session=session,
            )

            if not success:

                destination.unlink(
                    missing_ok=True
                )

                print(
                    f"  FAILED: {message}"
                )

                continue

            # Calculate SHA-256.
            try:

                digest = file_hash(
                    destination
                )

            except OSError as exc:

                destination.unlink(
                    missing_ok=True
                )

                print(
                    f"  Hashing failed: {exc}"
                )

                continue

            # Detect duplicate PDF content.
            if digest in seen_hashes:

                destination.unlink(
                    missing_ok=True
                )

                print(
                    "  DUPLICATE: PDF deleted."
                )

                continue

            seen_hashes.add(
                digest
            )

            # The PDF is now officially considered
            # a successful download.
            record = {
                "number": download_number,
                "title": title,
                "authors": authors,
                "year": year,
                "venue": venue,
                "doi": doi,
                "paper_url": paper_url,
                "pdf_url": pdf_url,
                "sha256": digest,
                "filename": destination.name,
            }

            downloaded_records.append(
                record
            )

            # Save Excel immediately.
            create_excel(
                excel_path,
                downloaded_records,
            )

            print()
            print(
                "  SUCCESS!"
            )

            print(
                f"  Saved: {destination.name}"
            )

            print(
                f"  Progress: "
                f"{len(downloaded_records)}/"
                f"{args.max_results}"
            )

            print(
                f"  Directory: {output_dir}"
            )

            if (
                len(downloaded_records)
                >= args.max_results
            ):
                break

            if args.delay > 0:

                time.sleep(
                    args.delay
                )

        # Target reached.
        if (
            len(downloaded_records)
            >= args.max_results
        ):
            break

        # Get the next search page.
        if next_offset is not None:

            offset = next_offset

        else:

            offset += len(papers)

        # Fewer results than requested means we have
        # reached the end of the available results.
        if (
            len(papers)
            < args.page_size
        ):

            print()
            print(
                "Reached the end of the "
                "available search results."
            )

            break

        print()
        print(
            f"Waiting {args.search_delay}s "
            "before the next search page..."
        )

        if args.search_delay > 0:

            time.sleep(
                args.search_delay
            )

    # Always save the final Excel file.
    create_excel(
        excel_path,
        downloaded_records,
    )

    print()
    print("=" * 70)
    print("FINISHED")
    print("=" * 70)

    print(
        f"Downloaded PDFs: "
        f"{len(downloaded_records)}"
    )

    print(
        f"Download folder: "
        f"{output_dir}"
    )

    print(
        f"Excel file:      "
        f"{excel_path}"
    )

    print("=" * 70)

    if (
        len(downloaded_records)
        < args.max_results
    ):

        print()
        print(
            "WARNING:"
        )

        print(
            f"Requested {args.max_results} PDFs, "
            "but only "
            f"{len(downloaded_records)} "
            "were successfully downloaded."
        )

        print(
            "The Excel file contains only "
            "successful downloads."
        )


if __name__ == "__main__":
    main()
