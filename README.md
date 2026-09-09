# scanner-drive-bridge

[![CI](https://github.com/solarssk/drive-scanner-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/drive-scanner-bridge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Bridges a legacy SMB1 network scanner to Synology Drive, bypassing a
Synology Drive bug where filesystem events are not reliably consumed.

## Table of Contents

- [Why this service exists](#why-this-service-exists)
- [Architecture](#architecture)
- [Why a hand-written Synology Drive API client instead of the `synology-drive-api` library](#why-a-hand-written-synology-drive-api-client-instead-of-the-synology-drive-api-library)
- [Idempotency strategy](#idempotency-strategy)
- [File stabilization](#file-stabilization)
- [Retry behavior](#retry-behavior)
- [Deployment](#deployment)
- [Deploying via Portainer](#deploying-via-portainer)
- [Secrets and credentials](#secrets-and-credentials)
- [Security](#security)
- [Scanner flow (unchanged)](#scanner-flow-unchanged)
- [Backup considerations](#backup-considerations)
- [Troubleshooting](#troubleshooting)
- [Upgrading](#upgrading)
- [Rollback](#rollback)
- [Development](#development)
- [Verified compatibility](#verified-compatibility)
- [License](#license)

## Why this service exists

This NAS's Synology Drive install has a confirmed bug: `synotifyd` receives
filesystem change events, the `@drive.synotifyd.queue.toread.*` queue files
are created, the queue generation counter increments -- but the event is
sometimes never actually consumed. `minimum gen in EventManager` stays at
`0`, and the new file never appears in Synology Drive, even though it
exists normally on disk and shows up immediately in File Station. The only
reliable workaround found was manually running:

```bash
/var/packages/SynologyDrive/target/bin/cloud-control synotifyd-rescan --view_id 21 --path /
```

That is a workaround, not a fix, and it is not something this project relies
on. Instead, this service **bypasses the filesystem-event pipeline
entirely**: files never get written to `/volume1/printer` at all. They land
in a private local inbox, and `drive-uploader` pushes them into Synology
Drive through its own upload API (`SYNO.SynologyDrive.Files`), i.e. exactly
the same path a human using the Synology Drive client would go through. If
Drive's API accepted the upload, Drive already knows about the file --
there is no separate filesystem-notification step left to fail.

## Architecture

```
Legacy scanner
      |
      | SMB1 / NT1
      v
smb1-printer (fixed IP on smb1_network)
      |
      | writes into the shared "scanner_incoming" Docker volume
      v
scanner_incoming (volume, mounted at /incoming in drive-uploader)
      |
      v
drive-uploader
      |
      | HTTPS -> SYNO.SynologyDrive.Files "upload"
      v
Synology Drive
      |
      v
Team Folder: printer  (/volume1/printer, indexed correctly)
```

`smb1-printer` no longer has `/volume1/printer` bind-mounted at all. The DSM
shared folder is populated exclusively by `drive-uploader` through the
Drive API, so Synology's own upload/indexing code path is the only thing
that ever writes there.

`drive-uploader` does not join `smb1_network`: it only needs outbound HTTPS
to the NAS's own DSM port, not to the scanner or the
Samba container, so it is kept off that network as a matter of least
privilege. It reaches the NAS via the default Docker bridge network. If
your environment's routing doesn't allow that, see
[Troubleshooting](#troubleshooting).

## Why a hand-written Synology Drive API client instead of the `synology-drive-api` library

Before writing any code, [`zbjdonald/synology-drive-api`](https://github.com/zbjdonald/synology-drive-api)
was reviewed as a candidate dependency. Findings:

- **Unmaintained.** Last commit December 18, 2023 -- no activity since.
- **Silently disables TLS verification for a very common setup.** Its
  `SynologySession` forces `verify=False` for any HTTPS host whose address
  looks like an IPv4 literal (`netloc.count('.') >= 3`) -- which is exactly
  how most NAS devices are reached on a LAN without internal DNS. Using this
  library there would silently defeat `SYNOLOGY_VERIFY_TLS` /
  `SYNOLOGY_CA_FILE` regardless of what they were set to.
- **Unnecessary heavy dependency.** Its `pyproject.toml` requires `selenium`
  unconditionally (used for a Synology-Office spreadsheet-conversion
  feature this service never touches) -- an unjustified addition to a
  container that should have a minimal attack surface.
- Its open issues include an unresolved `error_code 103` ("method does not
  exist") at login, consistent with a hardcoded API version drifting out of
  sync with newer DSM/Drive Server builds.
- On the positive side, its actual `upload_file` implementation confirmed
  the general shape (`POST entry.cgi`, `api=SYNO.SynologyDrive.Files`,
  `method=upload`, multipart file part) is real -- though, as it turned
  out, its exact parameter names (`dest_folder_path`, hardcoded `version=2`)
  are specific to an older API version and do not work against this NAS.
  See below.

Given this, [`uploader/scanner_drive_bridge/synology.py`](uploader/scanner_drive_bridge/synology.py)
is a small (~250 line), dependency-free (just `requests`) client that:

- Always makes TLS verification an explicit, honest choice
  (`SYNOLOGY_VERIFY_TLS`, `SYNOLOGY_CA_FILE`) -- never silently downgrades it.
- Calls `SYNO.API.Info` at connect time to discover the API versions this
  specific NAS actually supports, instead of hardcoding `version=2` --
  directly hedging against the version-drift issue seen in the wrapper.
- Sends credentials in the login request's POST body, never the query
  string (see [Secrets](#secrets-and-credentials) -- this was caught by a
  live smoke test, not code review, and is covered by a regression test).

**This paid off in practice, not just in theory:** against a real DSM
7.4.1 / Synology Drive Server 4.0.3 instance, `SYNO.API.Info` reported
`SYNO.SynologyDrive.Files`=**11** -- nowhere near the wrapper's hardcoded
`version=2` -- and that version's `upload` method turned out to need a
different parameter shape entirely. See
[Verified compatibility](#verified-compatibility) below for the details
and what to check if you're on a different version.

## Idempotency strategy

This is the part most likely to cause real damage if done carelessly
(duplicate uploads, or worse, a lost scan), so here is the exact mechanism,
also documented in the `worker.py` and `state.py` module docstrings:

1. Every file is identified by its **SHA-256 content hash**, not its
   filename -- the scanner reuses names like `SCN_0001.pdf`, so filename
   alone cannot answer "have I already handled this". A row per hash is
   kept in SQLite (`/data/state.db`) with state `pending -> uploading ->
   uploaded`.
2. A file is only deleted from `/incoming` after its `uploaded` state is
   committed to SQLite. A crash between that commit and the delete leaves a
   harmless leftover local file; the next time it's scanned, its hash is
   found already `uploaded` and it is removed without a second upload (this
   is always logged, e.g. `duplicate content detected ... removing local
   duplicate without re-upload` -- never silent).
3. **A failed HTTP response is never assumed to mean the upload didn't
   happen.** If the process crashes or is restarted while a row is in
   `uploading` state, startup reconciliation (`Worker._reconcile_in_flight`)
   lists the real destination folder in Synology Drive and checks for a
   matching file (by name and exact size) *before* allowing any retry. Only
   if no match is found does it retry the upload.
4. `conflict_action=autorename` is Synology's own safety net for the
   scanner genuinely reusing a filename for different content -- it is not
   the primary anti-duplicate mechanism, the SQLite ledger above is.
5. Two files with byte-identical content are treated as the same document:
   the second one is removed locally without being re-uploaded. This is a
   deliberate, always-logged choice (see `worker.py`), not an accident.

## File stabilization

The scanner may write a file progressively; uploading too early would send
a partial scan. Detection is poll-based (not inotify -- the entire premise
of this project is that this NAS's filesystem-notification pipeline is
unreliable, so nothing here depends on any notification mechanism):

- Every `SCAN_INTERVAL_SECONDS`, `/incoming` is scanned for new/changed
  entries -- this only controls responsiveness, not the safety margin.
- A file's `(size, mtime)` must be identical across `STABILITY_CHECKS`
  consecutive checks, each **at least `STABILITY_INTERVAL_SECONDS` apart in
  real time**, and it must be openable for reading, before it is considered
  stable and queued for upload. This is enforced independently of how often
  `/incoming` is polled: a fast `SCAN_INTERVAL_SECONDS` does not shrink the
  actual settle margin. This matters in practice, not just in theory -- a
  slow/flaky legacy SMB1 transfer that gets grabbed (and deleted) mid-write
  doesn't just risk an incomplete upload, it can itself cause the scanner's
  own SMB session to error out, since the file it's still writing to just
  disappeared from under it.
- Hidden files (`.foo`), editor lock files (`~foo`), and common
  partial-write suffixes (`.tmp`, `.part`, `.partial`, `.crdownload`) are
  always ignored.
- Once a file has been reported stable, it is not reported again as long as
  it sits there unchanged (this matters: otherwise a file waiting through
  retry backoff would be re-hashed and re-logged every polling cycle
  indefinitely). See `StabilityTracker` in
  [`scanner.py`](uploader/scanner_drive_bridge/scanner.py).

**`DELETE_AFTER_UPLOAD`** (default `true`): by default `/incoming` is a
temporary staging area, cleared once a file is confirmed uploaded. Some
scanners infer their *next* filename by listing the destination SMB folder
themselves and incrementing past the highest number found there -- if that
folder is always empty, they can get stuck reusing the same name. Set this
to `false` to keep every successfully uploaded file in `/incoming`
permanently instead; content-hash dedup already guarantees a kept file is
never re-uploaded, so this only affects local disk usage, not correctness.
Combine with **`LOCAL_RETENTION_HOURS`** (unset by default = keep forever)
to have the worker clean up a kept copy on its own once it's older than N
hours since confirmed upload, so `/incoming` doesn't grow without bound
while the scanner still sees enough recent history to number correctly.

**`TIMESTAMP_UPLOAD_FILENAME`** (default `false`): purely cosmetic, for
browsing the Team Folder -- prefixes the name sent to *Synology Drive*
with today's date (`SCN_0001.pdf` -> `2026-08-22_SCN_0001.pdf`). It never
touches the local `/incoming` filename, which must stay exactly as the
scanner wrote it for `DELETE_AFTER_UPLOAD=false`'s filename-numbering
trick above to keep working.

## Retry behavior

Failures back off along `RETRY_BACKOFF_SECONDS` (default `5,15,30,60,300`).
After the schedule is exhausted, retries continue indefinitely at the last
interval (300s by default) -- **a file is never given up on and never
deleted** after failure, only after a confirmed successful upload. The log
level escalates from `WARNING` (still within the normal schedule) to
`ERROR: permanent upload failure` the moment the schedule is exhausted, and
stays at `ERROR` for every attempt after that -- "permanent" here means
"this is now a flagged, ongoing problem an operator should look at", not
"the service has stopped trying".

## Deployment

Prerequisites: Docker / Container Manager on the NAS, the existing
`smb1_network` Docker network, and the `printer` Team Folder already
created in Synology Drive.

```bash
git clone <this repo> scanner-drive-bridge
cd scanner-drive-bridge
cp .env.example .env
# edit .env: at minimum set SYNOLOGY_HOST, SMB1_STATIC_IP, SMB_PRT01_PASSWORD
printf '%s' 'the prt01 DSM password' > secrets/synology_password
docker build -t scanner-drive-bridge-uploader:0.2.0 ./uploader
docker compose up -d
docker compose logs -f drive-uploader
```

`secrets/synology_password` is required. `secrets/synology_ca` is optional
(only needed if `SYNOLOGY_VERIFY_TLS=true` and the NAS's HTTPS certificate
isn't already trusted by the container's default CA bundle -- e.g. a
self-signed DSM certificate). Leave it absent to use the system trust
store.

Run the non-destructive connectivity check before trusting the stack with
real scans:

```bash
docker compose exec drive-uploader python -m scanner_drive_bridge.test_connection
```

This authenticates, lists Team Folders, and confirms `printer` is listable.
It does **not** upload anything unless you explicitly opt in:

```bash
docker compose exec -e SCANNER_BRIDGE_TEST_UPLOAD=true drive-uploader \
  python -m scanner_drive_bridge.test_connection
```

which uploads one tiny, uniquely-named file and deletes it again
afterwards.

## Deploying via Portainer

Portainer runs as its own container, and that container generally cannot
read arbitrary host paths (`/volume1/...`) unless they were explicitly
mounted into it -- so a `build:` context pointing at a host path fails with
`Cannot locate specified Dockerfile`, even though the exact same path is
completely valid on the NAS itself. Docker's bind-mount runtime, by
contrast, is handled by `dockerd` directly (which runs natively on DSM, not
in a container, and always sees the whole disk) -- so bind mounts work fine
from Portainer, only *building* from a host path doesn't.

Two things fell out of this in practice (both confirmed against a real
Portainer instance, not just reasoned about):

- Portainer's **Images -> Build a new image** screen has an **Upload**
  method that takes a build-context tarball directly through the browser,
  which sidesteps the host-path problem entirely (the Dockerfile never
  needs to live anywhere Portainer's container can see on disk).
- Portainer's **Stacks** deploy attempts to build *any* service that has a
  `build:` section, regardless of whether a same-tagged `image:` already
  exists locally -- unlike plain `docker compose up` on the CLI, which
  skips building if the image is already present. So `docker-compose.yml`
  deliberately has **no `build:` section** for `drive-uploader` at all: the
  image must already exist locally (via the step above, or `docker build`
  over SSH) before the stack is deployed, and the stack only ever runs it.

Steps:

1. **Build the image**: Portainer -> Images -> Build a new image -> Build
   method **Upload** -> upload a tarball of `uploader/`'s contents
   (Dockerfile at the tar's root -- this repo's `uploader/` directory,
   tarred up; regenerate it after any Dockerfile/source change). Name it
   explicitly and exactly, matching the `image:` line in
   `docker-compose.yml` (`scanner-drive-bridge-uploader:0.2.0` by default --
   bump both together on every rebuild, see "Upgrading" below). This builds
   natively for whatever CPU architecture the NAS actually is, no cross-arch
   guessing needed.
2. **Create a small folder on the NAS filesystem** for the secret (this
   *is* a runtime bind mount, so it works regardless of what Portainer's
   own container can see), e.g. via File Station:
   ```text
   /volume1/docker/scanner-drive-bridge/secrets/synology_password
   ```
   containing the real DSM password for `prt01` (plain text). Optionally
   add `secrets/synology_ca` next to it too.
3. **Portainer -> Stacks -> Add stack.**
   - Name: `scanner-drive-bridge` (or anything you like).
   - Build method: **Web editor** -- paste the contents of this repo's
     `docker-compose.yml` as-is.
   - **Environment variables** section, add at minimum:
     - `PROJECT_DIR` = `/volume1/docker/scanner-drive-bridge` (so the
       `secrets` bind mount resolves)
     - `SMB_PRT01_PASSWORD` = the real Samba password for `prt01`
     - `SMB1_STATIC_IP` = a free static IP on your `smb1_network` subnet
     - `SYNOLOGY_HOST` = your NAS's URL, e.g. `https://192.0.2.10:5001`
     - any other `SYNOLOGY_*` overrides you need for your environment
   - **Deploy the stack.**
4. **Watch it start:** Containers -> `drive-uploader` -> Logs. Look for
   `authenticated to Synology Drive` and `destination team folder 'printer'
   verified`. If Synology is briefly unreachable this is fine -- see
   [Retry behavior](#retry-behavior) and [Troubleshooting](#troubleshooting).
5. **Run the connectivity check:** Containers -> `drive-uploader` ->
   Console -> Connect, then run:
   ```bash
   python3 -m scanner_drive_bridge.test_connection
   ```
6. **Updating after a code/image change:** repeat step 1 under a *new* tag
   (e.g. `scanner-drive-bridge:v2`), update the `image:` line in the
   stack's pasted YAML to match, and **Update the stack**. Always bump the
   tag on updates rather than rebuilding under the same one -- it removes
   any ambiguity about whether Portainer picked up the new image content or
   kept running the old container.

If you'd rather manage this over SSH instead of Portainer, `docker-compose.yml`
works unmodified with the CLI flow in [Deployment](#deployment) above
(`docker build` once, then plain `docker compose up -d`; `PROJECT_DIR` stays
unset and defaults to `.`).

## Secrets and credentials

Nothing is hardcoded in source or in the image.

| Secret | How it's supplied |
|---|---|
| Synology Drive password (`prt01`) | `secrets/synology_password`, mounted read-only at `/run/secrets/synology_password`, read via `SYNOLOGY_PASSWORD_FILE` |
| Custom/self-signed CA (optional) | `secrets/synology_ca`, mounted at `/run/secrets/synology_ca`, read via `SYNOLOGY_CA_FILE` |
| Samba `prt01` password | `SMB_PRT01_PASSWORD` in `.env` (gitignored) -- the `dperson/samba` image only accepts this as a command-line argument, it has no secrets-file support, so `.env` substitution is the closest available equivalent |

`secrets/` and `.env` are gitignored; only `secrets/.gitkeep` is tracked.
Logs never contain the password or session id -- see
[Why a hand-written client](#why-a-hand-written-synology-drive-api-client-instead-of-the-synology-drive-api-library)
above for a case where this took an extra fix to get right, and
`tests/test_synology_client.py` / `tests/test_config.py` for the regression
tests guarding it.

**2FA note:** `prt01` is a machine account used only by this service. If
DSM-wide two-factor authentication is enforced, exclude `prt01` from it (DSM
Control Panel -> User -> the account -> "Allowed to skip 2-factor
authentication"), rather than trying to feed it a rotating TOTP code. A
static `SYNOLOGY_OTP_CODE` is supported for completeness but is not a
substitute for a real TOTP generator and will not work for ongoing use.

## Security

Container-level hardening (see `docker-compose.yml`): runs as a fixed
non-root user (1048:100, matching `prt01`), `read_only: true` root
filesystem (only `/incoming`, `/data`, and a `/tmp` tmpfs are writable),
`cap_drop: [ALL]`, `no-new-privileges`, no published ports, no Docker
socket, not on `smb1_network` (least privilege -- it only needs outbound
HTTPS to the NAS's own DSM port). Credential handling is covered under
[Secrets and credentials](#secrets-and-credentials) above.

**Image vulnerability scan** (`docker scout cves`): a `python:3.12-slim`
single-stage image was the initial choice, and scanned at 2 Critical / 2
High / 11 Medium / 29 Low / 5 Unspecified -- the usual long tail of Debian
base-OS package CVEs (glibc, systemd, coreutils, `perl-base`, etc.), almost
none of it reachable here (no shell exposed, no untrusted local multi-user
input, no exposed port). Rather than accept that as "good enough given the
threat model", the Dockerfile is now a multi-stage build: dependencies are
installed in a `python:3.11-slim` builder stage, and the final image is
[Google's distroless `python3-debian12`](https://github.com/GoogleContainerTools/distroless)
base, which ships nothing beyond the Python 3.11 runtime itself -- no
shell, no package manager, no coreutils, no `perl`. That takes the scan to
**0 Critical / 0 High / 0 Medium / 0 Low**, and the image shrank from ~46 MB
to ~20 MB. The builder stage deliberately matches distroless's Python 3.11
so `charset_normalizer`'s compiled extension (a `requests` transitive
dependency) stays ABI-compatible instead of silently falling back to its
pure-Python path. `pip-audit` against the actual application dependencies
(`requests` and its transitive deps) independently reported no known
vulnerabilities. Every change here was re-verified with the same full
functional smoke test (non-root UID/GID resolution, all imports, the
detect/stabilize/upload/retry log sequence, healthcheck) each step of the
way -- see `uploader/Dockerfile` for the exact stages.

Re-run the scan yourself after any base image bump:
```bash
docker scout cves scanner-drive-bridge-uploader:0.2.0
```

The 0/0/0/0 result above reflects the state at the time the distroless
migration was made, not a permanent guarantee -- new CVEs get published
against already-released package versions, and `distroless/python3-debian12`
carries whatever OS-level shared libraries (glibc, libssl, libsqlite3,
zlib, etc.) Python's own stdlib links against, each with its own CVE
history. This is now checked continuously instead of manually: `ci.yml`'s
`build-image` job fails a PR on any CRITICAL finding with an available fix,
and `.github/workflows/weekly-image-scan.yml` runs the fuller CRITICAL+HIGH
picture weekly (same cadence as Dependabot) without blocking merges --
HIGH findings in OS packages often trail Google's own distroless rebuild
cadence by days, so gating every PR on them would block unrelated work for
something no code change here can fix.

## Scanner flow (unchanged)

The scanner's own configuration does not need to change. It still connects
to the same fixed `SMB1_STATIC_IP` over SMB1/NT1 with the same
compatibility flags as before (`server/client min/max protocol = NT1`,
`ntlm auth`, `lanman auth`,
signing and encryption disabled, recycle bin disabled via `-r`). The only
thing that changed underneath it is where `/share` is backed by
(`scanner_incoming`, a Docker volume, instead of a bind mount to
`/volume1/printer`).

## Backup considerations

- `scanner_incoming` (the shared inbox volume) should be treated as
  transient working storage, not a backup target -- files only live there
  until upload succeeds.
- `uploader_state` (the SQLite ledger + heartbeat file) is useful to
  preserve across restarts for a clean idempotency history, but is not
  precious: if it is lost, the worst case is that files still sitting in
  `/incoming` get re-hashed and re-uploaded from scratch (still protected by
  `conflict_action=autorename`, so nothing gets overwritten). It is not a
  substitute for backing up the Team Folder `printer` itself, which is a
  normal DSM shared folder and should be covered by your existing Hyper
  Backup / Snapshot Replication policy exactly as before.
- `/volume2/docker/smb1-printer/{state,log,cache}` are unchanged from the
  previous Samba setup and should keep whatever backup treatment they had.

## Troubleshooting

- **`OCI runtime exec failed: exec: "sh": executable file not found`** when
  opening a console (Portainer's Console feature, or `docker exec -it ...
  sh`). The image is distroless -- there is no shell at all, by design (see
  [Security](#security)). Use `python3` as the exec target instead: in
  Portainer's Console dialog, replace the command field (usually
  pre-filled with `/bin/sh`) with `python3` to get an interactive
  interpreter, or run a specific one-off command directly, e.g.
  `docker exec drive-uploader python3 -m scanner_drive_bridge.main healthcheck`
  (this works fine without a shell since `docker exec` runs that exact
  command, no shell resolution involved). From an interactive `python3`
  console: `print(open('/data/heartbeat.json').read())` to inspect the
  heartbeat, or `from scanner_drive_bridge.main import run_healthcheck;
  run_healthcheck()` for the healthcheck (calling the module as `-m ...
  healthcheck` there would raise `SystemExit` into the REPL instead).
- **`drive-uploader` can't reach the NAS.** It intentionally is not on
  `smb1_network`. If your Docker network setup doesn't let the default
  bridge network reach the NAS's own DSM port, add it to `smb1_network`
  too (uncomment/add a `networks: - smb1_network` entry for `drive-uploader`
  in `docker-compose.yml`) rather than opening host networking.
- **Login works via browser but the service reports `error_code 103` or
  similar.** Check the log line `discovered Synology API versions: ...`
  logged at startup -- it shows what this NAS actually advertises for
  `SYNO.API.Auth` / `SYNO.SynologyDrive.Files` / `SYNO.SynologyDrive.TeamFolders`.
  A mismatch here is the first thing to check against DSM's own API
  documentation for this specific version.
- **Login fails specifically over plain HTTP or through a proxy that
  strips POST bodies.** Login intentionally sends credentials via the POST
  body instead of the query string (see above). If this specific DSM/Drive
  Server build rejects a POST login for some reason, that is a one-line
  change back to `params=` in `SynologyDriveClient.login()` -- note that
  doing so would put the password back in the query string, which is an
  accepted trade-off only if it turns out to be strictly necessary.
- **Uploads always fail with "destination team folder was not found".** The
  Team Folder `printer` must already exist in Synology Drive (Drive ->
  Admin Console -> Team Folders) before this service can write to it; it
  does not create it for you.
- **A response-shape mismatch.** `list_team_folders`/`list_folder` parsing
  is intentionally defensive (`_extract_items` in `synology.py` handles
  several plausible shapes), and logs the raw response's keys at `DEBUG`
  level if none match, to make this diagnosable without ever logging file
  contents or secrets. Run with `LOG_LEVEL=DEBUG` if uploads seem to
  succeed but folder verification doesn't recognize the result.
- **Healthcheck reports unhealthy.** It only triggers on (a) the worker
  loop's heartbeat file being stale beyond `HEALTHCHECK_MAX_LOOP_AGE_SECONDS`
  (default 120s -- suggests the process is stuck, not just that Synology is
  briefly unreachable), or (b) the oldest pending file exceeding
  `HEALTHCHECK_MAX_BACKLOG_AGE_SECONDS` (default 6h -- a real, long-lived
  backlog). Check `docker compose logs drive-uploader` and
  `docker compose exec drive-uploader cat /data/heartbeat.json` for
  `last_error`.

## Upgrading

```bash
git pull
docker compose build drive-uploader
docker compose up -d
```

`uploader_state` (SQLite + heartbeat) and `scanner_incoming` persist across
this; in-flight/pending files and their retry history are preserved. Watch
`docker compose logs -f drive-uploader` after upgrading for the startup
sequence (authentication, destination verification, interrupted-upload
reconciliation).

## Rollback

To go back to the previous direct-bind-mount Samba setup:

1. `docker compose down` (this stops both containers; `scanner_incoming`
   and `uploader_state` are left intact).
2. Restore the previous `docker-compose.yml` (the one binding
   `/volume1/printer:/share` directly, with no `drive-uploader` service).
3. Before starting it, copy out anything still sitting in the
   `scanner_incoming` volume that hasn't been uploaded yet:
   ```bash
   docker run --rm -v scanner-drive-bridge_scanner_incoming:/src -v /volume1/printer:/dst \
     alpine cp -a /src/. /dst/
   ```
4. `docker compose up -d` with the restored file.

This service was designed so rollback never has to race a deletion: nothing
in `/incoming` is ever removed except after a confirmed-successful Drive API
upload, so step 3 always has exactly the files that never made it in.

## Development

```bash
cd uploader
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The test suite (60+ cases) mocks the Synology API entirely (no network
calls) and covers: file stabilization (including that the settle interval
is real elapsed time, independent of poll frequency), conflict/duplicate
handling, retry backoff and its escalation to "permanent failure" logging,
the source file being kept on failure and removed only on confirmed
success (or kept indefinitely / cleaned up after `LOCAL_RETENTION_HOURS`
when `DELETE_AFTER_UPLOAD=false`), crash/restart idempotency (including
reconciliation against a remote listing), API response parsing across a
few plausible shapes, secret handling (never logged, redacted from
network-error messages, `_FILE`-based secrets), and that a broken/unreadable
file cannot crash the worker loop.

## Verified compatibility

Covered by automated tests, entirely mocked (no network calls): the full
suite described in [Development](#development) above, plus `docker compose
config` and a from-scratch image build.

Confirmed by running the full pipeline end to end against a real DSM 7.4.1
/ Synology Drive Server 4.0.3 instance with a real legacy scanner over
SMB1: a scan written over SMB1, detected, stabilized, uploaded through
`SYNO.SynologyDrive.Files`, and appearing in the destination Team Folder
with no manual `synotifyd-rescan`, plus correct filename-conflict handling
and correct crash/restart idempotency under real conditions. That process
is also where the following were found and fixed -- worth knowing about if
you're adapting this for a different DSM version or a different scanner:

- The real upload parameter shape for `SYNO.SynologyDrive.Files` on this
  DSM/Drive Server combination is `path` (the full destination file path,
  folder plus filename) and `type: "file"`, not `dest_folder_path` -- see
  [above](#why-a-hand-written-synology-drive-api-client-instead-of-the-synology-drive-api-library).
  If you're on a different DSM/Drive Server version, check the
  `discovered Synology API versions` log line at startup and be ready for
  the parameter shape to differ again; get the full raw response body
  before assuming a fix.
- A multi-stage Dockerfile `COPY --from` ownership bug only shows up
  against a real Docker named/bind-mounted volume, never a bare `docker
  run` or a bind mount to an arbitrary host path -- always test file
  ownership with the same kind of volume your compose file actually uses.
- `STABILITY_INTERVAL_SECONDS` needs to be real elapsed time independent
  of `SCAN_INTERVAL_SECONDS` (fixed in `scanner.py`) -- with a slow or
  flaky SMB1 transfer, too short a settle margin doesn't just risk an
  incomplete upload, grabbing a file the scanner still has open for
  writing can crash the scanner's own SMB session.
- Some scanners infer their own next filename by listing the destination
  SMB folder -- see `DELETE_AFTER_UPLOAD` / `LOCAL_RETENTION_HOURS` above
  if yours does the same and gets confused by an always-empty folder.

## License

This project is licensed under the [MIT License](LICENSE).
