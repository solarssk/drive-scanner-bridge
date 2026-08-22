import hashlib
import logging
from datetime import datetime

from scanner_drive_bridge.scanner import StabilityTracker
from scanner_drive_bridge.state import StateStore
from scanner_drive_bridge.synology import SynologyAPIError
from scanner_drive_bridge.worker import Worker


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeSynologyClient:
    def __init__(self, team_folders=None, remote_files=None, upload_outcomes=None, always_fail=None):
        self.login_calls = 0
        self.upload_calls = []
        self.team_folders = team_folders if team_folders is not None else [{"name": "printer"}]
        self.remote_files = remote_files if remote_files is not None else []
        self._upload_outcomes = list(upload_outcomes or [])
        self._always_fail = always_fail

    def login(self):
        self.login_calls += 1

    def list_team_folders(self):
        return self.team_folders

    def list_folder(self, path):
        return self.remote_files

    def upload_file(self, fileobj, filename, dest_folder_path, conflict_action="autorename"):
        self.upload_calls.append(filename)
        if self._always_fail is not None:
            raise self._always_fail
        if self._upload_outcomes:
            outcome = self._upload_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
        return {"name": filename, "file_id": f"id-{filename}"}


def _build_worker(config, client, clock=None):
    state = StateStore(config.state_db_path)
    stability = StabilityTracker(config.stability_checks)
    clock = clock or FakeClock()
    worker = Worker(config, client, state, stability, clock=clock, sleep=lambda s: None)
    return worker, state, clock


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_source_file_removed_after_successful_upload(make_config):
    config = make_config()
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()  # second unchanged poll satisfies stability_checks=2

    assert not (config.incoming_dir / "SCN_0001.pdf").exists()
    assert client.upload_calls == ["SCN_0001.pdf"]
    record = state.get(_sha(b"scan-content"))
    assert record.state == "uploaded"
    state.close()


def test_upload_filename_gets_date_prefix_when_enabled(make_config):
    # The date prefix is purely for organizing the Team Folder -- it must
    # never touch the local /incoming filename, which the scanner may rely
    # on staying exactly as it wrote it (see delete_after_upload).
    config = make_config(timestamp_upload_filename=True)
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()

    expected_date = datetime.fromtimestamp(clock.now).strftime("%Y-%m-%d")
    expected_name = f"{expected_date}_SCN_0001.pdf"
    assert client.upload_calls == [expected_name]

    record = state.get(_sha(b"scan-content"))
    assert record.original_name == "SCN_0001.pdf"
    assert record.uploaded_name == expected_name
    assert not (config.incoming_dir / "SCN_0001.pdf").exists()  # local delete unaffected
    state.close()


def test_upload_filename_unchanged_by_default(make_config):
    config = make_config()  # timestamp_upload_filename defaults to False
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()

    assert client.upload_calls == ["SCN_0001.pdf"]
    state.close()


def test_source_file_kept_after_successful_upload_when_delete_disabled(make_config):
    # Some scanners infer their next filename by listing the destination
    # folder; if we always clear it, they can get stuck re-using the same
    # name. DELETE_AFTER_UPLOAD=false lets the local copy persist while
    # still never being re-uploaded (dedup is by content hash, not
    # presence/absence of the file).
    config = make_config(delete_after_upload=False)
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()

    assert (config.incoming_dir / "SCN_0001.pdf").exists()
    assert client.upload_calls == ["SCN_0001.pdf"]
    assert state.get(_sha(b"scan-content")).state == "uploaded"

    # a later poll re-discovering the same still-present file must not
    # trigger a second upload, and must not delete it either
    worker._loop_once()
    worker._loop_once()
    assert client.upload_calls == ["SCN_0001.pdf"]
    assert (config.incoming_dir / "SCN_0001.pdf").exists()
    state.close()


def test_rediscovered_uploaded_file_kept_when_delete_disabled(make_config):
    # Directly exercises the "duplicate content, already uploaded" branch
    # (e.g. after a restart, where the in-memory StabilityTracker forgets
    # it already reported this file and re-surfaces it) rather than relying
    # on the tracker's own no-repeat-reporting behavior to keep it from
    # being touched again.
    config = make_config(delete_after_upload=False)
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)
    worker.startup()
    worker._loop_once()
    worker._loop_once()
    assert client.upload_calls == ["SCN_0001.pdf"]

    # simulate a restart: fresh StabilityTracker, same StateStore/content
    fresh_stability = StabilityTracker(config.stability_checks)
    worker._stability = fresh_stability
    worker._loop_once()
    worker._loop_once()

    assert client.upload_calls == ["SCN_0001.pdf"]  # no second upload
    assert (config.incoming_dir / "SCN_0001.pdf").exists()  # not deleted
    state.close()


def test_local_retention_cleans_up_expired_kept_copy(make_config):
    config = make_config(delete_after_upload=False, local_retention_hours=24.0)
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()
    assert (config.incoming_dir / "SCN_0001.pdf").exists()

    clock.advance(23 * 3600)  # not expired yet
    worker._loop_once()
    assert (config.incoming_dir / "SCN_0001.pdf").exists()

    clock.advance(2 * 3600)  # now past the 24h retention window
    worker._loop_once()
    assert not (config.incoming_dir / "SCN_0001.pdf").exists()
    state.close()


def test_local_retention_unset_keeps_file_forever(make_config):
    config = make_config(delete_after_upload=False, local_retention_hours=None)
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()

    clock.advance(365 * 24 * 3600)
    worker._loop_once()
    assert (config.incoming_dir / "SCN_0001.pdf").exists()
    state.close()


def test_source_file_not_removed_after_failed_upload(make_config):
    config = make_config()
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient(always_fail=SynologyAPIError("boom"))
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()

    assert (config.incoming_dir / "SCN_0001.pdf").exists()
    record = state.get(_sha(b"scan-content"))
    assert record.state == "pending"
    assert record.attempts == 1
    assert record.next_retry_at == clock.now + 5
    state.close()


def test_retry_backoff_sequence_matches_config(make_config):
    config = make_config(retry_backoff_seconds=[5, 15, 30, 60, 300])
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient(always_fail=SynologyAPIError("boom"))
    worker, state, clock = _build_worker(config, client)
    digest = _sha(b"scan-content")

    worker.startup()
    worker._loop_once()
    worker._loop_once()  # attempt 1 fails

    expected_delays = [5, 15, 30, 60, 300, 300, 300]
    for attempt_index, delay in enumerate(expected_delays, start=1):
        record = state.get(digest)
        assert record.attempts == attempt_index
        clock.advance(delay)
        worker._loop_once()

    state.close()


def test_permanent_failure_logged_after_exhausting_backoff(make_config, caplog):
    caplog.set_level(logging.WARNING)
    config = make_config(retry_backoff_seconds=[1, 1])
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"scan-content")
    client = FakeSynologyClient(always_fail=SynologyAPIError("boom"))
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()  # attempt 1
    clock.advance(1)
    worker._loop_once()  # attempt 2
    clock.advance(1)
    worker._loop_once()  # attempt 3 -> exhausts [1, 1], should log ERROR "permanent"

    permanent_logs = [r for r in caplog.records if "permanent upload failure" in r.message]
    assert len(permanent_logs) == 1
    assert permanent_logs[0].levelname == "ERROR"
    state.close()


def test_duplicate_content_is_not_reuploaded(make_config, caplog):
    caplog.set_level(logging.INFO)
    config = make_config()
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(b"same-bytes")
    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()
    assert client.upload_calls == ["SCN_0001.pdf"]

    (config.incoming_dir / "SCN_0002.pdf").write_bytes(b"same-bytes")
    worker._loop_once()
    worker._loop_once()

    assert client.upload_calls == ["SCN_0001.pdf"]  # no second upload
    assert not (config.incoming_dir / "SCN_0002.pdf").exists()
    assert any("duplicate content detected" in r.message for r in caplog.records)
    state.close()


def test_crash_recovery_does_not_reupload_when_remote_already_succeeded(make_config):
    config = make_config()
    content = b"scan-content"
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(content)
    digest = _sha(content)

    state = StateStore(config.state_db_path)
    state.upsert_pending(digest, "SCN_0001.pdf", len(content), now=900.0)
    state.mark_uploading(digest, now=901.0)
    state.close()

    client = FakeSynologyClient(remote_files=[{"name": "SCN_0001.pdf", "size": len(content), "file_id": "remote-1"}])
    worker, state, clock = _build_worker(config, client)

    worker.startup()  # runs _reconcile_in_flight

    record = state.get(digest)
    assert record.state == "uploaded"
    assert client.upload_calls == []
    state.close()


def test_crash_recovery_reuploads_when_remote_missing_file(make_config):
    config = make_config()
    content = b"scan-content"
    (config.incoming_dir / "SCN_0001.pdf").write_bytes(content)
    digest = _sha(content)

    state = StateStore(config.state_db_path)
    state.upsert_pending(digest, "SCN_0001.pdf", len(content), now=900.0)
    state.mark_uploading(digest, now=901.0)
    state.close()

    client = FakeSynologyClient(remote_files=[])
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    record = state.get(digest)
    assert record.state == "pending"
    assert record.next_retry_at <= clock.now

    worker._loop_once()

    assert client.upload_calls == ["SCN_0001.pdf"]
    assert state.get(digest).state == "uploaded"
    state.close()


def test_broken_file_does_not_crash_worker_loop(make_config, monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    config = make_config()
    (config.incoming_dir / "good.pdf").write_bytes(b"good-content")
    (config.incoming_dir / "bad.pdf").write_bytes(b"bad-content")

    import scanner_drive_bridge.worker as worker_module
    real_hash_file = worker_module.hash_file

    def flaky_hash_file(path):
        if path.name == "bad.pdf":
            raise OSError("simulated unreadable file")
        return real_hash_file(path)

    monkeypatch.setattr(worker_module, "hash_file", flaky_hash_file)

    client = FakeSynologyClient()
    worker, state, clock = _build_worker(config, client)

    worker.startup()
    worker._loop_once()
    worker._loop_once()

    assert client.upload_calls == ["good.pdf"]
    assert not (config.incoming_dir / "good.pdf").exists()
    assert (config.incoming_dir / "bad.pdf").exists()  # never lost, just skipped
    assert any("could not read file for hashing" in r.message for r in caplog.records)
    state.close()


def test_destination_not_found_logs_warning_but_does_not_crash(make_config, caplog):
    caplog.set_level(logging.WARNING)
    config = make_config()
    client = FakeSynologyClient(team_folders=[{"name": "some-other-folder"}])
    worker, state, clock = _build_worker(config, client)

    worker.startup()

    assert any("was not found" in r.message for r in caplog.records)
    state.close()
