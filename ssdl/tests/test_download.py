import hashlib
import os

import pytest
import requests

from ssdl.download import download_pdf, file_hash, safe_filename


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
