
import time

import requests


API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

FIELDS = ",".join([
    "paperId",
    "title",
    "authors",
    "year",
    "venue",
    "url",
    "externalIds",
    "openAccessPdf",
])


def create_session():
    """
    Create the HTTP session.

    No API key is required.
    """

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "ResearchPDFDownloader/3.0 "
            "(academic research)"
        ),
        "Accept": "application/json",
    })

    return session


def search_papers(
    query,
    offset,
    limit,
    session,
    max_retries=7,
):
    """
    Search Semantic Scholar.

    Handles:
        429 rate limiting
        500 server errors
        502 bad gateway
        503 service unavailable
        504 gateway timeout
    """

    params = {
        "query": query,
        "offset": offset,
        "limit": min(limit, 100),
        "fields": FIELDS,
    }

    for attempt in range(max_retries):

        try:
            response = session.get(
                API_URL,
                params=params,
                timeout=30,
            )

        except requests.RequestException as exc:

            if attempt == max_retries - 1:
                raise

            wait = min(
                120,
                2 ** attempt,
            )

            print(
                f"  Search connection error: {exc}"
            )

            print(
                f"  Retrying in {wait:.0f} seconds..."
            )

            time.sleep(wait)
            continue

        # Successful request.
        if response.status_code == 200:
            return response.json()

        # Rate limited.
        if response.status_code == 429:

            retry_after = response.headers.get(
                "Retry-After"
            )

            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = min(
                        120,
                        5 * (2 ** attempt),
                    )
            else:
                wait = min(
                    120,
                    5 * (2 ** attempt),
                )

            print()
            print(
                "  Semantic Scholar rate limit "
                "reached (HTTP 429)."
            )

            print(
                f"  Waiting {wait:.0f} seconds "
                "before retrying..."
            )

            time.sleep(wait)
            continue

        # Temporary server errors.
        if response.status_code in {
            500,
            502,
            503,
            504,
        }:

            if attempt == max_retries - 1:
                response.raise_for_status()

            wait = min(
                60,
                2 ** attempt,
            )

            print(
                f"  Semantic Scholar server error "
                f"({response.status_code})."
            )

            print(
                f"  Retrying in {wait:.0f} seconds..."
            )

            time.sleep(wait)
            continue

        # Other HTTP errors.
        response.raise_for_status()

    raise RuntimeError(
        "Semantic Scholar search failed after "
        f"{max_retries} attempts."
    )
