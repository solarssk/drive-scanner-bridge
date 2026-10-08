## What and why

<!-- One or two sentences. Link the issue: "Closes #N". -->

## Checklist

- [ ] Assignee, at least one label and the milestone are set (see CONTRIBUTING.md)
- [ ] `ruff check .`, `mypy` and `pytest -q` pass locally in `uploader/`
- [ ] Any new or changed GitHub Action is pinned to the **commit** SHA of its tag (use the peeled `^{}` ref), with the version as a trailing comment
- [ ] `CHANGELOG.md` `[Unreleased]` updated if the change is visible to someone running the bridge
- [ ] README / docs updated if behavior, configuration or deployment steps changed
- [ ] No secrets, hostnames or credentials in the diff

## Notes for the reviewer

<!-- Risks, what was not tested, anything that needs a check on the real NAS or scanner. -->
