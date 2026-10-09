# scripts

**In short:** helper scripts for the repository itself, not part of the service or the image.

| Script | Used by | Purpose |
|---|---|---|
| `format_release_notes.py` | `.github/workflows/release.yml` | Builds the GitHub Release notes for a version from its CHANGELOG section |
| `check_pr_docs_impact.py` | `.github/workflows/docs-impact.yml` | Checks the "Documentation impact" choice in a PR description against the files the PR changes |
| `check_docs.py` | the unit-test job (`uploader/tests/test_docs.py`), or by hand | Checks links, anchors, code and Mermaid blocks, style, file names, folder READMEs and the settings table |

## format_release_notes.py

```bash
python3 scripts/format_release_notes.py 0.1.7 > release-notes.md
```

- Takes a plain `X.Y.Z` version. Anything else is rejected.
- Reads the `## [X.Y.Z] - YYYY-MM-DD` section of `CHANGELOG.md`, adds an icon to each
  subsection heading, and appends the image name and useful links.
- Fails if the CHANGELOG has no section for that version, so a release cannot be created
  from an empty entry.

Tests are in `uploader/tests/test_release_notes.py`, and they run against the real
CHANGELOG headings. Lint covers this folder: `ruff check . ../scripts` from `uploader/`.

## check_docs.py

```bash
python3 scripts/check_docs.py
```

Prints every problem and exits 1. It is also a test, so a documentation drift fails the required
`Unit tests` check. It does not render Mermaid; it only checks that each block starts with a
diagram type.

## check_pr_docs_impact.py

Follows the playbook's rule: the PR description selects exactly one of `Docs updated` or
`No doc update needed: <reason>`, and the choice must agree with the diff. Documentation paths
are `docs/`, `.env.example`, and any `README.md`, `AGENTS.md`, `CLAUDE.md`, `SECURITY.md` or
`CONTRIBUTING.md`. Dependabot PRs are exempt (matched by author, not by branch name). The
description reaches the script through the event file, never through a workflow expression.
