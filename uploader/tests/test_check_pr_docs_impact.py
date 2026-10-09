"""Tests for scripts/check_pr_docs_impact.py, the PR "Documentation impact" check."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_pr_docs_impact", ROOT / "scripts" / "check_pr_docs_impact.py")
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)

UPDATED = "## Documentation impact\n\n- [x] Docs updated\n- [ ] No doc update needed: <state the reason>\n"
NO_UPDATE = "- [ ] Docs updated\n- [x] No doc update needed: only CI wiring changed\n"


@pytest.mark.parametrize(
    "body, expected",
    [
        (UPDATED, (True, False)),
        (NO_UPDATE, (False, True)),
        ("- [ ] Docs updated\n- [ ] No doc update needed: <state the reason>\n", (False, False)),
        # The reason is required, and the template's own placeholder is not a reason.
        ("- [x] No doc update needed: <state the reason>\n", (False, False)),
        ("- [x] No doc update needed:\n", (False, False)),
        ("- [X] Docs updated\n", (True, False)),
        ("", (False, False)),
    ],
)
def test_read_declaration(body, expected):
    assert chk.read_declaration(body) == expected


@pytest.mark.parametrize(
    "path, expected",
    [
        ("docs/architecture.md", True),
        ("docs/roadmap/README.md", True),
        ("README.md", True),
        ("uploader/README.md", True),
        ("uploader/AGENTS.md", True),
        (".env.example", True),
        ("CHANGELOG.md", False),
        ("uploader/scanner_drive_bridge/worker.py", False),
        (".github/workflows/ci.yml", False),
        ("docker-compose.yml", False),
    ],
)
def test_is_doc_path(path, expected):
    assert chk.is_doc_path(path) is expected


def test_consistent_declarations_pass():
    assert chk.evaluate(UPDATED, ["docs/deployment.md", "uploader/x.py"]) is None
    assert chk.evaluate(NO_UPDATE, [".github/workflows/ci.yml", "CHANGELOG.md"]) is None


def test_both_or_neither_selected_fails():
    both = UPDATED.replace("- [ ] No doc update needed: <state the reason>", "- [x] No doc update needed: because")
    assert "exactly one" in chk.evaluate(both, ["docs/a.md"])
    assert "exactly one" in chk.evaluate("no declaration here", ["docs/a.md"])


def test_docs_updated_without_a_doc_change_fails():
    assert "none of the documentation paths" in chk.evaluate(UPDATED, ["uploader/x.py"])


def test_no_update_with_a_doc_change_fails():
    assert "select 'Docs updated'" in chk.evaluate(NO_UPDATE, ["README.md"])
