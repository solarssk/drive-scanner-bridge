# Contributing

This is a personal-infrastructure project, maintained solo and best-effort.
There's no formal review process, but a few light conventions keep issues
and PRs readable months later:

- **Before opening a PR:** assign yourself, attach at least one label
  (`security`, `ci`, `governance`, `bug`, `enhancement`, `documentation`,
  ...), and attach it to the current milestone if one is open. Dependabot's
  own PRs are exempt -- it labels and targets them automatically.
- **Branch naming:** `<type>/<short-description>`, e.g.
  `maintenance/governance-ci-hardening`. `type` is one of `fix`, `feature`,
  `maintenance`, `security`, `docs`, `release` (`release/x.y.z` for a release PR).
- **Before merging:** the required CI checks (`Unit tests`,
  `Build uploader image`, `Validate docker-compose.yml`) must pass -- branch
  protection on `main` enforces this. SonarCloud and Codecov report on every PR
  but are report-only signals, not merge gates (same as the owner's other repos).
- **Running tests locally:** `cd uploader && pip install -e ".[dev]" && pytest -q`.
- **Repo secrets:** `SONAR_TOKEN` and `CODECOV_TOKEN` are Actions secrets only.
  Dependabot-triggered runs and fork PRs cannot read them, so ci.yml's
  `code-quality` job skips those steps there and the PR stays mergeable once the
  required checks pass. Nothing needs to be added to the Dependabot secrets store.

For anything touching credential handling, DSM authentication, or the
SMB1/Samba legacy-auth settings, see [SECURITY.md](SECURITY.md) instead of
opening a public issue or PR discussion.

Maintenance conventions, the release process and the playbook checklist are in
[docs/MAINTENANCE.md](docs/MAINTENANCE.md). The roadmap is in [docs/roadmap/](docs/roadmap/).
