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
