"""Environment-variable configuration, with Docker-secret file support.

Any secret value can be provided either directly as `<NAME>` or as a path
via `<NAME>_FILE` (the latter takes precedence). This is what lets
docker-compose mount `/run/secrets/synology_password` without the password
ever being a literal environment variable value.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_RETRY_BACKOFF = [5, 15, 30, 60, 300]


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _read_secret(name: str) -> Optional[str]:
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        try:
            return Path(file_path).read_text(encoding="utf-8").strip()
        except OSError:
            # Fall back to a plain env var rather than failing outright:
            # useful when the secrets bind mount was skipped entirely
            # (e.g. ad-hoc testing), while the default compose file still
            # always sets `{NAME}_FILE` to a fixed path.
            logger.warning(
                "%s_FILE=%s does not exist, falling back to plain %s if set",
                name, file_path, name,
            )
    value = os.environ.get(name)
    return value.strip() if value else None


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got: {raw!r}") from exc


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got: {raw!r}") from exc


def _get_optional_float(name: str) -> Optional[float]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got: {raw!r}") from exc


def _get_seconds_list(name: str, default: list[int]) -> list[int]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    try:
        values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise ConfigError(f"{name} must be a comma-separated list of integers, got: {raw!r}") from exc
    if not values:
        raise ConfigError(f"{name} must contain at least one value")
    return values


@dataclass(frozen=True)
class Config:
    synology_host: str
    synology_username: str
    synology_password: str
    synology_destination: str
    synology_verify_tls: bool
    synology_ca_file: Optional[str]
    synology_otp_code: Optional[str]
    conflict_action: str

    incoming_dir: Path
    state_db_path: Path
    heartbeat_path: Path

    scan_interval_seconds: float
    stability_interval_seconds: float
    stability_checks: int

    retry_backoff_seconds: list[int] = field(default_factory=lambda: list(_DEFAULT_RETRY_BACKOFF))
    # Default matches the original design: /incoming is a temporary staging
    # area, cleared once a file is confirmed uploaded. Set to false if the
    # scanner itself needs to see its own past output still sitting in
    # /incoming to number its next scan correctly (some scanners infer the
    # next filename by listing the destination folder) -- our own dedup-by-
    # content-hash ledger still guarantees a kept file is never re-uploaded.
    delete_after_upload: bool = True
    # Only relevant when delete_after_upload is False: how long a kept
    # local copy is allowed to sit in /incoming after confirmed upload
    # before the worker cleans it up on its own. None (default) means keep
    # forever. Lets the scanner see recent history (for filename numbering)
    # without /incoming growing without bound.
    local_retention_hours: Optional[float] = None
    # Prefixes the name sent to Synology Drive (not the local /incoming
    # filename, which must stay untouched -- see delete_after_upload) with
    # today's date as YYYY-MM-DD, e.g. SCN_0001.pdf -> 2026-08-22_SCN_0001.pdf.
    # Purely cosmetic/organizational for browsing the Team Folder.
    timestamp_upload_filename: bool = False
    http_timeout_seconds: float = 30.0
    healthcheck_max_loop_age_seconds: float = 120.0
    healthcheck_max_backlog_age_seconds: float = 21600.0
    log_level: str = "INFO"

    def __repr__(self) -> str:  # never leak secrets into logs or tracebacks
        redacted_otp = "<redacted>" if self.synology_otp_code else None
        return (
            "Config("
            f"synology_host={self.synology_host!r}, "
            f"synology_username={self.synology_username!r}, "
            "synology_password=<redacted>, "
            f"synology_destination={self.synology_destination!r}, "
            f"synology_verify_tls={self.synology_verify_tls!r}, "
            f"synology_ca_file={self.synology_ca_file!r}, "
            f"synology_otp_code={redacted_otp!r}, "
            f"conflict_action={self.conflict_action!r}, "
            f"incoming_dir={self.incoming_dir!r}, "
            f"state_db_path={self.state_db_path!r}, "
            f"scan_interval_seconds={self.scan_interval_seconds!r}, "
            f"stability_interval_seconds={self.stability_interval_seconds!r}, "
            f"stability_checks={self.stability_checks!r}, "
            f"retry_backoff_seconds={self.retry_backoff_seconds!r})"
        )

    @classmethod
    def from_env(cls) -> "Config":
        host = (os.environ.get("SYNOLOGY_HOST") or "").strip()
        username = (os.environ.get("SYNOLOGY_USERNAME") or "").strip()
        password = _read_secret("SYNOLOGY_PASSWORD")
        destination = (os.environ.get("SYNOLOGY_DESTINATION") or "/team-folders/printer").strip()

        missing = []
        if not host:
            missing.append("SYNOLOGY_HOST")
        if not username:
            missing.append("SYNOLOGY_USERNAME")
        if not password:
            missing.append("SYNOLOGY_PASSWORD (or SYNOLOGY_PASSWORD_FILE)")
        if not destination:
            missing.append("SYNOLOGY_DESTINATION")
        if missing:
            raise ConfigError(f"missing required configuration: {', '.join(missing)}")

        ca_file = (os.environ.get("SYNOLOGY_CA_FILE") or "").strip() or None
        if ca_file and not Path(ca_file).is_file():
            logger.warning("SYNOLOGY_CA_FILE=%s does not exist, ignoring it", ca_file)
            ca_file = None

        return cls(
            synology_host=host.rstrip("/"),
            synology_username=username,
            synology_password=password,  # type: ignore[arg-type]
            synology_destination=destination,
            synology_verify_tls=_get_bool("SYNOLOGY_VERIFY_TLS", True),
            synology_ca_file=ca_file,
            synology_otp_code=_read_secret("SYNOLOGY_OTP_CODE"),
            conflict_action=(os.environ.get("CONFLICT_ACTION") or "autorename").strip(),
            incoming_dir=Path(os.environ.get("INCOMING_DIR", "/incoming")),
            state_db_path=Path(os.environ.get("STATE_DB_PATH", "/data/state.db")),
            heartbeat_path=Path(os.environ.get("HEARTBEAT_PATH", "/data/heartbeat.json")),
            scan_interval_seconds=_get_float("SCAN_INTERVAL_SECONDS", 2.0),
            stability_interval_seconds=_get_float("STABILITY_INTERVAL_SECONDS", 2.0),
            stability_checks=_get_int("STABILITY_CHECKS", 2),
            retry_backoff_seconds=_get_seconds_list("RETRY_BACKOFF_SECONDS", _DEFAULT_RETRY_BACKOFF),
            delete_after_upload=_get_bool("DELETE_AFTER_UPLOAD", True),
            local_retention_hours=_get_optional_float("LOCAL_RETENTION_HOURS"),
            timestamp_upload_filename=_get_bool("TIMESTAMP_UPLOAD_FILENAME", False),
            http_timeout_seconds=_get_float("HTTP_TIMEOUT_SECONDS", 30.0),
            healthcheck_max_loop_age_seconds=_get_float("HEALTHCHECK_MAX_LOOP_AGE_SECONDS", 120.0),
            healthcheck_max_backlog_age_seconds=_get_float("HEALTHCHECK_MAX_BACKLOG_AGE_SECONDS", 21600.0),
            log_level=(os.environ.get("LOG_LEVEL") or "INFO").strip().upper(),
        )
