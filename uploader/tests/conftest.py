import pytest

from scanner_drive_bridge.config import Config


@pytest.fixture
def make_config(tmp_path):
    def _make(**overrides):
        defaults = dict(
            synology_host="https://nas.example:5001",
            synology_username="prt01",
            synology_password="super-secret-pw",
            synology_destination="/team-folders/printer",
            synology_verify_tls=True,
            synology_ca_file=None,
            synology_otp_code=None,
            conflict_action="autorename",
            incoming_dir=tmp_path / "incoming",
            state_db_path=tmp_path / "state.db",
            heartbeat_path=tmp_path / "heartbeat.json",
            scan_interval_seconds=0.01,
            stability_interval_seconds=0.01,
            stability_checks=2,
            retry_backoff_seconds=[5, 15, 30, 60, 300],
        )
        defaults.update(overrides)
        defaults["incoming_dir"].mkdir(parents=True, exist_ok=True)
        return Config(**defaults)

    return _make
