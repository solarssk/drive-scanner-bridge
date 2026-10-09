"""Check the Markdown documentation for the mistakes that went unnoticed before.

Run from anywhere: `python3 scripts/check_docs.py`. It exits 1 and lists every problem. The same
checks run as a test in the unit-test job, so a documentation drift fails the required check.

Checks: relative links and #anchors resolve, code fences are balanced, Mermaid blocks start with
a known diagram type, no em dash or " -- " in prose, lowercase kebab-case file names in `docs/`,
a README in each folder that needs one, nested AGENTS.md files have a CLAUDE.md stub that
imports them, and every setting of the service is listed in docs/configuration.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
# History keeps the wording it had when it was released.
SKIP_FILES = {"CHANGELOG.md"}
FOLDERS_WITH_README = ["docs", "docs/roadmap", "uploader", "scripts", ".github/workflows"]
CONVENTIONAL_NAMES = {"README.md", "AGENTS.md", "CLAUDE.md"}
MERMAID_TYPES = (
    "flowchart", "graph", "sequenceDiagram", "stateDiagram", "classDiagram", "erDiagram",
    "gantt", "pie", "journey", "mindmap", "timeline",
)
FENCE = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
KEBAB = re.compile(r"[a-z0-9][a-z0-9.\-]*\.md")
EM_DASH = chr(0x2014)


def slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    text = re.sub(r"[^\w\- ]", "", heading.replace("`", "").strip().lower())
    return text.replace(" ", "-")


def anchors_of(text: str) -> set[str]:
    """Every anchor GitHub generates for the headings of a page, in document order.

    A repeated heading gets a numeric suffix: the second "Configuration" is `configuration-1`.
    """
    seen: dict[str, int] = {}
    anchors = set()
    for heading in HEADING.findall(_prose(text)):
        base = slug(heading)
        count = seen.get(base, 0)
        anchors.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return anchors


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.md")
        if not (set(p.relative_to(root).parts) & SKIP_DIRS) and p.name not in SKIP_FILES
    )


def _prose(text: str) -> str:
    return FENCE.sub("", text)


def check_links(root: Path, files: list[Path]) -> list[str]:
    anchors = {f: anchors_of(f.read_text(encoding="utf-8")) for f in files}
    problems = []
    for f in files:
        for link in LINK.findall(_prose(f.read_text(encoding="utf-8"))):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, anchor = link.partition("#")
            target = f if not path else (f.parent / path).resolve()
            rel = f.relative_to(root)
            if not target.exists():
                problems.append(f"{rel}: link to a missing file: {link}")
            elif anchor and target.suffix == ".md":
                if target not in anchors:
                    anchors[target] = anchors_of(target.read_text(encoding="utf-8"))
                if anchor not in anchors[target]:
                    problems.append(f"{rel}: link to a missing anchor: {link}")
    return problems


def check_blocks(root: Path, files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(root)
        if len(re.findall(r"^```", text, re.MULTILINE)) % 2:
            problems.append(f"{rel}: a code fence is not closed")
        for block in re.findall(r"^```mermaid\n(.*?)^```", text, re.MULTILINE | re.DOTALL):
            first = next((ln.strip() for ln in block.splitlines() if ln.strip()), "")
            if not first.startswith(MERMAID_TYPES):
                problems.append(f"{rel}: a mermaid block does not start with a diagram type: {first[:40]!r}")
    return problems


def check_style(root: Path, files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        prose = _prose(f.read_text(encoding="utf-8"))
        if EM_DASH in prose or " -- " in prose:
            problems.append(f"{f.relative_to(root)}: an em dash or ' -- ' in prose (use a period, comma or colon)")
    return problems


def check_layout(root: Path) -> list[str]:
    problems = []
    for path in (root / "docs").rglob("*.md") if (root / "docs").is_dir() else []:
        if path.name not in CONVENTIONAL_NAMES and not KEBAB.fullmatch(path.name):
            problems.append(f"{path.relative_to(root)}: docs file names are lowercase kebab-case")
    for folder in FOLDERS_WITH_README:
        if (root / folder).is_dir() and not (root / folder / "README.md").exists():
            problems.append(f"{folder}/: needs a README.md that says what is in it")
    for agents in root.rglob("AGENTS.md"):
        if set(agents.relative_to(root).parts) & SKIP_DIRS:
            continue
        stub = agents.parent / "CLAUDE.md"
        if not stub.exists() or stub.read_text(encoding="utf-8").strip() != "@AGENTS.md":
            if agents.parent != root:  # the root CLAUDE.md has its own content and imports AGENTS.md
                problems.append(f"{agents.parent.relative_to(root)}/: CLAUDE.md must contain exactly '@AGENTS.md'")
    root_claude = root / "CLAUDE.md"
    if (root / "AGENTS.md").exists() and root_claude.exists():
        if "@AGENTS.md" not in root_claude.read_text(encoding="utf-8"):
            problems.append("CLAUDE.md: must import AGENTS.md with '@AGENTS.md'")
    return problems


def check_settings(root: Path) -> list[str]:
    config = root / "uploader/scanner_drive_bridge/config.py"
    doc = root / "docs/configuration.md"
    if not (config.exists() and doc.exists()):
        return []
    text = doc.read_text(encoding="utf-8")
    setting = re.compile(r'(?:_get_\w+|_read_secret|environ\.get)\(\s*"([A-Z][A-Z0-9_]+)"')
    names = set(setting.findall(config.read_text(encoding="utf-8")))
    compose = root / "docker-compose.yml"
    if compose.exists():
        names |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]+)[:?\-]", compose.read_text(encoding="utf-8")))
    return [
        f"docs/configuration.md: setting {name} is not documented"
        for name in sorted(names)
        if f"`{name}`" not in text and f"`{name}_FILE`" not in text
    ]


def check(root: Path) -> list[str]:
    files = markdown_files(root)
    return (
        check_links(root, files) + check_blocks(root, files) + check_style(root, files)
        + check_layout(root) + check_settings(root)
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems = check(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} documentation problem(s)", file=sys.stderr)
        return 1
    print(f"documentation OK ({len(markdown_files(root))} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
