# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `LICENSE` (MIT).
- `SECURITY.md` documenting private vulnerability reporting.
- `.github/dependabot.yml` for automated `pip` and `github-actions`
  dependency updates.

### Changed

- Hardened CI: actions pinned to commit SHAs, a least-privilege
  `permissions` block, a `pip-audit` step, and a container CVE scan step.
- README gained a table of contents, badges, and a License section.

### Removed

- The dead/no-op `SYNOLOGY_DSM_VERSION` setting.

## [0.2.0]

Initial documented release.
