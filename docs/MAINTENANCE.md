# Maintenance guide

How this repository is kept in order. Source of truth for conventions that are not
obvious from the code. Contribution rules live in [CONTRIBUTING.md](../CONTRIBUTING.md);
this file records the playbook tier, the release process and the pitfalls already hit.

## Playbook tier

This repo follows the Admitto Standard (owner's cross-repo maintenance playbook):
a **single-purpose personal-infra tool that handles credentials**, so Tier 1, moving to
Tier 2. SonarCloud and Codecov are Tier 3 items that were added deliberately; do not add
more Tier 3 machinery (DAST, SBOM, wiki) unless the scope actually grows.

| Tier | Item | Status |
|---|---|---|
| 0 | LICENSE matching the README | done |
| 0 | `.github/CODEOWNERS` | done |
| 0 | Dependabot security updates on | done |
| 0 | Delete head branches on merge | done |
| 0 | Branch protection, enforced for admins | done |
| 1 | CI on push and PR (tests, image build, compose check) | done |
| 1 | Lint step (ruff) and typecheck (mypy) | done |
| 1 | Actions pinned to commit SHA with version comment | done (see "Pinning actions") |
| 1 | `permissions: contents: read` | done |
| 1 | Base images pinned by digest | done |
| 1 | Python dependencies hash-locked | done (`requirements.txt`) |
| 1 | SECURITY.md | done |
| 1 | One structured issue template | done |
| 2 | Dependency audit (`pip-audit`) | done |
| 2 | Secret scanning | done (GitHub native secret scanning + push protection) |
| 2 | SAST (CodeQL) on PR and weekly | done |
| 2 | Dependabot for every used ecosystem (pip, actions, docker) | done (pip, github-actions, docker) |
| 2 | Container scan, blocking | done (CRITICAL blocks PRs, weekly CRITICAL+HIGH, both platforms of the published image are scanned before push) |
| 2 | `concurrency:` group in every workflow | done |
| 2 | CONTRIBUTING.md, PR template, CODEOWNERS | done |
| 2 | Badge row (CI, release, license) | done |
| 3 | Coverage gate, quality gate | done (Codecov, SonarCloud) |

Statuses that name a PR become plain "done" once it merges. Keep this table current when an item changes status.

## Conventions

- Every issue and PR gets an **assignee**, at least one **label** and a **milestone**
  (Dependabot PRs excepted). Labels in use: `security`, `ci`, `governance`,
  `dependencies`, `github_actions`, `documentation`, `bug`, `enhancement`.
- Branch names: `<type>/<short-description>` with type `fix`, `feature`,
  `maintenance`, `security`, `docs`, `release`.
- One milestone per release, named exactly like the version (`0.1.1`). It is closed when
  the release is published.
- The owner merges PRs. Required checks are enforced for admins too (no bypass).

## Required status checks (branch protection on `main`)

`Unit tests`, `Build uploader image`, `Validate docker-compose.yml`,
`Code quality (Sonar + Codecov)`, `SonarCloud Code Analysis`, `codecov/patch`.

Renaming a job changes its check name; update the branch protection contexts in the same
change or every PR will wait forever for a check that no longer exists.

## Release process

A release is a git tag + GitHub Release and a container image on ghcr.io
(`ghcr.io/solarssk/drive-scanner-bridge:<version>`, `linux/amd64` + `linux/arm64`). Pushing the tag runs
`.github/workflows/release-image.yml`: it builds each platform, scans each one (CRITICAL or
HIGH with a fix blocks), and only then pushes.

1. Close or move every issue in the milestone.
2. Bump the version everywhere: `uploader/pyproject.toml`,
   `uploader/scanner_drive_bridge/__init__.py`, the `image:` tag in `docker-compose.yml`,
   and the README references (`grep -rn "<old version>"`).
3. `CHANGELOG.md`: turn `[Unreleased]` into `[x.y.z] - <date>`, add a fresh empty
   `[Unreleased]`.
4. Open a `release/x.y.z` PR; the owner merges it once CI is green on `main`.
5. Tag the merge commit (annotated, no `v` prefix, matching the image tag), publish the
   GitHub Release with the CHANGELOG section as notes, close the milestone.
6. Check the `Publish image` run and that the new tag appears under
   `github.com/solarssk?tab=packages`. A version that was tagged before the workflow
   existed is published by hand: Actions -> Publish image -> Run workflow, with that
   version and `publish` ticked.

### Container registry (ghcr.io)

- The first push creates the package **private**. Make it public once (package settings
  on GitHub, Danger Zone, Change visibility; there is no API for it) or give Portainer a
  registry credential with a token that has `read:packages`.
- The image carries the `org.opencontainers.image.source` label (set by the workflow), which
  links the package to this repository.
- Only exact version tags are published, no `latest`, so a deployment never moves by itself.
- A pull request that touches the workflow, the Dockerfile or `requirements.txt` runs the
  same pipeline as a dry run: both platforms are built and scanned, nothing is pushed.

## Dependabot

- Updates are weekly. PRs authored by `dependabot[bot]` do **not** receive repository
  Actions secrets, only a separate Dependabot secrets store. `SONAR_TOKEN` and
  `CODECOV_TOKEN` must therefore exist under *Settings > Secrets and variables >
  Dependabot* as well, or every Dependabot PR stays `BLOCKED` (SonarCloud and Codecov
  report nothing and have no "skipped" state).
- Fallback when that store is empty: apply the same changes in one human-authored PR and
  close the Dependabot PRs. Verify every new SHA first (next section).
- `if:` conditions cannot read `secrets.*`. Route the check through a job-level `env:`
  value, as the `code-quality` job does.

## Python dependencies

Runtime dependencies are hash-locked: `uploader/requirements.in` is the input and
`uploader/requirements.txt` the generated output (the Dockerfile and CI install it with
`--require-hashes`). Dependabot's `pip` ecosystem keeps both current. To regenerate by hand,
with Python 3.13:

```bash
cd uploader && pip-compile --generate-hashes --strip-extras -o requirements.txt requirements.in
```

Keep `requirements.in` in sync with `[project].dependencies` in `pyproject.toml`. CI enforces
it: the last step of the `Unit tests` job installs the lock plus the package with `--no-deps`
(as the Dockerfile does) in a throwaway venv and runs `pip check`, which fails if
`pyproject.toml` declares a dependency the lock does not contain. Dev tools
(ruff, mypy, pytest) are version ranges on purpose: they do not ship in the image.

## Pinning actions

Pin to the **commit** SHA of the tag, with the version as a trailing comment. For
annotated tags `git ls-remote --tags <repo> refs/tags/<tag>` returns the *tag object*,
not the commit. Ask for the peeled ref:

```bash
git ls-remote --tags https://github.com/OWNER/REPO "refs/tags/vX.Y.Z" "refs/tags/vX.Y.Z^{}"
# use the ^{} line when present, otherwise the plain line
```

(`trivy-action` and `codecov-action` were pinned to tag-object SHAs once; Dependabot's
"same version, new SHA" PRs were that correction.) Validate workflows with `actionlint`,
not just a YAML parser: GitHub rejects some expressions that are valid YAML.

## Container scanning

- PRs: Trivy, CRITICAL only, fixed vulnerabilities only. HIGH findings in the base image
  follow the base image publisher's rebuild cadence and would otherwise block unrelated
  work for days.
- Weekly (`weekly-image-scan.yml`): CRITICAL+HIGH, fixed only. A red weekly run means a
  fixed vulnerability exists upstream and the base image has not picked it up; check the
  log, then bump or change the base image. Do not blanket-ignore; any `.trivyignore`
  entry needs a CVE id, a reason and an expiry date.

## Roadmap

- 0.1.1: stabilization of the current two-container setup (milestone `0.1.1`).
- 0.1.2: the image is published to ghcr.io on release (milestone `0.1.2`).
- 0.2.0: single container with an embedded SMB1 server, see
  [roadmap/0.2.0-single-container-smb1.md](roadmap/0.2.0-single-container-smb1.md).
