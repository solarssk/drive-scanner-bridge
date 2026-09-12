# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
