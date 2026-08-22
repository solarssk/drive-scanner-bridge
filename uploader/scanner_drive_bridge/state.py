"""SQLite-backed idempotency ledger for files moving through the bridge.

Rows are keyed by content SHA-256, not by filename: the scanner reuses
filenames (SCN_0001.pdf, SCN_0002.pdf, ...) across genuinely different
scans, so filename alone cannot answer "have I already handled this file".
Content hash is the identity that survives a crash/restart even if the
inbox file was renamed or the process has no memory of it, which is what
makes restart/crash idempotency work (see Worker._reconcile_in_flight).

If two files ever have byte-identical content, they are treated as the
same document: the duplicate is removed locally without a second upload.
This is always logged explicitly (never silent) -- see
Worker._handle_new_stable_file.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_HASH_CHUNK_SIZE = 1024 * 1024

STATE_PENDING = "pending"
STATE_UPLOADING = "uploading"
STATE_UPLOADED = "uploaded"


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


@dataclass(frozen=True)
class FileRecord:
    sha256: str
    original_name: str
    size: int
    state: str
    attempts: int
    next_retry_at: float
    last_error: Optional[str]
    uploaded_name: Optional[str]
    uploaded_file_id: Optional[str]
    first_seen_at: float
    updated_at: float


class StateStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                sha256 TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_retry_at REAL NOT NULL DEFAULT 0,
                last_error TEXT,
                uploaded_name TEXT,
                uploaded_file_id TEXT,
                first_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def _to_record(row: sqlite3.Row) -> FileRecord:
        return FileRecord(**{key: row[key] for key in row.keys()})

    def get(self, sha256: str) -> Optional[FileRecord]:
        row = self._conn.execute("SELECT * FROM files WHERE sha256 = ?", (sha256,)).fetchone()
        return self._to_record(row) if row else None

    def upsert_pending(self, sha256: str, original_name: str, size: int, now: float) -> FileRecord:
        self._conn.execute(
            """
            INSERT INTO files (sha256, original_name, size, state, attempts, next_retry_at,
                                first_seen_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            ON CONFLICT(sha256) DO NOTHING
            """,
            (sha256, original_name, size, STATE_PENDING, now, now, now),
        )
        self._conn.commit()
        record = self.get(sha256)
        assert record is not None
        return record

    def mark_uploading(self, sha256: str, now: float) -> None:
        self._conn.execute(
            "UPDATE files SET state = ?, updated_at = ? WHERE sha256 = ?",
            (STATE_UPLOADING, now, sha256),
        )
        self._conn.commit()

    def mark_uploaded(
        self, sha256: str, uploaded_name: str, uploaded_file_id: Optional[str], now: float
    ) -> None:
        self._conn.execute(
            """
            UPDATE files
            SET state = ?, uploaded_name = ?, uploaded_file_id = ?, last_error = NULL, updated_at = ?
            WHERE sha256 = ?
            """,
            (STATE_UPLOADED, uploaded_name, uploaded_file_id, now, sha256),
        )
        self._conn.commit()

    def schedule_retry(self, sha256: str, delay_seconds: float, error: str, now: float) -> None:
        self._conn.execute(
            """
            UPDATE files
            SET state = ?, attempts = attempts + 1, next_retry_at = ?, last_error = ?, updated_at = ?
            WHERE sha256 = ?
            """,
            (STATE_PENDING, now + delay_seconds, error, now, sha256),
        )
        self._conn.commit()

    def delete(self, sha256: str) -> None:
        self._conn.execute("DELETE FROM files WHERE sha256 = ?", (sha256,))
        self._conn.commit()

    def due_pending(self, now: float) -> list[FileRecord]:
        rows = self._conn.execute(
            "SELECT * FROM files WHERE state = ? AND next_retry_at <= ? ORDER BY first_seen_at",
            (STATE_PENDING, now),
        ).fetchall()
        return [self._to_record(row) for row in rows]

    def in_flight_uploading(self) -> list[FileRecord]:
        rows = self._conn.execute("SELECT * FROM files WHERE state = ?", (STATE_UPLOADING,)).fetchall()
        return [self._to_record(row) for row in rows]

    def uploaded_before(self, cutoff: float) -> list[FileRecord]:
        """Rows confirmed uploaded at or before `cutoff` (a unix timestamp).
        `updated_at` is frozen at the upload-success moment once a row
        reaches the `uploaded` state, so it doubles as "uploaded_at"."""
        rows = self._conn.execute(
            "SELECT * FROM files WHERE state = ? AND updated_at <= ?",
            (STATE_UPLOADED, cutoff),
        ).fetchall()
        return [self._to_record(row) for row in rows]

    def counts(self, now: Optional[float] = None) -> dict:
        pending = self._conn.execute(
            "SELECT COUNT(*) FROM files WHERE state = ?", (STATE_PENDING,)
        ).fetchone()[0]
        failed = self._conn.execute(
            "SELECT COUNT(*) FROM files WHERE state = ? AND attempts > 0", (STATE_PENDING,)
        ).fetchone()[0]
        uploading = self._conn.execute(
            "SELECT COUNT(*) FROM files WHERE state = ?", (STATE_UPLOADING,)
        ).fetchone()[0]
        uploaded = self._conn.execute(
            "SELECT COUNT(*) FROM files WHERE state = ?", (STATE_UPLOADED,)
        ).fetchone()[0]
        oldest_age = None
        row = self._conn.execute(
            "SELECT MIN(first_seen_at) FROM files WHERE state IN (?, ?)",
            (STATE_PENDING, STATE_UPLOADING),
        ).fetchone()
        if row and row[0] is not None and now is not None:
            oldest_age = now - row[0]
        return {
            "pending": pending,
            "failed": failed,
            "uploading": uploading,
            "uploaded": uploaded,
            "oldest_pending_age_seconds": oldest_age,
        }

    def close(self) -> None:
        self._conn.close()
