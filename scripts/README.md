# scripts

**In short:** helper scripts for the repository itself, not part of the service or the image.

| Script | Used by | Purpose |
|---|---|---|
| `format_release_notes.py` | `.github/workflows/release.yml` | Builds the GitHub Release notes for a version from its CHANGELOG section |

## format_release_notes.py

```bash
python3 scripts/format_release_notes.py 0.1.4 > release-notes.md
```

- Takes a plain `X.Y.Z` version. Anything else is rejected.
- Reads the `## [X.Y.Z] - YYYY-MM-DD` section of `CHANGELOG.md`, adds an icon to each
  subsection heading, and appends the image name and useful links.
- Fails if the CHANGELOG has no section for that version, so a release cannot be created
  from an empty entry.

Tests are in `uploader/tests/test_release_notes.py`, and they run against the real
CHANGELOG headings. Lint covers this folder: `ruff check . ../scripts` from `uploader/`.
