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
  `maintenance`, `security`.
- **Before merging:** all required CI checks (`Unit tests`,
  `Build uploader image`, `Validate docker-compose.yml`,
  `Code quality (Sonar + Codecov)`, `SonarCloud Code Analysis`,
  `codecov/patch`) must pass -- branch protection on `main` enforces this.
- **Running tests locally:** `cd uploader && pip install -e ".[dev]" && pytest -q`.
- **Repo secrets:** `SONAR_TOKEN` and `CODECOV_TOKEN` must also be added
  under Settings > Secrets and variables > **Dependabot** (same values as
  the Actions secrets) -- GitHub does not pass ordinary Actions secrets to
  Dependabot-triggered workflow runs, only a separate Dependabot-secrets
  store. Without that, every weekly Dependabot PR fails the Sonar/Codecov
  checks and can never merge. ci.yml's `code-quality` job skips its
  secret-backed steps cleanly rather than erroring when a token is absent,
  but SonarCloud's and Codecov's own external checks have no such skip and
  will simply never report on such a PR, leaving it permanently blocked.

For anything touching credential handling, DSM authentication, or the
SMB1/Samba legacy-auth settings, see [SECURITY.md](SECURITY.md) instead of
opening a public issue or PR discussion.
