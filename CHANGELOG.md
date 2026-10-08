# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- The uploader image is published to `ghcr.io/solarssk/drive-scanner-bridge` (`linux/amd64` and
  `linux/arm64`) when a release tag is pushed, after a Trivy scan of each platform that
  blocks on any CRITICAL or HIGH finding with a fix (`release-image.yml`).

### Changed

- `docker-compose.yml` pulls `ghcr.io/solarssk/drive-scanner-bridge:<version>` instead of expecting a locally
  built `scanner-drive-bridge-uploader` image. Building locally still works under the new name.

## [0.1.1] - 2026-10-08

Stabilization of the current two-container architecture. No behavior change to the
bridge itself; the changes are the runtime base, dependency pinning, CI and governance.

### Changed

- Runtime base image moved from `distroless/python3-debian12` to `python3-debian13`, and
  the builder from `python:3.11-slim` to `python:3.13-slim`; both are pinned by digest.
  The weekly image scan had been red since 2026-09-14 (25 fixable HIGH findings that the
  debian12 image never picked up); on debian13 it scans clean. The Python floor is now
  3.13 (`requires-python`, CI, Sonar), matching what ships.
- Runtime dependencies are hash-locked: `uploader/requirements.in` and the generated
  `requirements.txt`. The Docker build installs them with `--require-hashes`, and CI
  installs the same lock before running tests and checks, with `pip check` against a
  Docker-style `--no-deps` install, that the lock covers everything `pyproject.toml` declares.
- Dependabot groups updates (one PR per ecosystem per week) and now also covers the
  Docker base images. Python minor/major jumps of the builder image are ignored on purpose.
- GitHub Actions bumped: `docker/build-push-action` 7.4.0, `docker/setup-buildx-action`
  4.4.1, `SonarSource/sonarqube-scan-action` 8.3.0, `codecov/codecov-action` 7.1.1.
- CI runs `ruff` and `mypy` in the `Unit tests` job, adds CodeQL (python and the Actions
  workflows), a `concurrency:` group in every workflow, and builds a PR commit once
  (push trigger limited to `main`).
- Eight SonarCloud code smells fixed: `StabilityTracker.poll()` split so its Cognitive
  Complexity is under the limit, and repeated string literals turned into constants.

### Fixed

- `aquasecurity/trivy-action` and `codecov/codecov-action` were pinned to the SHA of
  the annotated tag *object*; they now pin the tag's commit SHA.
- `Worker._cleanup_expired_local_copies` multiplied the optional `local_retention_hours`
  without a guard (only its caller checked it); found by the new type check.
- Four `assert False` in tests, which `python -O` strips.

### Added

- `docs/roadmap/0.2.0-single-container-smb1.md` (the plan for the next release) and
  `docs/MAINTENANCE.md` (playbook checklist, conventions, release process).
- A structured bug-report issue form, a pull request template and a release badge.

## [0.1.0] - 2026-09-09

First tagged release. Nothing was ever formally released before this --
`0.2.0` had been used only as an internal/Docker-image version string,
with no matching git tag or GitHub Release, so numbering restarts here
at `0.1.0` as the actual first release.

### Added

- The bridge itself: watches a legacy SMB1 scanner's inbox and uploads
  new files to Synology Drive via its HTTPS API, with idempotent
  content-hash dedup, file-stabilization detection, and retry with
  backoff. See the README for the full design rationale.
- Container hardening: distroless multi-stage image, non-root fixed UID,
  `read_only` root filesystem, `cap_drop: [ALL]`, `no-new-privileges`,
  no published ports, network-isolated from the legacy SMB1 container.
- `LICENSE` (MIT).
- `SECURITY.md` documenting private vulnerability reporting.
- `CONTRIBUTING.md` documenting the milestone/label/assignee-before-PR
  convention and branch naming.
- `CODEOWNERS`.
- `.github/dependabot.yml` for automated `pip` and `github-actions`
  dependency updates.
- `.coderabbit.yaml` disabling CodeRabbit's automatic per-PR review.
- `.github/workflows/ci.yml`: unit tests, image build, compose-config
  validation, `pip-audit`, and a CRITICAL-only container CVE gate
  (actions pinned to commit SHAs, least-privilege `permissions` block).
- `.github/workflows/weekly-image-scan.yml`: full CRITICAL+HIGH container
  CVE scan on the same weekly cadence as Dependabot, unblocked from PRs.
- SonarQube Cloud CI-based analysis and Codecov coverage + test-results
  reporting, both gated on a `code-quality` CI job kept separate from
  `Unit tests` so an external service hiccup can't be mistaken for a
  code regression.
- README table of contents, CI/license badges, and a License section.

### Removed

- The dead/no-op `SYNOLOGY_DSM_VERSION` setting (documented and read into
  `Config`, but never actually consulted -- DSM API versions are always
  discovered dynamically via `SYNO.API.Info`).
