# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `AGENTS.md` (commands, code and workflow rules, and what an agent must not do) and a
  `CLAUDE.md` that imports it, following the playbook. `uploader/`, `.github/` and `docs/` have
  their own nested `AGENTS.md` (the closest file wins), each with a `CLAUDE.md` that imports it.
- A `README.md` in `docs/` (an index by task), `docs/roadmap/`, `uploader/`, `scripts/` and
  `.github/workflows/` (what each workflow does and whether it can block a merge).
- Mermaid diagrams (data flow, file states, crash recovery, when a file is complete, the
  release flow, failure recovery, secrets, CI) and GitHub callouts in the docs.
- `docs/configuration.md`: every setting with its default, whether `.env` can set it, and what
  it does (the README never listed them all).

### Changed

- The README was about 600 lines and held everything. It is now a short front page (what the
  project is and is not, quick start, the most common settings, security at a glance) that
  follows the playbook README standard. The rest moved, rewritten for clarity, into
  `docs/architecture.md`, `deployment.md`, `security.md`, `troubleshooting.md`,
  `synology-client.md` and `development.md`. The README title now matches the repository name.
  References in comments and docs point at the new pages. `docs/MAINTENANCE.md` is now
  `docs/maintenance.md` (all docs use lowercase file names) and the release process moved to
  `docs/releasing.md`. The release notes link to it.

## [0.1.4] - 2026-10-09

Fixes retention cleanup deleting a re-scanned file; also ships the release-automation hardening and the documentation audit.

### Changed

- SonarCloud and Codecov are report-only signals, as in the owner's other repositories: the
  external `SonarCloud Code Analysis` and `codecov/patch` checks and the `Code quality` job are no
  longer required status checks, and their steps use `continue-on-error`. Dependabot PRs cannot
  read repository secrets, so those two external checks were never posted and every such PR sat
  `BLOCKED`; they are now mergeable once `Unit tests`, `Build uploader image` and
  `Validate docker-compose.yml` are green. The Dependabot secrets store is not needed.
- Release automation hardened after an independent review of its first real run (0.1.3, which
  was not affected):
  - one failed API call while waiting for the image run no longer aborts the wait;
  - `Release` run by hand refuses any branch except `main`;
  - a push that does not move the version says whether that version is already tagged, and warns
    when it is not (a fix merged after a failed release run releases nothing by itself);
  - the `Build, scan, publish` dry run now also runs on release PRs, so a fixable CRITICAL/HIGH
    finding shows up before the tag exists;
  - the documented recovery for a failed image run now separates transient causes (run
    `Publish image` again) from findings in the tagged files (ship the next patch version).

- `docker-compose.yml` now forwards `HEALTHCHECK_MAX_LOOP_AGE_SECONDS` and
  `HEALTHCHECK_MAX_BACKLOG_AGE_SECONDS` from `.env` (the README documented them, but only the
  built-in defaults could take effect). The defaults are unchanged.

### Fixed

- Stale or wrong documentation corrected: a heartbeat command that needs `cat`, which the
  distroless image does not have; a scan command and a frozen scan result from the Docker Scout
  era (the project scans with Trivy); a "build context" that compose no longer has; comments that
  pointed at a SECURITY.md section that does not exist; and the list of PR triggers of the image
  dry run. The released milestones are no longer repeated in the roadmap list.
- An unused counter in a test fake, and an unused `caplog` parameter that now asserts the warning
  it was meant to check. A docstring in `worker.py` no longer claims that startup reconciliation
  cleans up leftover local files (it does not; the next stability poll does).
- The unit-test job no longer checks out the full git history, which nothing in it uses.
- Local retention cleanup (`DELETE_AFTER_UPLOAD=false`) could delete a fresh scan that reused the
  name of an expired upload: it removed whatever file had that name without checking its content,
  and the stale record also stayed behind, so re-scanning the same document (e.g. after deleting
  it from Drive) was removed on arrival and never uploaded. Cleanup now checks the content hash,
  never touches a file that no longer matches, and drops the record once the local copy is gone
  (or was already gone); a record is kept when the file cannot be removed, and a failing record
  delete no longer stops the worker. Records are also kept while the inbox volume is missing and
  while a byte-identical copy under another name is still kept there.
- A `Publish image` run started by hand from `main` stamped `org.opencontainers.image.revision`
  with main's tip instead of the commit it built (as happened to 0.1.1). The label now records
  the checked-out commit.

## [0.1.3] - 2026-10-09

Releases are now automatic. The runtime code is identical to 0.1.2.

### Added

- Releases are automatic. Merging a release PR to `main` (version bumped, matching
  `## [X.Y.Z] - date` CHANGELOG entry) now creates the git tag and the GitHub Release (notes
  built from the CHANGELOG by `scripts/format_release_notes.py`), publishes the image and closes
  the milestone, but only after the image run it dispatched has finished successfully
  (`release.yml`; a manual run on the same version cannot be mistaken for it). A version
  that disagrees between `pyproject.toml`, `__version__`, the compose image tag and the CHANGELOG
  fails the run and releases nothing.

### Changed

- `Publish image` never overwrites a version that is already on ghcr.io, so a retried run cannot
  change the digest someone has deployed.

## [0.1.2] - 2026-10-08

The container image is now published to ghcr.io. The runtime code is identical to 0.1.1.
0.1.1 itself was published to ghcr.io by hand (a manual run of the workflow, which is why its
`org.opencontainers.image.revision` label names the `main` commit of that run rather than the
tag's commit); from this release on a pushed tag publishes the image automatically.

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
