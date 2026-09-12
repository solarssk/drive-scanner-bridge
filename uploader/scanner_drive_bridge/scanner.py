"""Polling-based file-stabilization detector.

Deliberately polling, not inotify: the entire reason this service exists is
that this NAS's filesystem-event pipeline (synotifyd -> Synology Drive) is
unreliable, so leaning on any other filesystem-notification mechanism here
would risk the same class of bug.

`stability_interval_seconds` is enforced independently of how often `poll()`
itself is called (i.e. independently of SCAN_INTERVAL_SECONDS): an unchanged
observation only counts as a fresh stability check once at least that many
seconds have passed since the last one that counted. Conflating the two
(treating every poll as a check) makes the effective settle time only as
long as the scan interval, which is nowhere near enough margin for a slow
or flaky legacy SMB1 transfer -- grabbing (and deleting) a file the scanner
still has open for writing doesn't just risk uploading a truncated file, it
can itself cause the scanner's own SMB session to error out.

A path is reported at most once per "stable episode": once returned by
`poll()`, it is not returned again on later polls as long as it remains
unchanged on disk (the caller is expected to have taken ownership of it).
It only becomes eligible to be reported again if its (size, mtime) changes
again afterwards, or if the caller explicitly calls `forget()`.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_IGNORED_SUFFIXES = {".tmp", ".part", ".partial", ".crdownload"}


@dataclass
class _Observation:
    size: int
    mtime: float
    consecutive_matches: int
    last_checked_at: float
    reported: bool = False


def _is_candidate(entry: Path) -> bool:
    if not entry.is_file():
        return False
    if entry.name.startswith((".", "~")):
        return False
    if entry.suffix.lower() in _IGNORED_SUFFIXES:
        return False
    return True


def _is_readable(path: Path) -> bool:
    try:
        with path.open("rb"):
            return True
    except OSError:
        return False


class StabilityTracker:
    def __init__(
        self,
        stability_checks: int,
        stability_interval_seconds: float = 0.0,
        clock: Callable[[], float] = time.time,
    ):
        if stability_checks < 1:
            raise ValueError("stability_checks must be >= 1")
        self._stability_checks = stability_checks
        self._stability_interval_seconds = stability_interval_seconds
        self._clock = clock
        self._observations: dict[Path, _Observation] = {}

    def forget(self, path: Path) -> None:
        """Drop tracking state for `path` so it is treated as newly detected
        next time it is seen. Used when something downstream (hashing,
        upload) discovers the file is not actually usable after all."""
        self._observations.pop(path, None)

    def _next_observation(self, entry: Path, stat: os.stat_result, now: float) -> tuple[_Observation, bool]:
        """Decide whether `entry` should be reported as newly stable given
        its latest stat(), returning (observation_to_keep, should_report)."""
        previous = self._observations.get(entry)
        unchanged = (
            previous is not None
            and previous.size == stat.st_size
            and previous.mtime == stat.st_mtime
        )

        if unchanged and previous.reported:
            return previous, False  # already reported stable and still untouched: nothing to do

        if unchanged and (now - previous.last_checked_at) < self._stability_interval_seconds:
            return previous, False  # too soon since the last check to count as a fresh one

        if unchanged:
            matches = previous.consecutive_matches + 1
        else:
            if previous is None:
                logger.info("detected file %s", entry.name)
            matches = 1

        is_stable = matches >= self._stability_checks and _is_readable(entry)
        if not is_stable:
            logger.info("waiting for file stabilization %s", entry.name)
        return _Observation(stat.st_size, stat.st_mtime, matches, now, reported=is_stable), is_stable

    def poll(self, incoming_dir: Path) -> list[Path]:
        try:
            entries = sorted(incoming_dir.iterdir())
        except FileNotFoundError:
            logger.warning("incoming directory does not exist: %s", incoming_dir)
            return []
        except OSError as exc:
            logger.warning("could not list incoming directory %s: %s", incoming_dir, exc)
            return []

        stable: list[Path] = []
        seen: set[Path] = set()
        now = self._clock()

        for entry in entries:
            if not _is_candidate(entry):
                continue
            seen.add(entry)
            try:
                stat = entry.stat()
            except OSError:
                continue

            observation, is_stable = self._next_observation(entry, stat, now)
            self._observations[entry] = observation
            if is_stable:
                stable.append(entry)

        # Snapshot the keys to drop into their own list before popping --
        # self._observations is mutated inside this loop, so iterating the
        # dict itself here (even via a comprehension) would raise
        # "dictionary changed size during iteration".
        stale = [tracked for tracked in self._observations if tracked not in seen]
        for tracked in stale:
            self._observations.pop(tracked, None)

        return stable
