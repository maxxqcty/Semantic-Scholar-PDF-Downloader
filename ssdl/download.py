
import hashlib
import re
import time

import requests


def safe_filename(text, max_length=150):
    """
    Convert text into a filename-safe string.
    """

    text = text or "Untitled"

    # Characters forbidden in Windows filenames:
    # < > : " / \ | ? *
    text = re.sub(r'[<>:"/\\|?*]', "", text)

    # Normalize whitespace.
    text = re.sub(r"\s+", " ", text).strip()

    # Avoid filenames ending in a period or space.
    return text[:max_length].rstrip(". ")


def file_hash(path):
    """
    Calculate SHA-256 hash of a file.
    """

    sha256 = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha256.update(chunk)

    return sha256.hexdigest()


def download_pdf(
    url,
    destination,
    session,
    max_retries=4,
):
    """
    Download and validate a PDF.

    Uses a .part file so interrupted downloads
    do not leave incomplete PDFs.
    """

    temporary = destination.with_suffix(
        destination.suffix + ".part"
    )

    for attempt in range(max_retries):

        try:

            with session.get(
                url,
                timeout=60,
                stream=True,
                allow_redirects=True,
            ) as response:

                # Handle rate limits and temporary
                # server errors.
                if response.status_code in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }:

                    retry_after = response.headers.get(
                        "Retry-After"
                    )

                    if retry_after:
                        try:
                            wait = float(retry_after)
                        except ValueError:
                            wait = min(
                                60,
                                3 * (2 ** attempt),
                            )
                    else:
                        wait = min(
                            60,
                            3 * (2 ** attempt),
                        )

                    print(
                        f"  PDF server returned "
                        f"HTTP {response.status_code}."
                    )

                    print(
                        f"  Retrying in "
                        f"{wait:.0f} seconds..."
                    )

                    time.sleep(wait)
                    continue

                response.raise_for_status()

                content_type = response.headers.get(
                    "content-type",
                    "",
                ).lower()

                first_chunk = next(
                    response.iter_content(
                        chunk_size=8192
                    ),
                    b"",
                )

                if not first_chunk:
                    return False, "Empty response"

                # Check both content type and PDF signature.
                is_pdf = (
                    "application/pdf" in content_type
                    or first_chunk.startswith(b"%PDF")
                )

                if not is_pdf:
                    return False, (
                        "Response is not a PDF "
                        f"(content-type: "
                        f"{content_type or 'unknown'})"
                    )

                with open(
                    temporary,
                    "wb",
                ) as file:

                    file.write(first_chunk)

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):
                        if chunk:
                            file.write(chunk)

            # Download completed.
            temporary.replace(destination)

            return True, "Downloaded"

        except requests.RequestException as exc:

            temporary.unlink(
                missing_ok=True
            )

            if attempt == max_retries - 1:
                return False, str(exc)

            wait = min(
                60,
                2 ** attempt,
            )

            print(
                f"  Download error: {exc}"
            )

            print(
                f"  Retrying in "
                f"{wait:.0f} seconds..."
            )

            time.sleep(wait)

        except OSError as exc:

            temporary.unlink(
                missing_ok=True
            )

            return False, str(exc)

    return False, "Download failed"
