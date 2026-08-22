"""Main orchestration loop: detect stable files, upload them, track state.

Idempotency strategy (see README for the full write-up):
  1. Every file is identified by its SHA-256 content hash, tracked in
     `StateStore`, with states pending -> uploading -> uploaded.
  2. `conflict_action` (autorename by default) is Synology's own safety net
     against two *different* files sharing a name.
  3. On startup, any row left in `uploading` (crash mid-upload) is
     reconciled against the real destination folder listing *before* any
     retry is allowed -- we never assume a failed/interrupted HTTP call
     means the upload did not happen.
  4. A file is only deleted locally after its state is durably committed
     to `uploaded` in SQLite. A crash between that commit and the delete
     leaves a harmless leftover local file, which startup reconciliation
     or the next stability poll cleans up (see `_handle_new_stable_file`'s
     duplicate-content branch) without ever re-uploading it.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .scanner import StabilityTracker
from .state import FileRecord, StateStore, hash_file
from .synology import SynologyAPIError, SynologyDriveClient

logger = logging.getLogger(__name__)


def _matches_remote_file(remote: dict, original_name: str, size: int) -> bool:
    """Best-effort match used only for interrupted-upload reconciliation.

    Requires an exact size match plus either an exact name match or the
    remote name starting with the original's stem, to also catch
    autorenamed variants (e.g. "SCN_0001 (1).pdf"). A false negative here
    just causes a redundant (but safe, autorename-protected) re-upload; a
    false positive is guarded against by the size match.
    """
    if remote.get("size") != size:
        return False
    name = remote.get("name", "")
    stem = Path(original_name).stem
    return name == original_name or name.startswith(stem)


class Worker:
    def __init__(
        self,
        config: Config,
        client: SynologyDriveClient,
        state: StateStore,
        stability: StabilityTracker,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._client = client
        self._state = state
        self._stability = stability
        self._clock = clock
        self._sleep = sleep
        self._stop = False

        self.last_auth_success_at: Optional[float] = None
        self.last_upload_at: Optional[float] = None
        self.last_error: Optional[str] = None

    def request_stop(self) -> None:
        self._stop = True

    # -- startup -----------------------------------------------------------

    def startup(self) -> None:
        logger.info("starting scanner-drive-bridge worker")
        try:
            self._client.login()
            self.last_auth_success_at = self._clock()
            logger.info("authenticated to Synology Drive")
        except Exception as exc:  # noqa: BLE001 - must not crash-loop at startup
            self.last_error = str(exc)
            logger.warning(
                "initial authentication failed, will keep retrying during normal operation: %s", exc
            )
        self._verify_destination()
        self._reconcile_in_flight()
        logger.info("startup complete, entering polling loop")

    def _verify_destination(self) -> None:
        try:
            folders = self._client.list_team_folders()
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not verify destination team folder at startup (will proceed anyway): %s", exc)
            return
        name = self._config.synology_destination.rstrip("/").split("/")[-1]
        if any(folder.get("name") == name for folder in folders):
            logger.info("destination team folder '%s' verified", name)
        else:
            logger.warning(
                "destination team folder '%s' was not found in SYNO.SynologyDrive.TeamFolders "
                "listing; uploads will fail until this is corrected",
                name,
            )

    def _reconcile_in_flight(self) -> None:
        interrupted = self._state.in_flight_uploading()
        for record in interrupted:
            logger.warning(
                "found interrupted upload from a previous run, reconciling file=%s", record.original_name
            )
            try:
                remote_files = self._client.list_folder(self._config.synology_destination)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "could not reconcile interrupted upload (will retry later) file=%s error=%s",
                    record.original_name, exc,
                )
                self._state.schedule_retry(
                    record.sha256, self._config.retry_backoff_seconds[0], str(exc), self._clock()
                )
                continue

            match = next(
                (rf for rf in remote_files if _matches_remote_file(rf, record.original_name, record.size)),
                None,
            )
            if match:
                logger.info(
                    "interrupted upload had already succeeded, confirming file=%s uploaded_as=%s",
                    record.original_name, match.get("name"),
                )
                self._state.mark_uploaded(
                    record.sha256, match.get("name", record.original_name), match.get("file_id"), self._clock()
                )
            else:
                logger.info("interrupted upload did not complete, will retry file=%s", record.original_name)
                self._state.schedule_retry(record.sha256, 0, "interrupted-by-restart", self._clock())

    # -- main loop -----------------------------------------------------------

    def run_forever(self) -> None:
        self.startup()
        while not self._stop:
            self._loop_once()
            self._write_heartbeat()
            if not self._stop:
                self._sleep(self._config.scan_interval_seconds)
        self._write_heartbeat()
        logger.info("worker stopped cleanly")

    def _loop_once(self) -> None:
        try:
            stable_paths = self._stability.poll(self._config.incoming_dir)
        except Exception:  # noqa: BLE001
            logger.exception("unexpected error while polling incoming directory")
            return

        for path in stable_paths:
            try:
                self._handle_new_stable_file(path)
            except Exception:  # noqa: BLE001
                logger.exception("unexpected error handling file %s, skipping this cycle", path.name)

        try:
            due = self._state.due_pending(self._clock())
        except Exception:  # noqa: BLE001
            logger.exception("unexpected error reading due uploads")
            return

        for record in due:
            try:
                self._attempt_upload_for_record(record)
            except Exception:  # noqa: BLE001
                logger.exception("unexpected error uploading %s, will retry next cycle", record.original_name)

        if not self._config.delete_after_upload and self._config.local_retention_hours is not None:
            self._cleanup_expired_local_copies()

    def _cleanup_expired_local_copies(self) -> None:
        cutoff = self._clock() - self._config.local_retention_hours * 3600
        try:
            expired = self._state.uploaded_before(cutoff)
        except Exception:  # noqa: BLE001
            logger.exception("unexpected error checking local retention cleanup")
            return
        for record in expired:
            path = self._config.incoming_dir / record.original_name
            if not path.exists():
                continue
            self._safe_remove(path)
            logger.info(
                "removed local copy past retention window (%.1fh) file=%s",
                self._config.local_retention_hours, record.original_name,
            )

    # -- per-file handling ---------------------------------------------------

    def _handle_new_stable_file(self, path: Path) -> None:
        try:
            digest, size = hash_file(path)
        except OSError as exc:
            logger.warning(
                "could not read file for hashing, will retry next cycle file=%s error=%s", path.name, exc
            )
            self._stability.forget(path)
            return

        now = self._clock()
        record = self._state.upsert_pending(digest, path.name, size, now)

        if record.state == "uploaded":
            if self._config.delete_after_upload:
                logger.info(
                    "duplicate content detected file=%s matches previously uploaded file=%s, "
                    "removing local duplicate without re-upload",
                    path.name, record.uploaded_name,
                )
                self._safe_remove(path)
            else:
                logger.info(
                    "duplicate content detected file=%s matches previously uploaded file=%s, "
                    "leaving it in place (DELETE_AFTER_UPLOAD=false) without re-upload",
                    path.name, record.uploaded_name,
                )
            return

        if record.state == "uploading":
            logger.warning("file %s already marked uploading, skipping until next cycle", path.name)
            return

        if record.attempts == 0:
            self._attempt_upload(path, record)

    def _attempt_upload_for_record(self, record: FileRecord) -> None:
        path = self._config.incoming_dir / record.original_name
        try:
            digest, _size = hash_file(path)
        except OSError:
            logger.warning(
                "pending file missing or unreadable, abandoning stale record file=%s", record.original_name
            )
            self._state.delete(record.sha256)
            self._stability.forget(path)
            return

        if digest != record.sha256:
            logger.warning(
                "file content changed since it was queued, abandoning stale record file=%s "
                "(will be re-detected as a new file)",
                record.original_name,
            )
            self._state.delete(record.sha256)
            self._stability.forget(path)
            return

        self._attempt_upload(path, record)

    def _upload_filename(self, original_name: str) -> str:
        """Name sent to Synology Drive. Never affects the local /incoming
        filename (the scanner may depend on that staying exactly as it
        wrote it -- see delete_after_upload)."""
        if not self._config.timestamp_upload_filename:
            return original_name
        date_str = datetime.fromtimestamp(self._clock()).strftime("%Y-%m-%d")
        return f"{date_str}_{original_name}"

    def _attempt_upload(self, path: Path, record: FileRecord) -> None:
        now = self._clock()
        self._state.mark_uploading(record.sha256, now)
        upload_filename = self._upload_filename(path.name)
        logger.info("uploading %s to %s", upload_filename, self._config.synology_destination)
        try:
            with path.open("rb") as fh:
                result = self._client.upload_file(
                    fh,
                    filename=upload_filename,
                    dest_folder_path=self._config.synology_destination,
                    conflict_action=self._config.conflict_action,
                )
            self.last_auth_success_at = self._clock()
        except (SynologyAPIError, OSError) as exc:
            self._handle_upload_failure(record, exc)
            return

        uploaded_name = result.get("name", upload_filename)
        uploaded_file_id = result.get("file_id")
        self._state.mark_uploaded(record.sha256, uploaded_name, uploaded_file_id, self._clock())
        self.last_upload_at = self._clock()
        logger.info(
            "upload successful file=%s uploaded_as=%s file_id=%s", path.name, uploaded_name, uploaded_file_id
        )
        if self._config.delete_after_upload:
            self._safe_remove(path)
            logger.info("removed local file %s", path.name)
        else:
            logger.info("kept local file %s (DELETE_AFTER_UPLOAD=false)", path.name)

    def _handle_upload_failure(self, record: FileRecord, exc: Exception) -> None:
        attempts_next = record.attempts + 1
        backoff = self._config.retry_backoff_seconds
        delay = backoff[min(attempts_next - 1, len(backoff) - 1)]
        self.last_error = str(exc)

        if attempts_next == len(backoff) + 1:
            logger.error(
                "permanent upload failure file=%s after %d attempts, will keep retrying every %ss error=%s",
                record.original_name, attempts_next - 1, delay, exc,
            )
        elif attempts_next > len(backoff) + 1:
            logger.error(
                "upload still failing file=%s attempt=%d retry_in=%ss error=%s",
                record.original_name, attempts_next, delay, exc,
            )
        else:
            logger.warning(
                "upload failed attempt=%d retry_in=%ss file=%s error=%s",
                attempts_next, delay, record.original_name, exc,
            )
        self._state.schedule_retry(record.sha256, delay, str(exc), self._clock())

    @staticmethod
    def _safe_remove(path: Path) -> None:
        try:
            path.unlink()
        except OSError as exc:
            logger.warning(
                "could not remove local file after upload (will not be re-uploaded) file=%s error=%s",
                path.name, exc,
            )

    # -- observability ---------------------------------------------------

    def _write_heartbeat(self) -> None:
        counts = self._state.counts(self._clock())
        payload = {
            "last_loop_at": self._clock(),
            "last_auth_success_at": self.last_auth_success_at,
            "last_upload_at": self.last_upload_at,
            "last_error": self.last_error,
            "pending_count": counts["pending"],
            "failed_count": counts["failed"],
            "uploading_count": counts["uploading"],
            "uploaded_count": counts["uploaded"],
            "oldest_pending_age_seconds": counts["oldest_pending_age_seconds"],
        }
        try:
            tmp_path = self._config.heartbeat_path.with_suffix(".tmp")
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(json.dumps(payload))
            tmp_path.replace(self._config.heartbeat_path)
        except OSError as exc:
            logger.warning("could not write heartbeat file: %s", exc)
