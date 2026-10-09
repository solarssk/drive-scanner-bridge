# AGENTS.md: .github

Rules for changing workflows, templates and repository automation. They add to the root
[AGENTS.md](../AGENTS.md); where they differ, this file wins for files under `.github/`.

## Before you commit

- Lint every workflow with `actionlint` (it includes `shellcheck`). A YAML parser is not
  enough: GitHub rejects some expressions that are valid YAML.
- A workflow change that can affect a required check name needs a matching change to
  branch protection. Tell the owner; do not change the setting yourself.

## Workflow rules

| Rule | Why |
|---|---|
| Pin every action to the **commit** SHA of its tag, with the version as a trailing comment. For annotated tags use the peeled `^{}` ref. | A tag can move; a tag-object SHA is not a commit. See [docs/maintenance.md](../docs/maintenance.md#pinning-actions). |
| Start with `permissions: {}` or `contents: read` and grant per job, only what the job needs. | Least privilege for the token. |
| Give every workflow a `concurrency:` group. In `release.yml` it is per commit. | A shared group could evict the pending run of a real release push. |
| Never put `${{ ... }}` of untrusted input (branch names, PR titles, dispatch inputs) into a `run:` script. Pass it through `env:` and quote it. | Script injection. |
| `secrets` cannot be read in `if:`. Route the check through a job-level `env:` value. | GitHub rejects the workflow otherwise. |
| Quote any `run:` command that contains `:` followed by a space, such as `--only-binary=:all:`. | It is otherwise parsed as YAML. |

## What not to do

- Do not make a gate weaker without the owner's explicit approval of that exact change: no
  `continue-on-error` on a required step, no dropped required check.
- Do not create tags or Releases from a workflow other than `release.yml`. Tags created
  with `GITHUB_TOKEN` do not start other workflows, which is why `release.yml` dispatches
  `release-image.yml` itself.
- Do not widen the release dispatch: `Release` must keep refusing any ref except `main`,
  and `Publish image` must keep refusing to overwrite a published version.

## Files here

| Path | Purpose |
|---|---|
| [`workflows/`](workflows/README.md) | CI, CodeQL, image publishing, release, weekly scan |
| `dependabot.yml` | pip, github-actions and docker, weekly and grouped |
| `CODEOWNERS` | Review ownership |
| `pull_request_template.md`, `ISSUE_TEMPLATE/` | Templates; keep the PR checklist in line with the real checks |
