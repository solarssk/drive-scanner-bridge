# The Synology Drive client

**In short:** the project has its own small client for the Synology Drive API, because the
library that was reviewed disables TLS verification for typical NAS addresses, pulls in
`selenium`, and does not match this NAS. This page lists what was found and what has been
verified on real hardware.

## Contents

- [Why a hand-written client](#why-a-hand-written-client)
- [What the client does](#what-the-client-does)
- [Compatibility](#compatibility)

## Why a hand-written client

Before writing code, the library
[`zbjdonald/synology-drive-api`](https://github.com/zbjdonald/synology-drive-api) was
reviewed as a dependency. It was rejected:

| Concern | The library | This client |
|---|---|---|
| Maintenance | Unmaintained: the last commit is from 18 December 2023 | Small enough to own |
| TLS | Forces `verify=False` for any HTTPS host that looks like an IPv4 literal (`netloc.count('.') >= 3`), which is how most NAS devices are reached on a LAN. `SYNOLOGY_VERIFY_TLS` and `SYNOLOGY_CA_FILE` would have no effect. | Verification is always an explicit choice |
| Dependencies | Requires `selenium` unconditionally, for a spreadsheet-conversion feature this service never uses | Only `requests` |
| API versions | A hardcoded `version=2`. An open issue reports `error_code 103` ("method does not exist") at login, which fits version drift. | Versions are discovered from the NAS |
| Upload call | Right shape (`POST entry.cgi`, `method=upload`, multipart file) but parameters (`dest_folder_path`) from an older API version | Parameters verified on a real NAS; see [Compatibility](#compatibility) |

## What the client does

[`synology.py`](../uploader/scanner_drive_bridge/synology.py) is a small client of about
250 lines. Its only dependency is `requests`.

- **TLS is always an explicit choice.** `SYNOLOGY_VERIFY_TLS` and `SYNOLOGY_CA_FILE` are
  honored, and verification is never downgraded silently.
- **API versions are discovered, not hardcoded.** At connect time it calls
  `SYNO.API.Info` to learn which versions this NAS supports. This protects against the
  version drift behind the `error_code 103` problem above.
- **Credentials go in the POST body.** They are never put in the query string; see
  [security.md](security.md#secrets-and-credentials).

This paid off in practice. On a real DSM 7.4.1 with Synology Drive Server 4.0.3,
`SYNO.API.Info` reported `SYNO.SynologyDrive.Files` at version **11**, far from the
library's fixed `version=2`. That version's `upload` method needs a different set of
parameters.

## Compatibility

**Tested without a NAS.** The automated tests mock the Synology API completely and make
no network calls. CI also runs `docker compose config` and builds the image from scratch.

**Tested on real hardware.** The full pipeline ran end to end against a DSM 7.4.1 /
Synology Drive Server 4.0.3 instance with a real legacy scanner over SMB1. A scan was
written over SMB1, detected, stabilized, uploaded through `SYNO.SynologyDrive.Files`, and
appeared in the Team Folder with no manual `synotifyd-rescan`. Filename conflicts and
crash-and-restart behavior were also correct under real conditions.

That testing found several things worth knowing if you adapt the project to a different
DSM version or scanner:

- **The upload parameters.** On this DSM and Drive Server combination, `upload` needs
  `path` (the full destination file path: folder plus filename) and `type: "file"`. It
  does not accept `dest_folder_path`. On a different version, check the
  `discovered Synology API versions` log line at startup and expect the parameters to
  differ again. Read the full raw response body before assuming a fix.
- **File ownership in the image.** A multi-stage Dockerfile `COPY --from` ownership bug
  shows up only with a real Docker named volume or bind mount, not with a bare
  `docker run`. Test ownership with the same kind of volume the compose file uses.
- **Settle time must be real time.** `STABILITY_INTERVAL_SECONDS` has to be elapsed time,
  independent of `SCAN_INTERVAL_SECONDS` (fixed in `scanner.py`). With a slow or flaky
  SMB1 transfer, a short margin does more than risk an incomplete upload: taking a file
  the scanner still has open can crash the scanner's own SMB session.
- **Scanners that number their own files.** Some scanners choose the next filename by
  listing the share. If yours does, see `DELETE_AFTER_UPLOAD` and `LOCAL_RETENTION_HOURS`
  in [configuration.md](configuration.md#the-local-inbox).
