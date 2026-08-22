from pathlib import Path

from scanner_drive_bridge.scanner import StabilityTracker, _is_readable


def test_file_not_stable_until_checks_satisfied(tmp_path):
    tracker = StabilityTracker(stability_checks=2)
    f = tmp_path / "SCN_0001.pdf"
    f.write_bytes(b"scan-bytes")

    first = tracker.poll(tmp_path)
    assert first == []

    second = tracker.poll(tmp_path)
    assert second == [f]


def test_growing_file_never_reported_stable_while_changing(tmp_path):
    tracker = StabilityTracker(stability_checks=2)
    f = tmp_path / "SCN_0001.pdf"

    f.write_bytes(b"a")
    assert tracker.poll(tmp_path) == []

    f.write_bytes(b"a" * 100)  # still growing: size changes, resets the counter
    assert tracker.poll(tmp_path) == []

    f.write_bytes(b"a" * 500)
    assert tracker.poll(tmp_path) == []

    # size settles at 500 bytes here; the poll above already counted as the
    # first observation of this size, so exactly one more unchanged poll
    # is needed to reach stability_checks=2
    assert tracker.poll(tmp_path) == [f]


def test_stable_file_is_not_reported_twice(tmp_path):
    tracker = StabilityTracker(stability_checks=2)
    f = tmp_path / "SCN_0001.pdf"
    f.write_bytes(b"scan-bytes")

    tracker.poll(tmp_path)
    assert tracker.poll(tmp_path) == [f]

    # file still sitting there untouched (e.g. upload retry pending) - must
    # not be re-reported, or the worker would re-hash/re-queue it forever.
    assert tracker.poll(tmp_path) == []
    assert tracker.poll(tmp_path) == []


def test_forget_allows_rediscovery(tmp_path):
    tracker = StabilityTracker(stability_checks=2)
    f = tmp_path / "SCN_0001.pdf"
    f.write_bytes(b"scan-bytes")

    tracker.poll(tmp_path)
    assert tracker.poll(tmp_path) == [f]

    tracker.forget(f)

    assert tracker.poll(tmp_path) == []
    assert tracker.poll(tmp_path) == [f]


def test_hidden_and_temp_files_are_never_reported(tmp_path):
    tracker = StabilityTracker(stability_checks=1)
    (tmp_path / ".hidden.pdf").write_bytes(b"x")
    (tmp_path / "notes.tmp").write_bytes(b"x")
    (tmp_path / "~lock.pdf").write_bytes(b"x")

    assert tracker.poll(tmp_path) == []
    assert tracker.poll(tmp_path) == []


def test_ordinary_file_reported_with_single_check(tmp_path):
    tracker = StabilityTracker(stability_checks=1)
    f = tmp_path / "SCN_0001.pdf"
    f.write_bytes(b"scan-bytes")

    assert tracker.poll(tmp_path) == [f]


def test_missing_incoming_dir_returns_empty(tmp_path):
    tracker = StabilityTracker(stability_checks=1)
    assert tracker.poll(tmp_path / "does-not-exist") == []


def test_is_readable_false_for_missing_path(tmp_path):
    assert _is_readable(tmp_path / "nope.pdf") is False


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_stability_interval_is_independent_of_poll_frequency(tmp_path):
    # Regression test: STABILITY_INTERVAL_SECONDS must gate how much real
    # time has to pass between checks, not just count every poll() call as
    # one -- otherwise a fast SCAN_INTERVAL_SECONDS silently makes the
    # configured settle margin meaningless (a real incident: a slow/flaky
    # legacy SMB1 transfer got grabbed mid-write because every 2s poll
    # counted as a full stability check regardless of this setting).
    clock = _FakeClock()
    tracker = StabilityTracker(stability_checks=2, stability_interval_seconds=10.0, clock=clock)
    f = tmp_path / "SCN_0001.pdf"
    f.write_bytes(b"scan-bytes")

    assert tracker.poll(tmp_path) == []  # first sighting

    # polling rapidly (as SCAN_INTERVAL_SECONDS would) must NOT advance
    # stability progress before stability_interval_seconds has elapsed
    for _ in range(5):
        clock.advance(1.0)
        assert tracker.poll(tmp_path) == []

    # now enough real time has passed since the last counted check
    clock.advance(10.0)
    assert tracker.poll(tmp_path) == [f]


def test_stability_interval_does_not_delay_detecting_a_change(tmp_path):
    clock = _FakeClock()
    tracker = StabilityTracker(stability_checks=2, stability_interval_seconds=10.0, clock=clock)
    f = tmp_path / "SCN_0001.pdf"
    f.write_bytes(b"a")
    assert tracker.poll(tmp_path) == []

    # even before stability_interval_seconds has elapsed, a genuine size
    # change must be noticed immediately (growing files are never held up
    # by the interval gate, only "looks unchanged" observations are)
    clock.advance(1.0)
    f.write_bytes(b"a" * 100)
    assert tracker.poll(tmp_path) == []

    clock.advance(10.0)
    assert tracker.poll(tmp_path) == [f]
