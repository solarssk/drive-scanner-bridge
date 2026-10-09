"""Check a pull request's "Documentation impact" declaration against its own diff.

Same rule as the playbook's scripts/check-pr-docs-impact.mjs (ci-cookbook #12): the PR
description must select exactly one of "Docs updated" or "No doc update needed: <reason>",
and the choice must agree with whether a documentation path really changed.

Runs only for pull_request events. The description reaches this script through the event
file, never through a workflow expression, so it is data and not code.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

DOCS_UPDATED = re.compile(r"^- \[[xX]\] Docs updated\s*$", re.MULTILINE)
NO_DOC_UPDATE = re.compile(r"^- \[[xX]\] No doc update needed: (?!<state the reason>\s*$)\S.+$", re.MULTILINE)

DOC_FILE_NAMES = {"README.md", "AGENTS.md", "CLAUDE.md", "SECURITY.md", "CONTRIBUTING.md"}
DOC_FILES = {".env.example"}


def read_declaration(body: str) -> tuple[bool, bool]:
    """Return (docs_updated, no_doc_update) as selected in the description."""
    return bool(DOCS_UPDATED.search(body)), bool(NO_DOC_UPDATE.search(body))


def is_doc_path(path: str) -> bool:
    """True for the files that document behavior, configuration or deployment."""
    return path.startswith("docs/") or path in DOC_FILES or Path(path).name in DOC_FILE_NAMES


def evaluate(body: str, changed_files: Iterable[str]) -> Optional[str]:
    """Return an error message, or None when the declaration is consistent with the diff."""
    docs_updated, no_doc_update = read_declaration(body)
    if docs_updated == no_doc_update:
        return "Select exactly one Documentation impact declaration, with a real reason if none is needed."
    docs_changed = any(is_doc_path(path) for path in changed_files)
    if docs_updated and not docs_changed:
        return "'Docs updated' is selected but none of the documentation paths actually changed."
    if no_doc_update and docs_changed:
        return "A documentation path changed; select 'Docs updated' instead."
    return None


def _git() -> str:
    # The absolute path is deliberate: it avoids resolving an executable through PATH on the
    # hosted runner, which installs git here. Fall back to PATH for local runs.
    return "/usr/bin/git" if os.path.exists("/usr/bin/git") else "git"


def changed_files(base_sha: str, head_sha: str) -> list[str]:
    out = subprocess.run(
        [_git(), "diff", "--name-only", f"{base_sha}...{head_sha}"], check=True, capture_output=True, text=True
    ).stdout
    return [line for line in out.splitlines() if line]


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return 0
    pull_request = json.loads(Path(event_path).read_text(encoding="utf-8")).get("pull_request")
    if not pull_request:
        return 0
    # Automated dependency PRs cannot fill in a hand-written template. Match the author, never
    # the branch name: anyone can open a PR from a branch called dependabot/...
    if (pull_request.get("user") or {}).get("login", "") == "dependabot[bot]":
        return 0
    error = evaluate(
        pull_request.get("body") or "",
        changed_files(pull_request["base"]["sha"], pull_request["head"]["sha"]),
    )
    if error:
        print(error, file=sys.stderr)
        return 1
    print("Documentation impact declaration is consistent with the diff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
