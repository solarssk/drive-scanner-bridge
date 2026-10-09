# Maintenance guide

**In short:** how this repository is kept in order. It records the playbook tier, the
conventions that are not obvious from the code, and the pitfalls already hit. Contribution
rules are in [CONTRIBUTING.md](../CONTRIBUTING.md). Releases are in
[releasing.md](releasing.md).

## Contents

- [Playbook tier](#playbook-tier)
- [Conventions](#conventions)
- [Required status checks](#required-status-checks)
- [Dependabot](#dependabot)
- [Python dependencies](#python-dependencies)
- [Pinning actions](#pinning-actions)
- [Container scanning](#container-scanning)

## Playbook tier

This repository follows the [solarssk playbook](https://github.com/solarssk/playbook) at
**Tier 2**: a single-purpose tool that handles credentials and has real dependents.
SonarCloud and Codecov are Tier 3 items that were added deliberately.

> [!NOTE]
> Do not add more Tier 3 machinery (DAST, a user-facing wiki) unless the scope actually grows.
> An SBOM is not Tier 3: the playbook requires one at Tier 2 for any repository that publishes a
> container image, which this one does.

| Tier | Item | Status |
|---|---|---|
| 0 | LICENSE matching the README | ✅ |
| 0 | `.github/CODEOWNERS` | ✅ |
| 0 | Dependabot security updates on | ✅ |
| 0 | Delete head branches on merge | ✅ |
| 0 | Branch protection, enforced for admins | ✅ |
| 1 | CI on push and PR (tests, image build, compose check) | ✅ |
| 1 | Lint (ruff) and type check (mypy) | ✅ |
| 1 | Actions pinned to commit SHA with a version comment | ✅ see [Pinning actions](#pinning-actions) |
| 1 | `permissions` set to the minimum | ✅ |
| 1 | Base images pinned by digest | ✅ |
| 1 | Python dependencies hash-locked | ✅ `requirements.txt` |
| 1 | SECURITY.md, one structured issue template | ✅ |
| 2 | Dependency audit (`pip-audit`) | ✅ |
| 1 | Secret scan in CI | ✅ `gitleaks`, scoped to the run's commits |
| 2 | Platform secret scanning | ✅ GitHub secret scanning and push protection |
| 2 | SAST (CodeQL) on PR and weekly | ✅ |
| 2 | Workflows linted in CI with actionlint and zizmor | ✅ job `lint-workflows` |
| 2 | Dependabot for every ecosystem in use, each with a cooldown | ✅ pip, github-actions, docker |
| 2 | Blocking container scan | ✅ see [Container scanning](#container-scanning) |
| 2 | `concurrency:` group in every workflow | ✅ |
| 2 | Release automation (tag, Release, image, milestone) | ✅ `release.yml` |
| 2 | SBOM (CycloneDX) for the published image | ✅ attached to each Release |
| 2 | OpenSSF Scorecard workflow, report-only | ✅ `scorecard.yml` |
| 2 | CONTRIBUTING.md, PR template, CODEOWNERS | ✅ |
| 2 | "Documentation impact" in the PR template, checked in CI against the diff | ✅ `docs-impact.yml` |
| 2 | Documentation checks (links, anchors, style, settings table) | ✅ in the unit tests |
| 2 | The playbook's `verify-tier` runs against this repo | ✅ `verify-standard.yml`, pinned to v0.2.0 |
| 2 | Badge row (CI, release, license) | ✅ |
| 2 | README follows the playbook README standard, depth in `docs/` | ✅ |
| 2 | `AGENTS.md` with the standard pointer, `CLAUDE.md` that imports it | ✅ |
| 3 | Coverage gate and quality gate | ✅ Codecov, SonarCloud (report-only) |

Keep this table current when an item changes status.

## Conventions

| Topic | Rule |
|---|---|
| Issues and PRs | Each has an **assignee**, at least one **label** and a **milestone**. Dependabot PRs are exempt. |
| Labels in use | The playbook's `type:` labels (`type: bug`, `type: feature`, `type: docs`, `type: chore`), plus `security`, `ci`, `governance`, and the two Dependabot applies itself (`dependencies`, `github_actions`) |
| Branch names | `<type>/<short-description>`, type is `fix`, `feature`, `maintenance`, `security`, `docs` or `release` |
| Milestones | One per release, named exactly like the version (`0.1.7`). Closed automatically when the release is published. |
| Merging | The owner merges. Required checks apply to admins too, with no bypass. |
| Playbook updates | Dependabot proposes a bump of the pinned `verify-standard.yml` call. Read the release's "Adopter action" list, then bump. |
| Doc file names | Lowercase kebab-case in `docs/` (`troubleshooting.md`). Uppercase only for the conventional root files (`README`, `AGENTS`, `CLAUDE`, `CONTRIBUTING`, `SECURITY`, `CHANGELOG`, `LICENSE`). Details: [docs/AGENTS.md](AGENTS.md). |
| Roadmap | Lives in one place: [docs/roadmap/](roadmap/README.md). |

## Required status checks

Branch protection on `main` requires exactly these three checks:

| Check | Job in `ci.yml` |
|---|---|
| `Unit tests` | `test` |
| `Build uploader image` | `build-image` |
| `Validate docker-compose.yml` | `compose-lint` |

SonarCloud (`SonarCloud Code Analysis`), Codecov (`codecov/patch`) and the
`Code quality (Sonar + Codecov)` job are **report-only**. They run and report wherever the
tokens exist, but they do not gate a merge. This matches the owner's other repositories.

> [!IMPORTANT]
> Renaming a job changes its check name. Update the branch protection contexts in the same
> change, or every pull request waits forever for a check that no longer exists.

The reason for report-only: the two external checks have no "skipped" state. A pull
request that cannot read repository secrets (Dependabot, forks) never receives them, so
requiring them would leave those pull requests blocked for good.

## Dependabot

- Updates are weekly and grouped (one PR per ecosystem per week). The owner merges them
  by hand.
- Every entry has a `cooldown` of 7 days, so a version published minutes ago is not proposed
  before it has had time to be pulled if it was compromised. Security updates ignore it.
- `docker-compose.yml` is not watched on purpose: its only third-party image is
  `dperson/samba:latest`, a floating tag Dependabot cannot track, and 0.2.0 removes that
  container.
- Dependabot PRs do **not** receive repository Actions secrets, so the `Code quality` job
  skips its Sonar and Codecov steps. Those are report-only, so the PR is mergeable once the
  three required checks are green. Nothing needs to be added to the Dependabot secrets store.
- Verify every new action SHA first; see [Pinning actions](#pinning-actions).
- `if:` conditions cannot read `secrets.*`. Route the check through a job-level `env:`
  value, as the `code-quality` job does.

## Python dependencies

Two hash-locked sets, both installed with `--require-hashes`:

| Set | Input | Generated lock | Installed by |
|---|---|---|---|
| Runtime | `uploader/requirements.in` | `uploader/requirements.txt` | the Dockerfile and CI |
| Dev tools (pytest, ruff, mypy, pip-audit, ...) | `uploader/requirements-dev.in` | `uploader/requirements-dev.txt` | CI and contributors |

The dev lock is constrained to the exact runtime pins (`-c requirements.txt`), so CI tests the
versions the image ships. Dependabot's `pip` ecosystem keeps both current, and a new release waits
out the 7-day cooldown first.

To regenerate by hand, with Python 3.13, from `uploader/`:

```bash
pip-compile --generate-hashes --strip-extras -o requirements.txt requirements.in
pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.txt requirements-dev.in
```

Keep the `.in` files in sync with `pyproject.toml`. Unit tests check that the runtime list and
every dev extra match, that each pin has hashes, and that the dev lock keeps the runtime pins. CI
also installs the runtime lock plus the package with `--no-deps` (as the Dockerfile does) in a
throwaway venv and runs `pip check`, which fails if `pyproject.toml` declares a dependency the
lock does not contain.

## Pinning actions

Pin to the **commit** SHA of the tag, with the version as a trailing comment. For annotated
tags, `git ls-remote --tags <repo> refs/tags/<tag>` returns the *tag object*, not the
commit. Ask for the peeled ref as well:

```bash
git ls-remote --tags https://github.com/OWNER/REPO "refs/tags/vX.Y.Z" "refs/tags/vX.Y.Z^{}"
# use the ^{} line when present, otherwise the plain line
```

> [!TIP]
> Validate workflows with `actionlint`, not just a YAML parser. GitHub rejects some
> expressions that are valid YAML.

`trivy-action` and `codecov-action` were once pinned to tag-object SHAs. Dependabot's
"same version, new SHA" pull requests were that correction.

## Container scanning

| Where | Scope | Effect |
|---|---|---|
| Pull requests (`ci.yml`) | Trivy, CRITICAL only, fixed vulnerabilities only | Blocks the PR |
| Weekly (`weekly-image-scan.yml`) | CRITICAL and HIGH, fixed only | Reports, does not block |
| Release (`release-image.yml`) | CRITICAL and HIGH, fixed only, both platforms, before the push | Blocks the publish |

HIGH findings in the base image follow the publisher's rebuild cadence. Gating pull
requests on them would block unrelated work for days.

A red weekly run means a fixed vulnerability exists upstream and the base image has not
picked it up yet. Check the log, then bump or change the base image.

> [!WARNING]
> Do not blanket-ignore findings. Any `.trivyignore` entry needs a CVE id, a reason and an
> expiry date.
