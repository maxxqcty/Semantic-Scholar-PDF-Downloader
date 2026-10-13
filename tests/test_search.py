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
