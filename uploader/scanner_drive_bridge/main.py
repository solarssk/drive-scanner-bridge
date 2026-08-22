"""Entrypoint: `python -m scanner_drive_bridge.main [healthcheck]`."""
from __future__ import annotations

import json
import logging
import signal
import sys
import time
from typing import Optional

from .config import Config, ConfigError
from .scanner import StabilityTracker
from .state import StateStore
from .synology import SynologyDriveClient
from .worker import Worker

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _build_worker(config: Config) -> Worker:
    client = SynologyDriveClient(
        host=config.synology_host,
        username=config.synology_username,
        password=config.synology_password,
        verify=config.synology_verify_tls,
        ca_file=config.synology_ca_file,
        otp_code=config.synology_otp_code,
        timeout=config.http_timeout_seconds,
    )
    state = StateStore(config.state_db_path)
    stability = StabilityTracker(config.stability_checks, config.stability_interval_seconds)
    return Worker(config, client, state, stability)


def run_healthcheck(config: Optional[Config] = None) -> int:
    try:
        config = config or Config.from_env()
    except ConfigError as exc:
        print(f"UNHEALTHY: invalid configuration: {exc}")
        return 1

    try:
        payload = json.loads(config.heartbeat_path.read_text())
    except (OSError, ValueError) as exc:
        print(f"UNHEALTHY: could not read heartbeat file: {exc}")
        return 1

    now = time.time()
    loop_age = now - payload.get("last_loop_at", 0)
    if loop_age > config.healthcheck_max_loop_age_seconds:
        print(f"UNHEALTHY: worker loop stale, last_loop_at {loop_age:.0f}s ago")
        return 1

    backlog_age = payload.get("oldest_pending_age_seconds")
    if backlog_age is not None and backlog_age > config.healthcheck_max_backlog_age_seconds:
        print(f"UNHEALTHY: backlog age {backlog_age:.0f}s exceeds threshold")
        return 1

    print("healthy")
    return 0


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if argv and argv[0] == "healthcheck":
        return run_healthcheck()

    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1

    _configure_logging(config.log_level)
    worker = _build_worker(config)

    def _handle_signal(signum, _frame):
        logger.info("received signal %s, shutting down gracefully", signum)
        worker.request_stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    worker.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
