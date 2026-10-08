"""Tests for scripts/format_release_notes.py, which turns CHANGELOG.md into GitHub Release notes."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("format_release_notes", ROOT / "scripts" / "format_release_notes.py")
frn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frn)

SAMPLE = """# Changelog

## [Unreleased]

## [1.2.3] - 2026-01-02

A short intro that explains the release.

### Added

- First new thing.

### Fixed

- A bug.

### Removed

## [1.2.2] - 2025-12-31

### Changed

- Something older.
"""


def test_extract_section_stops_at_the_next_version():
    body = frn.extract_section(SAMPLE, "1.2.3")
    assert "First new thing." in body
    assert "Something older." not in body


def test_extract_section_missing_version_exits():
    with pytest.raises(SystemExit):
        frn.extract_section(SAMPLE, "9.9.9")


def test_notes_have_header_intro_emoji_sections_and_image():
    notes = frn.build_release_notes("1.2.3", SAMPLE)
    assert notes.startswith("## \U0001f680 drive-scanner-bridge 1.2.3")
    assert "A short intro that explains the release." in notes
    assert "### \u2728 Added" in notes
    assert "### \U0001f41b Fixed" in notes
    assert "ghcr.io/solarssk/drive-scanner-bridge:1.2.3" in notes
    assert notes.endswith("\n")


def test_empty_subsections_are_left_out():
    assert "Removed" not in frn.build_release_notes("1.2.3", SAMPLE)


def test_unknown_subsection_heading_is_kept():
    changelog = "## [1.0.0] - 2026-01-01\n\n### Notes\n\n- hello\n"
    assert "### \U0001f4cc Notes" in frn.build_release_notes("1.0.0", changelog)


@pytest.mark.parametrize("version", ["v1.2.3", "1.2", "1.2.3-rc1", "1.2.3.4", ""])
def test_only_plain_release_versions_are_accepted(version):
    with pytest.raises(SystemExit):
        frn.build_release_notes(version, SAMPLE)


def test_every_released_version_in_the_real_changelog_formats():
    """Guards the heading format release.yml depends on: a drifted heading would silently
    skip a release, so each released section must produce notes."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", changelog, flags=re.MULTILINE)
    assert versions, "no released sections found in CHANGELOG.md"
    for version in versions:
        assert f"drive-scanner-bridge:{version}" in frn.build_release_notes(version)
