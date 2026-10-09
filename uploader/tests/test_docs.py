"""The repository's own documentation must pass scripts/check_docs.py, and the checker must catch what it claims to."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts" / "check_docs.py")
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)


def test_the_repository_documentation_is_consistent():
    assert cd.check(ROOT) == []


def _tree(tmp_path, files):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


def test_slug_matches_github_anchors():
    assert cd.slug("Why the bridge exists") == "why-the-bridge-exists"
    assert cd.slug("The `uploader` image (v2)") == "the-uploader-image-v2"
    assert cd.slug("Login works, but error_code 103") == "login-works-but-error_code-103"


def test_repeated_headings_get_githubs_numeric_suffixes():
    text = "# T\n\n## Configuration\n\n## Other\n\n## Configuration\n\n```md\n## Configuration\n```\n## Configuration\n"
    assert cd.anchors_of(text) == {"t", "configuration", "other", "configuration-1", "configuration-2"}


def test_a_link_to_a_repeated_heading_is_valid_only_with_its_suffix(tmp_path):
    root = _tree(tmp_path, {
        "README.md": "# T\n\n[first](a.md#setup)\n[second](a.md#setup-1)\n[third](a.md#setup-2)\n",
        "a.md": "# A\n\n## Setup\n\n## Setup\n",
    })
    problems = cd.check_links(root, cd.markdown_files(root))
    assert problems == ["README.md: link to a missing anchor: a.md#setup-2"]


def test_broken_file_and_anchor_links_are_reported(tmp_path):
    root = _tree(tmp_path, {
        "README.md": "# T\n\n[ok](docs/a.md#real)\n[bad file](docs/missing.md)\n[bad anchor](docs/a.md#nope)\n",
        "docs/a.md": "# A\n\n## Real\n",
    })
    problems = cd.check_links(root, cd.markdown_files(root))
    assert any("missing file: docs/missing.md" in p for p in problems)
    assert any("missing anchor: docs/a.md#nope" in p for p in problems)
    assert not any("docs/a.md#real" in p for p in problems)


def test_links_inside_code_fences_are_ignored(tmp_path):
    root = _tree(tmp_path, {"README.md": "# T\n\n```md\n[x](nowhere.md)\n```\n"})
    assert cd.check_links(root, cd.markdown_files(root)) == []


def test_unclosed_fence_and_bad_mermaid_are_reported(tmp_path):
    root = _tree(tmp_path, {
        "a.md": "# A\n\n```bash\nls\n",
        "b.md": "# B\n\n```mermaid\nnot a diagram\n```\n",
        "c.md": "# C\n\n```mermaid\nflowchart LR\n  A --> B\n```\n",
    })
    problems = cd.check_blocks(root, cd.markdown_files(root))
    assert any(p.startswith("a.md") and "not closed" in p for p in problems)
    assert any(p.startswith("b.md") and "mermaid" in p for p in problems)
    assert not any(p.startswith("c.md") for p in problems)


def test_dashes_are_reported_in_prose_but_not_in_code_or_diagrams(tmp_path):
    root = _tree(tmp_path, {
        "a.md": "# A\n\nThis \u2014 is wrong.\n",
        "b.md": "# B\n\nFine prose.\n\n```mermaid\nflowchart LR\n  A -- yes --> B\n```\n",
    })
    problems = cd.check_style(root, cd.markdown_files(root))
    assert [p.split(":")[0] for p in problems] == ["a.md"]


def test_layout_rules(tmp_path):
    root = _tree(tmp_path, {
        "docs/Bad_Name.md": "# x\n",
        "docs/good-name.md": "# x\n",
        "docs/roadmap/plan.md": "# x\n",
        "uploader/AGENTS.md": "# x\n",
        "AGENTS.md": "# root\n",
        "CLAUDE.md": "no import here\n",
    })
    problems = cd.check_layout(root)
    assert any("Bad_Name.md" in p for p in problems)
    assert not any("good-name.md" in p for p in problems)
    assert any(p.startswith("docs/:") for p in problems)
    assert any(p.startswith("docs/roadmap/:") for p in problems)
    assert any("uploader" in p and "CLAUDE.md" in p for p in problems)
    assert any(p.startswith("CLAUDE.md:") for p in problems)


def test_undocumented_setting_is_reported(tmp_path):
    root = _tree(tmp_path, {
        "uploader/scanner_drive_bridge/config.py": (
            'x = _get_int("NEW_SETTING", 1)\ny = _get_bool("OLD_SETTING", True)\n'
        ),
        "docs/configuration.md": "| `OLD_SETTING` | true |\n",
    })
    assert cd.check_settings(root) == ["docs/configuration.md: setting NEW_SETTING is not documented"]
