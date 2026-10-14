from importlib.metadata import version

import ssdl


def test_version_matches_installed_metadata():
    assert ssdl.__version__ == version("semantic-scholar-pdf-downloader")


def test_version_is_pinned():
    assert ssdl.__version__ == "3.0.0"
