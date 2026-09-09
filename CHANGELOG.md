# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `LICENSE` (MIT).
- `SECURITY.md` documenting private vulnerability reporting.
- `CONTRIBUTING.md` documenting the milestone/label/assignee-before-PR
  convention and branch naming.
- `.github/dependabot.yml` for automated `pip` and `github-actions`
  dependency updates.
- `.coderabbit.yaml` disabling CodeRabbit's automatic per-PR review.
- `.github/workflows/weekly-image-scan.yml`: full CRITICAL+HIGH container
  CVE scan on the same weekly cadence as Dependabot, unblocked from PRs.
- SonarQube Cloud CI-based analysis and Codecov coverage reporting, both
  gated on a new `code-quality` CI job separate from `Unit tests` so an
  external service hiccup can't be mistaken for a code regression.

### Changed

- Hardened CI: actions pinned to commit SHAs, a least-privilege
  `permissions` block, a `pip-audit` step, and a container CVE scan step
  (CRITICAL blocks PRs; HIGH is covered by the weekly scan instead).
- README gained a table of contents, badges, and a License section, and
  its "0 Critical/High/Medium/Low" scan claim now points at the CI
  workflows that verify this continuously instead of standing as a
  static, point-in-time claim.
- `pytest` now runs with coverage (`pytest-cov`), uploaded as a build
  artifact and consumed by both Sonar and Codecov.

### Removed

- The dead/no-op `SYNOLOGY_DSM_VERSION` setting.

## [0.2.0]

Initial documented release.
