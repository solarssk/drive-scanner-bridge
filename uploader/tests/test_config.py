import pytest

from scanner_drive_bridge.config import Config, ConfigError


def _set_required_env(monkeypatch, **overrides):
    values = dict(
        SYNOLOGY_HOST="https://192.0.2.10:5001",
        SYNOLOGY_USERNAME="prt01",
        SYNOLOGY_PASSWORD="super-secret-pw",
        SYNOLOGY_DESTINATION="/team-folders/printer",
    )
    values.update(overrides)
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("SYNOLOGY_HOST", raising=False)
    monkeypatch.delenv("SYNOLOGY_USERNAME", raising=False)
    monkeypatch.delenv("SYNOLOGY_PASSWORD", raising=False)
    monkeypatch.delenv("SYNOLOGY_PASSWORD_FILE", raising=False)

    with pytest.raises(ConfigError) as excinfo:
        Config.from_env()

    assert "SYNOLOGY_HOST" in str(excinfo.value)
    assert "SYNOLOGY_USERNAME" in str(excinfo.value)


def test_password_from_plain_env(monkeypatch):
    _set_required_env(monkeypatch)
    config = Config.from_env()
    assert config.synology_password == "super-secret-pw"


def test_password_from_file_takes_precedence(monkeypatch, tmp_path):
    secret_file = tmp_path / "synology_password"
    secret_file.write_text("password-from-file\n")
    _set_required_env(monkeypatch, SYNOLOGY_PASSWORD="ignored-plain-value")
    monkeypatch.setenv("SYNOLOGY_PASSWORD_FILE", str(secret_file))

    config = Config.from_env()

    assert config.synology_password == "password-from-file"


def test_password_falls_back_to_plain_env_when_file_missing(monkeypatch, tmp_path, caplog):
    missing_file = tmp_path / "does-not-exist"
    _set_required_env(monkeypatch, SYNOLOGY_PASSWORD="plain-fallback-value")
    monkeypatch.setenv("SYNOLOGY_PASSWORD_FILE", str(missing_file))

    config = Config.from_env()

    assert config.synology_password == "plain-fallback-value"
    assert any("falling back to plain" in r.message for r in caplog.records)


def test_defaults_applied(monkeypatch):
    _set_required_env(monkeypatch)
    for key in (
        "STABILITY_INTERVAL_SECONDS", "STABILITY_CHECKS", "SCAN_INTERVAL_SECONDS",
        "SYNOLOGY_VERIFY_TLS", "RETRY_BACKOFF_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    config = Config.from_env()

    assert config.stability_interval_seconds == 2.0
    assert config.stability_checks == 2
    assert config.scan_interval_seconds == 2.0
    assert config.synology_verify_tls is True
    assert config.retry_backoff_seconds == [5, 15, 30, 60, 300]


def test_verify_tls_false(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("SYNOLOGY_VERIFY_TLS", "false")
    config = Config.from_env()
    assert config.synology_verify_tls is False


def test_ca_file_ignored_if_missing(monkeypatch, tmp_path, caplog):
    _set_required_env(monkeypatch)
    missing = tmp_path / "does-not-exist.pem"
    monkeypatch.setenv("SYNOLOGY_CA_FILE", str(missing))

    config = Config.from_env()

    assert config.synology_ca_file is None


def test_retry_backoff_parsing(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("RETRY_BACKOFF_SECONDS", "1, 2,3")
    config = Config.from_env()
    assert config.retry_backoff_seconds == [1, 2, 3]


def test_retry_backoff_invalid_raises(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("RETRY_BACKOFF_SECONDS", "not-a-number")
    with pytest.raises(ConfigError):
        Config.from_env()


def test_repr_does_not_leak_password_or_otp(make_config):
    config = make_config(synology_password="very-secret-value", synology_otp_code="123456")
    text = repr(config)
    assert "very-secret-value" not in text
    assert "123456" not in text
    assert "<redacted>" in text


def test_str_does_not_leak_password(make_config):
    config = make_config(synology_password="very-secret-value")
    assert "very-secret-value" not in str(config)
