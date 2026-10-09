# AGENTS.md

This file is for AI coding agents, and for anyone who wants a checklist. If you are looking
for an overview of what this project is, read [README.md](README.md) first. This file
assumes you know that and goes straight to instructions.

## What this repository is

A Python service (`drive-scanner-bridge`) that uploads scans from a legacy SMB1 scanner to
Synology Drive through the Drive API. In 0.1.x it runs as two containers: a Samba container
(`dperson/samba`) that the scanner writes to, and the uploader in `uploader/`. The plan to
replace Samba with an embedded SMB1 server (one container) is in
[docs/roadmap/0.2.0-single-container-smb1.md](docs/roadmap/0.2.0-single-container-smb1.md).
Do not start that work unless you were asked to.

## Repository standard

This repository follows the solarssk engineering standard: https://github.com/solarssk/playbook
Tier: 2 (see playbook/docs/tiers.md)

Do not add Tier 3 machinery (DAST, SBOM, a wiki) unless the scope grows.

## Commands

Run from `uploader/` with Python 3.13. These are exactly the commands CI runs:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # once
.venv/bin/ruff check . ../scripts
.venv/bin/mypy
.venv/bin/pytest -q
```

- Compose renders without errors: `docker compose config` (needs a `.env`, copy
  `.env.example`).
- Workflows are linted with `actionlint` in CI. Run it when you touch `.github/workflows/`.

## Code

- Python 3.13, line length 120, ruff rules `E,F,I,B`, mypy clean.
- The only runtime dependency is `requests`. Do not add dependencies without a reason that
  is written down in the pull request. Runtime dependencies are hash-locked; see
  [docs/maintenance.md](docs/maintenance.md#python-dependencies) before changing them.
- Secrets must never reach a log, an exception message or a URL query string.
- The image is distroless: it has no shell, no `cat`, no `sh`. Use `python3` in any command
  you document or run inside the container.
- A file is deleted only after its `uploaded` state is committed to SQLite, and a failed
  upload is never assumed to have failed on the server. Read
  [docs/architecture.md](docs/architecture.md) before changing `worker.py` or `state.py`.
- Tests mock the Synology API. They must not make network calls.

## Issues, pull requests and releases

- Every issue and pull request gets an assignee, at least one label and a milestone named
  like the version. Use the `.github/pull_request_template.md` checklist.
- Branch names are `<type>/<short-description>` with type `fix`, `feature`, `maintenance`,
  `security`, `docs` or `release`.
- Add an entry under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for anything visible to
  someone running the bridge. Never edit released entries: insert under the `[Unreleased]`
  heading itself, not next to the text of another entry, which may already belong to a release.
- GitHub Actions are pinned to the full commit SHA of the tag (the peeled `^{}` commit, not
  the tag object), with the version as a trailing comment.
- A release is automatic. Merging a release pull request creates the tag, the GitHub
  Release, the image on ghcr.io and closes the milestone. Do not create tags or Releases by
  hand. The release pull request bumps the version in `uploader/pyproject.toml`,
  `uploader/scanner_drive_bridge/__init__.py`, the `image:` tag in `docker-compose.yml`, every
  image tag in the docs (`grep -rn "<old version>" README.md docs`), and turns `[Unreleased]`
  into `## [X.Y.Z] - YYYY-MM-DD`. Details: [docs/releasing.md](docs/releasing.md).
- Required checks on `main`: `Unit tests`, `Build uploader image`,
  `Validate docker-compose.yml`. SonarCloud and Codecov are report-only. Codecov counts every
  changed line toward patch coverage, so avoid cosmetic edits to executable lines the tests
  do not reach.

## Documentation

Depth belongs in `docs/`, and the README stays a front page. Writing, structure and file-name
rules are in [docs/AGENTS.md](docs/AGENTS.md). When behavior, a setting or a deployment step
changes, update the docs in the same pull request.

## What you must not do

- Do not merge pull requests, force-push, or bypass branch protection. The owner merges.
- Do not change repository settings (branch protection, secrets, webhooks). Hand the owner
  the exact command instead.
- Do not make CI less strict (fewer required checks, `continue-on-error`) without the
  owner's explicit approval of that exact change.
- Do not delete tags, releases, milestones or labels without asking first.

## Map of the repository

| Path | Purpose |
|---|---|
| `uploader/` | The service, its tests and its `Dockerfile` |
| `scripts/` | Release-notes script used by the release workflow |
| `docs/` | Topic documentation; index in [docs/README.md](docs/README.md) |
| `docs/roadmap/` | Plans for what comes next |
| `.github/workflows/` | CI, CodeQL, image publishing, release, weekly image scan |
| `docker-compose.yml`, `.env.example` | Deployment files |

## Nested instructions

Some folders have their own `AGENTS.md`. The closest file to the one you are editing wins,
and explicit instructions from the user win over all of them. Each has a `CLAUDE.md` that
imports it, so Claude Code loads it too.

| Folder | Read it before you |
|---|---|
| [`uploader/`](uploader/AGENTS.md) | change the service or its tests |
| [`.github/`](.github/AGENTS.md) | change a workflow, a template or Dependabot |
| [`docs/`](docs/AGENTS.md) | write or restructure documentation |
