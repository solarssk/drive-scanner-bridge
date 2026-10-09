# Architecture

This page explains why the bridge exists, how a scan travels from the scanner to
Synology Drive, and which guarantees the bridge gives along the way. For the settings
that tune this behavior, see [configuration.md](configuration.md).

## Contents

- [Why the bridge exists](#why-the-bridge-exists)
- [How a scan travels](#how-a-scan-travels)
- [Network and privileges](#network-and-privileges)
- [The scanner side](#the-scanner-side)
- [How a file is processed](#how-a-file-is-processed)
- [No duplicates and no lost scans](#no-duplicates-and-no-lost-scans)
- [Deciding when a file is complete](#deciding-when-a-file-is-complete)
- [Retries](#retries)

## Why the bridge exists

On the NAS this project was built for, Synology Drive has a confirmed bug. The
`synotifyd` service receives the filesystem change event and creates the queue file
(`@drive.synotifyd.queue.toread.*`), and the queue generation counter goes up. But the
event is sometimes never consumed: `minimum gen in EventManager` stays at `0`, and the new
file never appears in Synology Drive. The file exists on disk and shows up in File
Station right away.

The only reliable workaround found was to rescan by hand:

```bash
/var/packages/SynologyDrive/target/bin/cloud-control synotifyd-rescan --view_id 21 --path /
```

That is a workaround, and this project does not rely on it. Instead, the bridge avoids
the filesystem-event pipeline completely:

1. Scans never get written to the Team Folder directly. They land in a private inbox.
2. `drive-uploader` uploads each file through the Synology Drive API
   (`SYNO.SynologyDrive.Files`). This is the same path the Synology Drive client uses.
3. When the API accepts the upload, Drive already knows about the file. No separate
   notification step remains that could fail.

## How a scan travels

```text
Legacy scanner
      |
      | SMB1 / NT1
      v
smb1-printer (fixed IP on smb1_network)
      |
      | writes into the shared "scanner_incoming" Docker volume
      v
scanner_incoming (mounted at /incoming in drive-uploader)
      |
      v
drive-uploader
      |
      | HTTPS -> SYNO.SynologyDrive.Files "upload"
      v
Synology Drive
      |
      v
Team Folder "printer" (/volume1/printer, indexed correctly)
```

| Component | Role |
|---|---|
| `smb1-printer` | A Samba container (`dperson/samba`) forced to the SMB1/NT1 dialect, because the scanner speaks nothing newer. It no longer mounts `/volume1/printer`. |
| `scanner_incoming` | A Docker volume shared by both containers. Treat it as working storage: files stay there only until the upload is confirmed. |
| `drive-uploader` | This project's Python service. It watches `/incoming` and uploads to Synology Drive. |
| Team Folder `printer` | A normal DSM shared folder. Only `drive-uploader` writes to it, through the Drive API. |

## Network and privileges

`drive-uploader` is not on `smb1_network`. It only needs outbound HTTPS to the DSM port
of the NAS, not access to the scanner or the Samba container, so it stays off that
network (least privilege). It reaches the NAS through the default Docker bridge network.
If your routing does not allow that, see
[Troubleshooting](troubleshooting.md#drive-uploader-cannot-reach-the-nas).

## The scanner side

The scanner configuration does not change. It still connects to the same fixed
`SMB1_STATIC_IP` over SMB1/NT1, with the same Samba compatibility settings as before:

- `server`/`client` protocol fixed to NT1
- `ntlm auth` and `lanman auth` enabled
- signing and encryption disabled
- recycle bin disabled (`-r`)

The one change is where the share is stored: `/share` is backed by the
`scanner_incoming` volume instead of a bind mount to `/volume1/printer`.

## How a file is processed

1. **Detect.** The worker lists `/incoming` every `SCAN_INTERVAL_SECONDS`.
2. **Wait until complete.** A file is "stable" when its size and modification time stay
   the same across several checks. See [Deciding when a file is complete](#deciding-when-a-file-is-complete).
3. **Identify.** The worker computes the SHA-256 hash of the content and records it in
   SQLite (`/data/state.db`) with state `pending`.
4. **Upload.** The state becomes `uploading`, the file goes to Synology Drive, and on
   success the state becomes `uploaded`.
5. **Clean up.** With `DELETE_AFTER_UPLOAD=true` (the default), the local file is
   removed only after the `uploaded` state is committed.

## No duplicates and no lost scans

This is the part that does the most damage if it is done carelessly, so the exact rules
are listed here. They are also documented in the `worker.py` and `state.py` docstrings.

1. **Files are identified by content, not by name.** The scanner reuses names such as
   `SCN_0001.pdf`, so a filename cannot answer "did I already handle this file". The
   ledger has one row per SHA-256 hash, with the state `pending`, `uploading` or
   `uploaded`.
2. **A file is deleted only after `uploaded` is committed.** If the process crashes
   between the commit and the delete, a harmless local copy remains. The next time that
   content shows up, its hash is already `uploaded`, so it is removed without a second
   upload. This is always logged (`duplicate content detected ... removing local
   duplicate without re-upload`), never silent.
3. **A failed HTTP response does not prove the upload failed.** If the process stops
   while a row is `uploading`, startup reconciliation (`Worker._reconcile_in_flight`)
   lists the real destination folder and looks for a file with the same name and exact
   size. Only when there is no match does it upload again.
4. **`conflict_action=autorename` is a safety net, not the dedup mechanism.** It covers
   the case where the scanner reuses a name for genuinely different content. The SQLite
   ledger is what prevents duplicates.
5. **Identical content means the same document.** The second copy is removed locally
   and not uploaded again. This is deliberate and always logged.

## Deciding when a file is complete

The scanner may write a file in pieces. Uploading too early would send a partial scan.

Detection is polling, not inotify. The whole premise of this project is that the NAS
filesystem notifications are unreliable, so nothing here depends on them.

- A file is queued when its `(size, mtime)` is identical across `STABILITY_CHECKS`
  consecutive checks, each at least `STABILITY_INTERVAL_SECONDS` apart in real time, and
  the file can be opened for reading.
- The settle time is enforced separately from the polling rate. A fast
  `SCAN_INTERVAL_SECONDS` does not shorten it. This matters because taking (and deleting)
  a file the scanner still has open can make the scanner's own SMB session fail.
- Ignored files: hidden files (`.foo`), editor lock files (`~foo`), and partial-write
  suffixes (`.tmp`, `.part`, `.partial`, `.crdownload`).
- A file reported stable is not reported again while it stays unchanged. Without this, a
  file waiting through retry backoff would be re-hashed and re-logged on every poll.
  The logic is `StabilityTracker` in
  [`scanner.py`](../uploader/scanner_drive_bridge/scanner.py).

## Retries

A failed upload backs off along `RETRY_BACKOFF_SECONDS` (default `5,15,30,60,300`).
When the list runs out, retries continue at the last interval (300 seconds by default).

A file is never given up on and never deleted after a failure. It is deleted only after a
confirmed upload.

The log level shows how bad things are. Failures inside the schedule are logged as
`WARNING`. The moment the schedule is exhausted, the log changes to
`ERROR: permanent upload failure`, and every later attempt stays at `ERROR`. "Permanent"
means "an operator should look at this", not "the service stopped trying".
