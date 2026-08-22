import hashlib

import pytest

from scanner_drive_bridge.state import StateStore, hash_file


@pytest.fixture
def store(tmp_path):
    s = StateStore(tmp_path / "state.db")
    yield s
    s.close()


def test_hash_file_matches_hashlib(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes(b"hello world" * 1000)

    digest, size = hash_file(path)

    assert digest == hashlib.sha256(b"hello world" * 1000).hexdigest()
    assert size == len(b"hello world" * 1000)


def test_upsert_pending_creates_row(store):
    record = store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)

    assert record.sha256 == "hash1"
    assert record.state == "pending"
    assert record.attempts == 0


def test_upsert_pending_is_idempotent(store):
    store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)
    store.schedule_retry("hash1", 5, "boom", now=1001.0)

    # rediscovering the same file (e.g. after a restart) must not reset attempts
    record = store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1002.0)

    assert record.attempts == 1
    assert record.last_error == "boom"


def test_mark_uploaded_transitions_state(store):
    store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)
    store.mark_uploading("hash1", now=1001.0)

    store.mark_uploaded("hash1", "SCN_0001.pdf", "file-id-123", now=1002.0)

    record = store.get("hash1")
    assert record.state == "uploaded"
    assert record.uploaded_name == "SCN_0001.pdf"
    assert record.uploaded_file_id == "file-id-123"


def test_schedule_retry_increments_attempts_and_sets_next_retry_at(store):
    store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)

    store.schedule_retry("hash1", 15, "network error", now=1000.0)

    record = store.get("hash1")
    assert record.attempts == 1
    assert record.state == "pending"
    assert record.next_retry_at == 1015.0
    assert record.last_error == "network error"


def test_due_pending_respects_next_retry_at(store):
    store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)
    store.schedule_retry("hash1", 15, "err", now=1000.0)

    assert store.due_pending(now=1010.0) == []
    due = store.due_pending(now=1016.0)
    assert len(due) == 1
    assert due[0].sha256 == "hash1"


def test_uploaded_before_respects_cutoff(store):
    store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)
    store.mark_uploaded("hash1", "SCN_0001.pdf", "file-id", now=2000.0)

    assert store.uploaded_before(1999.0) == []
    due = store.uploaded_before(2000.0)
    assert len(due) == 1
    assert due[0].sha256 == "hash1"


def test_uploaded_before_ignores_non_uploaded_rows(store):
    store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)  # still pending
    assert store.uploaded_before(9999999.0) == []


def test_in_flight_uploading_returns_uploading_rows(store):
    store.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)
    store.mark_uploading("hash1", now=1001.0)
    store.upsert_pending("hash2", "SCN_0002.pdf", 100, now=1000.0)

    in_flight = store.in_flight_uploading()

    assert [r.sha256 for r in in_flight] == ["hash1"]


def test_counts_reports_failed_as_pending_with_attempts(store):
    store.upsert_pending("hash1", "a.pdf", 100, now=1000.0)
    store.upsert_pending("hash2", "b.pdf", 100, now=1000.0)
    store.schedule_retry("hash2", 5, "err", now=1000.0)

    counts = store.counts(now=1000.0)

    assert counts["pending"] == 2
    assert counts["failed"] == 1


def test_delete_removes_row(store):
    store.upsert_pending("hash1", "a.pdf", 100, now=1000.0)
    store.delete("hash1")
    assert store.get("hash1") is None


def test_restart_recovery_reloads_rows_from_disk(tmp_path):
    db_path = tmp_path / "state.db"
    store1 = StateStore(db_path)
    store1.upsert_pending("hash1", "SCN_0001.pdf", 100, now=1000.0)
    store1.mark_uploading("hash1", now=1001.0)
    store1.close()

    store2 = StateStore(db_path)
    try:
        record = store2.get("hash1")
        assert record is not None
        assert record.state == "uploading"
        assert store2.in_flight_uploading()[0].sha256 == "hash1"
    finally:
        store2.close()
