#!/usr/bin/env python3
"""Format a CHANGELOG.md section into GitHub Release notes.

Usage: format_release_notes.py <version>      e.g. 0.1.3

Prints the notes to stdout. Exits non-zero when CHANGELOG.md has no section for the version.
"""

from __future__ import annotations

import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
IMAGE = "ghcr.io/solarssk/drive-scanner-bridge"
REPO_URL = "https://github.com/solarssk/drive-scanner-bridge"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

SECTION_EMOJI = {
    "added": "✨ Added",
    "changed": "🔄 Changed",
    "deprecated": "⚠️ Deprecated",
    "removed": "🗑️ Removed",
    "fixed": "🐛 Fixed",
    "security": "🔒 Security",
}


def extract_section(changelog: str, version: str) -> str:
    pattern = rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    match = re.search(pattern, changelog, flags=re.MULTILINE | re.DOTALL)
    if not match:
        raise SystemExit(f"No CHANGELOG section found for version {version}")
    return match.group(1).strip()


def split_subsections(body: str) -> tuple[list[str], OrderedDict[str, list[str]]]:
    """Return the intro lines before the first '### ' heading and the '### ' sections."""
    intro: list[str] = []
    sections: OrderedDict[str, list[str]] = OrderedDict()
    current: str | None = None
    for raw in body.splitlines():
        line = raw.rstrip()
        if line.startswith("### "):
            current = line.removeprefix("### ").strip()
            sections[current] = []
        elif current is None:
            intro.append(line)
        else:
            sections[current].append(line)
    return intro, sections


def trim(lines: list[str]) -> list[str]:
    out = list(lines)
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return out


def image_block(version: str) -> str:
    return "\n".join(
        [
            "---",
            "",
            "## 🐳 Container image",
            "",
            "```text",
            f"{IMAGE}:{version}",
            "```",
            "",
            "Platforms: `linux/amd64`, `linux/arm64`. **Portainer / production:** pin this exact tag; "
            "no `latest` is published.",
            "",
            "## 📚 Useful links",
            "",
            f"- [Full CHANGELOG]({REPO_URL}/blob/main/CHANGELOG.md)",
            f"- [README]({REPO_URL}#readme)",
            f"- [Releasing and maintenance]({REPO_URL}/blob/main/docs/releasing.md)",
        ]
    )


def build_release_notes(version: str, changelog: str | None = None) -> str:
    if not VERSION_RE.match(version):
        raise SystemExit(f"Not a release version (expected X.Y.Z): {version}")
    text = changelog if changelog is not None else CHANGELOG.read_text(encoding="utf-8")
    intro, sections = split_subsections(extract_section(text, version))

    parts = [f"## 🚀 drive-scanner-bridge {version}"]
    intro_lines = trim(intro)
    if intro_lines:
        parts += ["", *intro_lines]
    for heading, lines in sections.items():
        content = trim(lines)
        if not content:
            continue
        parts += ["", f"### {SECTION_EMOJI.get(heading.lower(), f'📌 {heading}')}", "", *content]
    parts += ["", image_block(version)]
    return "\n".join(parts).strip() + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: format_release_notes.py <version>   e.g. 0.1.3")
    sys.stdout.write(build_release_notes(sys.argv[1]))


if __name__ == "__main__":
    main()
