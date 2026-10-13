
import hashlib
import re


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
