# Configuration

**In short:** every setting of the uploader, with its default and what it does. Set them in
`.env` (Compose) or in the stack's environment section (Portainer). The container reads
them once, at start, so restart it after a change.

## Contents

- [How settings reach the container](#how-settings-reach-the-container)
- [Connection to Synology Drive](#connection-to-synology-drive)
- [Detecting new files](#detecting-new-files)
- [Retries](#retries)
- [The local inbox](#the-local-inbox)
- [Health check and logging](#health-check-and-logging)
- [Compose-only settings](#compose-only-settings)
- [Paths inside the container](#paths-inside-the-container)

## How settings reach the container

- Copy `.env.example` to `.env` and edit it. `.env` is ignored by git.
- The `In .env` column in the tables below says whether the shipped compose file passes
  the setting on.

  > [!NOTE]
  > A setting marked "no" is read by the service but cannot be changed through `.env`.
  > Use `docker compose exec -e NAME=value ...` for a one-off command, or add it to the
  > `environment:` block of `docker-compose.yml`.
- Secrets can be given as a value (`NAME`) or as the path of a file that contains it
  (`NAME_FILE`). If both are set, the file wins. The shipped compose file uses files; see
  [security.md](security.md#secrets-and-credentials).
- An empty value means "use the default". A value that is not a valid number (or, for
  `RETRY_BACKOFF_SECONDS`, not a list of integers) stops the service at startup with an
  error that names the setting. A missing required setting stops it the same way and
  lists everything that is missing.
- Booleans accept `1`, `true`, `yes` and `on` (any case) as true. Any other non-empty
  value means false.

## Connection to Synology Drive

| Setting | Default | In .env | Meaning |
|---|---|---|---|
| `SYNOLOGY_HOST` | none, **required** | yes | URL of the NAS DSM, for example `https://192.0.2.10:5001`. |
| `SYNOLOGY_USERNAME` | `prt01` in compose, **required** in the service | yes | DSM account that owns the uploads. |
| `SYNOLOGY_PASSWORD_FILE` | `/run/secrets/synology_password` | no | File with the DSM password. **Required**: one of `SYNOLOGY_PASSWORD` or this file. |
| `SYNOLOGY_PASSWORD` | none | no | The password itself. Use the file in real deployments. |
| `SYNOLOGY_DESTINATION` | `/team-folders/printer` | yes | Drive path that receives the files. The Team Folder must already exist. |
| `SYNOLOGY_VERIFY_TLS` | `true` | yes | Verify the NAS certificate. Leave it on; see [security.md](security.md#tls-to-the-nas). |
| `SYNOLOGY_CA_FILE` | `/run/secrets/synology_ca` | no | CA certificate for a self-signed or internal CA. Ignored (with a warning) if the file is missing. |
| `SYNOLOGY_OTP_CODE` | none | no | A fixed one-time code. Supported for completeness, useless for ongoing use; see [security.md](security.md#two-factor-authentication). |
| `CONFLICT_ACTION` | `autorename` | yes | What Synology does when a file with the same name exists. `autorename` never overwrites. |
| `HTTP_TIMEOUT_SECONDS` | `30` | no | Timeout of each request to the NAS. |

## Detecting new files

How a file is judged complete is explained in
[architecture.md](architecture.md#deciding-when-a-file-is-complete). For a slow or flaky
SMB1 transfer, raise `STABILITY_CHECKS` and `STABILITY_INTERVAL_SECONDS`. The settle time
is roughly their product.

| Setting | Default | In .env | Meaning |
|---|---|---|---|
| `SCAN_INTERVAL_SECONDS` | `2` | yes | How often `/incoming` is listed. Affects responsiveness only. |
| `STABILITY_INTERVAL_SECONDS` | `2` | yes | Minimum real time between two checks that count. |
| `STABILITY_CHECKS` | `2` | yes | How many identical checks make a file stable. Must be at least `1`. |

## Retries

| Setting | Default | In .env | Meaning |
|---|---|---|---|
| `RETRY_BACKOFF_SECONDS` | `5,15,30,60,300` | yes | Comma-separated wait times in seconds. The last value repeats forever. |

## The local inbox

By default `/incoming` is a staging area that is emptied after each confirmed upload.

| Setting | Default | In .env | Meaning |
|---|---|---|---|
| `DELETE_AFTER_UPLOAD` | `true` | yes | Delete the local file after the upload is confirmed. |
| `LOCAL_RETENTION_HOURS` | unset | yes | Only with `DELETE_AFTER_UPLOAD=false`: remove a kept copy this many hours after its confirmed upload. Unset keeps copies forever. |
| `TIMESTAMP_UPLOAD_FILENAME` | `false` | yes | Prefix the name **sent to Synology Drive** with today's date, for example `2026-08-22_SCN_0001.pdf`. Cosmetic. |

> [!TIP]
> **When to set `DELETE_AFTER_UPLOAD=false`.** Some scanners pick their next filename by
> listing the share and counting past the highest number. If the share is always empty,
> such a scanner can keep reusing the same name. Keeping the uploaded files in `/incoming`
> fixes that.

| Topic | How it behaves |
|---|---|
| Duplicates with `DELETE_AFTER_UPLOAD=false` | Content-hash deduplication still guarantees a kept file is never uploaded twice. Only disk usage changes. |
| `LOCAL_RETENTION_HOURS` | Stops kept copies from growing without bound while leaving the scanner enough history to number correctly. Cleanup checks the content hash first, so a new scan that reuses an old name is never removed. |
| `TIMESTAMP_UPLOAD_FILENAME` | Never changes the local filename. The local name must stay exactly as the scanner wrote it, or the numbering above breaks. |

## Health check and logging

| Setting | Default | In .env | Meaning |
|---|---|---|---|
| `HEALTHCHECK_MAX_LOOP_AGE_SECONDS` | `120` | yes | The container is unhealthy if the worker heartbeat is older than this. Points to a stuck process. |
| `HEALTHCHECK_MAX_BACKLOG_AGE_SECONDS` | `21600` (6 h) | yes | The container is unhealthy if the oldest pending file is older than this. Points to a long-lived backlog. |
| `LOG_LEVEL` | `INFO` | yes | Python log level. Use `DEBUG` to see the raw shape of unexpected API responses. |

A short Synology outage does not make the container unhealthy. Run the check by hand with
`docker compose exec drive-uploader python3 -m scanner_drive_bridge.main healthcheck`.

## Compose-only settings

These are used by `docker-compose.yml` itself and never reach the service.

| Setting | Required | Meaning |
|---|---|---|
| `SMB1_STATIC_IP` | yes | A free fixed IP on your `smb1_network` subnet. The scanner is configured to connect to this exact address. |
| `SMB_PRT01_PASSWORD` | yes | Samba password of the `prt01` account used by the scanner. The `dperson/samba` image accepts it only as a command-line argument, so it goes through `.env`. |
| `PROJECT_DIR` | no | Absolute path of this repository on the NAS. Needed only when the compose file is managed separately, as in Portainer, so the `secrets` bind mount can be found. Defaults to `.`. |

## Paths inside the container

| Variable | Default | Content |
|---|---|---|
| `INCOMING_DIR` | `/incoming` | The shared inbox (the `scanner_incoming` volume). |
| `STATE_DB_PATH` | `/data/state.db` | The SQLite ledger (the `uploader_state` volume). |
| `HEARTBEAT_PATH` | `/data/heartbeat.json` | Written by the worker loop, read by the health check. |

These have no reason to change with the shipped compose file.
