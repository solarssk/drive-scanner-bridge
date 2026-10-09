# AGENTS.md: uploader

Rules for the service code and its tests. They add to the root [AGENTS.md](../AGENTS.md);
where they differ, this file wins for files under `uploader/`.

## Commands

Run from this directory with Python 3.13:

```bash
.venv/bin/ruff check . ../scripts
.venv/bin/mypy
.venv/bin/pytest -q
```

## Invariants you must not break

These protect the promise that a scan is never lost and never uploaded twice. The full
reasoning is in [docs/architecture.md](../docs/architecture.md#no-duplicates-and-no-lost-scans).

1. A file is identified by its SHA-256 content hash, never by name.
2. A local file is deleted only after its `uploaded` state is committed to SQLite.
3. A failed upload call is never assumed to mean the file is missing on the server. After a
   restart, `Worker._reconcile_in_flight` checks the real destination before any retry.
4. A file that fails is never deleted and never abandoned. Retries continue at the last
   backoff interval.
5. Polling decides when a file is complete, and the settle time is real elapsed time,
   independent of the polling rate.

## Code rules

- The only runtime dependency is `requests`. Adding one needs a written reason in the PR.
- Secrets never reach a log line, an exception message, a repr or a URL query string.
  `Config.__repr__` hides them; keep it that way and keep the regression tests.
- Credentials go in the POST body of the login request.
- TLS verification stays an explicit setting. Never turn it off silently.
- Every new setting is read in `config.py`, listed in
  [docs/configuration.md](../docs/configuration.md) with its default, and, if operators
  should set it, passed on in `docker-compose.yml` and `.env.example`.

## Tests

- The Synology API is mocked. Tests must not make network calls.
- When you fix a bug, add a test that fails without the fix.
- Test fakes must stay faithful: a fake that raises inside code that swallows errors makes
  tests pass while exercising the failure path (this happened once with `login()`).
- Codecov counts every changed line toward patch coverage. Avoid cosmetic edits to
  executable lines the tests do not reach.
