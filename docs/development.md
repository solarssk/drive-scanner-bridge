# Development

**In short:** set up Python 3.13, run three checks, and read the code layout.

| Looking for | Go to |
|---|---|
| Issue, PR and branch rules | [CONTRIBUTING.md](../CONTRIBUTING.md), [maintenance.md](maintenance.md) |
| How to publish a release | [releasing.md](releasing.md) |
| Rules for AI coding agents | [AGENTS.md](../AGENTS.md), [uploader/AGENTS.md](../uploader/AGENTS.md) |

## Set up

You need Python 3.13. Work from the `uploader/` directory:

```bash
cd uploader
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Run the checks

CI runs these three commands in `uploader/`. Run them before you open a pull request:

```bash
.venv/bin/ruff check . ../scripts
.venv/bin/mypy
.venv/bin/pytest -q
```

`ruff` also covers `scripts/`, which holds the release-notes script. The test run
produces a coverage report that Codecov and SonarCloud read.

## Code layout

| Path | Purpose |
|---|---|
| `uploader/scanner_drive_bridge/main.py` | Entry point (`python -m scanner_drive_bridge.main [healthcheck]`) and health check. |
| `uploader/scanner_drive_bridge/worker.py` | The main loop, upload, retry and crash recovery. |
| `uploader/scanner_drive_bridge/scanner.py` | `StabilityTracker`: decides when a file is complete. |
| `uploader/scanner_drive_bridge/state.py` | The SQLite ledger keyed by content hash. |
| `uploader/scanner_drive_bridge/synology.py` | The Synology Drive API client. |
| `uploader/scanner_drive_bridge/config.py` | Settings from environment variables. |
| `uploader/scanner_drive_bridge/test_connection.py` | The connectivity check used in [deployment.md](deployment.md#check-that-it-works). |
| `uploader/tests/` | Unit tests. |
| `scripts/format_release_notes.py` | Builds GitHub Release notes from the CHANGELOG. |

## What the tests cover

The Synology API is mocked completely, so the tests make no network calls. They cover:

- file stabilization, including that the settle time is real elapsed time, independent of
  the polling rate
- conflict and duplicate handling
- retry backoff and the escalation to "permanent failure" logging
- the source file being kept after a failure and removed only after a confirmed upload,
  or kept and cleaned up after `LOCAL_RETENTION_HOURS` when `DELETE_AFTER_UPLOAD=false`
- crash and restart safety, including reconciliation against a remote listing
- parsing of several plausible API response shapes
- secret handling: never logged, redacted from network-error messages, `_FILE`-based
  secrets
- a broken or unreadable file never crashing the worker loop
- the release-notes script

## Dependencies

Runtime dependencies are hash-locked. How to change the lock, and how the dependency
checks work, is described in [maintenance.md](maintenance.md#python-dependencies).

## Build the image locally

```bash
docker build -t ghcr.io/solarssk/drive-scanner-bridge:0.1.5 ./uploader
```

Use the same name as the `image:` line in `docker-compose.yml` so that Compose uses your
build.
