## Description

<!--
Two short paragraphs:
1. The problem this solves, in plain language. For pure maintenance (a dependency bump, a CI
   tweak) say so instead.
2. What changed, grouped by area. Describe the diff as shipped, not the original plan.
Link the issue: "Closes #N".
-->

## How to test

<!-- Concrete verification steps. If something was not run, say so and why. -->

## What stays / known limitations

<!-- Anything intentionally left out, deferred or still transitional. Risks, and anything that needs a check on the real NAS or scanner. -->

## Documentation impact

<!-- Choose exactly one. CI checks the choice against the diff. -->

- [ ] Docs updated
- [ ] No doc update needed: <state the reason>

## Checklist

- [ ] Assignee, at least one label and the milestone are set (see CONTRIBUTING.md)
- [ ] `ruff check . ../scripts`, `mypy` and `pytest -q` pass locally in `uploader/`
- [ ] Any new or changed GitHub Action is pinned to the **commit** SHA of its tag (use the peeled `^{}` ref), with the version as a trailing comment
- [ ] `CHANGELOG.md` `[Unreleased]` updated if the change is visible to someone running the bridge
- [ ] No secrets, hostnames or credentials in the diff
