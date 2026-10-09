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
| 2 | Release automation (tag, GitHub Release, image, milestone on merge) | done (`release.yml`) |
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

`Unit tests`, `Build uploader image`, `Validate docker-compose.yml`.

SonarCloud (`SonarCloud Code Analysis`), Codecov (`codecov/patch`) and the `Code quality
(Sonar + Codecov)` job are **report-only**: they run and report on every PR where the tokens
are available, but do not gate a merge. That is how the owner's other repositories work, and it
is what keeps PRs that cannot read repository secrets (Dependabot, forks) from sitting
`BLOCKED` on checks that will never be posted: the two external checks have no "skipped" state.

Renaming a job changes its check name; update the branch protection contexts in the same
change or every PR will wait forever for a check that no longer exists.

## Release process

Merging a release PR **is** the release. A release is a git tag, a GitHub Release and a
container image on ghcr.io (`ghcr.io/solarssk/drive-scanner-bridge:<version>`, `linux/amd64` +
`linux/arm64`); `.github/workflows/release.yml` creates all of it, you only prepare the PR:

1. Close or move every issue in the milestone (named exactly like the version, e.g. `0.1.3`).
2. Bump the version everywhere it is written: `uploader/pyproject.toml`,
   `uploader/scanner_drive_bridge/__init__.py`, the `image:` tag in `docker-compose.yml`, and
   the README references (`grep -rn "<old version>"`).
3. `CHANGELOG.md`: turn `[Unreleased]` into `## [x.y.z] - YYYY-MM-DD` (that exact heading
   format; the release notes are built from it) and add a fresh empty `[Unreleased]`.
4. Open a `release/x.y.z` PR. The owner merges it once CI is green, **including the `Build,
   scan, publish` dry run** (it runs because a release PR changes `uploader/pyproject.toml`; it
   is not a required check, so look at it). It builds and scans both platforms exactly as the
   release will, so a fixable CRITICAL/HIGH finding shows up before the tag exists.
5. On the merge to `main` the `Release` workflow compares the version before and after the
   push and, if it moved: checks that `__version__`, the compose image tag and the CHANGELOG
   heading all agree (a mismatch fails the run and releases nothing), creates the tag
   `x.y.z` on the merge commit and the GitHub Release (notes from the CHANGELOG via
   `scripts/format_release_notes.py`), dispatches `Publish image`, **waits for that run to
   finish**, and only if it succeeded closes the milestone. It waits for the exact run it
   dispatched (the run URL `gh` returns, or else a request id in the run's title), so a manual
   `Publish image` run on the same version can never be mistaken for it.
6. `Publish image` builds each platform, scans each one (CRITICAL or HIGH with a fix blocks)
   and only then pushes. Check that the `Release` run is green and that the tag appears under
   `github.com/solarssk?tab=packages`.

If the image run fails, the `Release` run goes red and the milestone stays open. The tag and
the GitHub Release already exist at that point but the image does not. Nothing vulnerable is
ever pushed. Open the failed `Publish image` run and decide by the cause:

- **Transient** (registry, network, runner, scanner database download): run `Publish image`
  by hand for that version (a failed run publishes nothing, so it is not blocked as "already
  published"), then close the milestone.
- **A scan finding or build error in the tagged files** (a fixable CVE in a pinned base image
  or a locked package): running it again rebuilds the same tag and fails the same way, because
  the fix is a new commit and a tag never moves. Fix it on `main` and ship it as the **next
  patch version**; edit the Release of the broken one to say it has no image and point to the
  new version. Only if nobody can have used the tag yet, you may instead delete the tag and the
  Release, merge the fix, and run `Release` by hand from `main`, which tags the fix commit.

Recovery and manual use:

- `Release` can be run by hand (Actions -> Release -> Run workflow, **from `main`**; it
  refuses any other branch). It repeats the steps for the version currently in `pyproject.toml`;
  each step is safe to repeat. It only works while `main` is still at the release commit: a tag
  that sits on a different commit fails the run on purpose, rather than attaching a release
  to the wrong code.
- Merging a fix after a *failed* `Release` run (for example a version that disagreed between
  files) does **not** release anything by itself: that push does not move the version. The
  run says so in a warning; run `Release` by hand from `main` once the fix is merged.
- `Publish image` can be run by hand with a version and `publish` ticked, for a tag that
  exists but has no image. It always builds that tag's files, whichever branch it is started
  from, and the image's `revision` label records the commit it built. It never overwrites a
  version that is already on ghcr.io.
- Do not push release tags by hand: the automation owns them. A hand-pushed tag still
  publishes an image (fallback) but gets no Release and no milestone closing.

### Container registry (ghcr.io)

- The first push creates the package **private**. Make it public once (package settings
  on GitHub, Danger Zone, Change visibility; there is no API for it) or give Portainer a
  registry credential with a token that has `read:packages`.
- The image carries the `org.opencontainers.image.source` label (set by the workflow), which
  links the package to this repository.
- Only exact version tags are published, no `latest`, so a deployment never moves by itself.
  A published tag is immutable: `Publish image` leaves a version that is already on ghcr.io untouched.
- A pull request that touches the workflow, the Dockerfile, `requirements.txt` or
  `uploader/pyproject.toml` (every release PR bumps it) runs the same pipeline as a dry
  run: both platforms are built and scanned, nothing is pushed.

## Dependabot

- Updates are weekly and grouped; the owner merges them by hand. PRs authored by
  `dependabot[bot]` do **not** receive repository Actions secrets, so the `Code quality` job
  skips its Sonar and Codecov steps there. Those are report-only, so such a PR is mergeable once
  the three required checks are green; nothing needs to be added to the Dependabot secrets store.
- Verify every new SHA first (see "Pinning actions" below).
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

- 0.1.4: hardening of the release automation and a tidy-up of stale docs (milestone `0.1.4`).
- 0.2.0: single container with an embedded SMB1 server, see
  [roadmap/0.2.0-single-container-smb1.md](roadmap/0.2.0-single-container-smb1.md).
