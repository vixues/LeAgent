"""Tests for edit/patch did-you-mean helpers."""

from leagent.tools.project.edit_hints import find_closest_lines, format_no_match_hint


def test_find_closest_lines_single_line() -> None:
    text = "alpha\nbeta line\ngamma\n"
    matches = find_closest_lines(text, "beta lin", threshold=0.5)
    assert matches
    assert matches[0]["line"] == 2


def test_format_no_match_hint_includes_closest() -> None:
    text = "def foo():\n    return 1\n"
    payload = format_no_match_hint(
        rel_path="x.py",
        needle="return 2",
        file_text=text,
        base_message="old_string not found",
    )
    assert payload["patch_hint"]["closest_matches"]
    assert payload["path"] == "x.py"
