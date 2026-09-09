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
- **Before merging:** all three required CI checks (`Unit tests`,
  `Build uploader image`, `Validate docker-compose.yml`) must pass --
  branch protection on `main` enforces this.
- **Running tests locally:** `cd uploader && pip install -e ".[dev]" && pytest -q`.

For anything touching credential handling, DSM authentication, or the
SMB1/Samba legacy-auth settings, see [SECURITY.md](SECURITY.md) instead of
opening a public issue or PR discussion.
