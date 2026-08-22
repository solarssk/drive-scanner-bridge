import logging
from io import BytesIO

import requests

from scanner_drive_bridge.synology import SynologyAPIError, SynologyDriveClient, _extract_items


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None, verify=None):
        self.calls.append(
            {"method": "GET", "url": url, "params": params, "timeout": timeout, "verify": verify}
        )
        return self._next()

    def post(self, url, params=None, data=None, files=None, timeout=None, verify=None):
        self.calls.append(
            {
                "method": "POST", "url": url, "params": params, "data": data, "files": files,
                "timeout": timeout, "verify": verify,
            }
        )
        return self._next()

    def _next(self):
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item() if callable(item) else item


def _discovery_response(versions=None):
    versions = versions or {
        "SYNO.API.Auth": 6,
        "SYNO.SynologyDrive.Files": 2,
        "SYNO.SynologyDrive.TeamFolders": 1,
    }
    data = {name: {"maxVersion": v, "minVersion": 1} for name, v in versions.items()}
    return FakeResponse({"success": True, "data": data})


def _login_response(sid="sid-123"):
    return FakeResponse({"success": True, "data": {"sid": sid}})


def _error_response(code=400):
    return FakeResponse({"success": False, "error": {"code": code}})


def make_client(responses, **kwargs):
    session = FakeSession(responses)
    client = SynologyDriveClient(
        host="https://192.0.2.10:5001",
        username="prt01",
        password="super-secret-pw",
        session=session,
        **kwargs,
    )
    return client, session


def test_login_success_sets_sid_and_discovers_versions():
    client, session = make_client([_discovery_response(), _login_response("sid-abc")])

    client.login()

    assert client.authenticated is True
    discovery_call = session.calls[0]
    assert discovery_call["params"]["api"] == "SYNO.API.Info"
    assert discovery_call["params"]["query"] == (
        "SYNO.API.Auth,SYNO.SynologyDrive.Files,SYNO.SynologyDrive.TeamFolders"
    )
    login_call = session.calls[1]
    assert login_call["method"] == "POST"
    assert login_call["params"]["api"] == "SYNO.API.Auth"
    # credentials must travel in the POST body, never the query string
    assert "account" not in login_call["params"]
    assert "passwd" not in login_call["params"]
    assert login_call["data"]["account"] == "prt01"
    assert login_call["data"]["passwd"] == "super-secret-pw"


def test_login_uses_discovered_api_version_instead_of_hardcoded_default():
    client, session = make_client(
        [_discovery_response({
            "SYNO.API.Auth": 7,
            "SYNO.SynologyDrive.Files": 2,
            "SYNO.SynologyDrive.TeamFolders": 1,
        }), _login_response()]
    )

    client.login()

    assert session.calls[1]["params"]["version"] == 7


def test_login_failure_raises_with_error_code():
    client, session = make_client([_discovery_response(), _error_response(code=400)])

    try:
        client.login()
        assert False, "expected SynologyAPIError"
    except SynologyAPIError as exc:
        assert exc.code == 400


def test_verify_tls_true_by_default():
    client, session = make_client([_discovery_response(), _login_response()])
    client.login()
    assert session.calls[0]["verify"] is True


def test_verify_tls_false_logs_warning(caplog):
    caplog.set_level(logging.WARNING)
    make_client([], verify=False)
    assert any("DISABLED" in record.message for record in caplog.records)


def test_ca_file_used_as_verify_argument():
    client, session = make_client([_discovery_response(), _login_response()], ca_file="/run/secrets/synology_ca")
    client.login()
    assert session.calls[0]["verify"] == "/run/secrets/synology_ca"


def test_upload_file_success_returns_data():
    client, session = make_client(
        [
            _discovery_response(),
            _login_response(),
            FakeResponse({"success": True, "data": {"name": "SCN_0001.pdf", "file_id": "abc"}}),
        ]
    )

    result = client.upload_file(
        BytesIO(b"scan-bytes"), "SCN_0001.pdf", "/team-folders/printer", "autorename"
    )

    assert result == {"name": "SCN_0001.pdf", "file_id": "abc"}
    upload_call = session.calls[-1]
    assert upload_call["method"] == "POST"
    assert upload_call["data"]["path"] == "/team-folders/printer/SCN_0001.pdf"
    assert upload_call["data"]["type"] == "file"
    assert upload_call["data"]["conflict_action"] == "autorename"
    assert upload_call["files"]["file"][0] == "SCN_0001.pdf"


def test_upload_file_failure_raises():
    client, session = make_client(
        [_discovery_response(), _login_response(), _error_response(code=119)]
    )

    try:
        client.upload_file(BytesIO(b"x"), "a.pdf", "/team-folders/printer")
        assert False, "expected SynologyAPIError"
    except SynologyAPIError:
        pass

    # an auth-related error code must invalidate the cached session id
    assert client.authenticated is False


def test_delete_path_looks_up_file_id_then_deletes():
    client, session = make_client(
        [
            _discovery_response(),
            _login_response(),
            FakeResponse({"success": True, "data": {"items": [{"name": "test.txt", "file_id": "999"}]}}),
            FakeResponse({"success": True, "data": {}}),
        ]
    )

    client.delete_path("/team-folders/printer/test.txt")

    delete_call = session.calls[-1]
    assert delete_call["data"]["files"] == '["999"]'


def test_delete_path_raises_when_not_found():
    client, session = make_client(
        [
            _discovery_response(),
            _login_response(),
            FakeResponse({"success": True, "data": {"items": []}}),
        ]
    )

    try:
        client.delete_path("/team-folders/printer/missing.txt")
        assert False, "expected SynologyAPIError"
    except SynologyAPIError:
        pass


def test_password_never_appears_in_logs(caplog):
    caplog.set_level(logging.DEBUG)
    client, session = make_client(
        [
            _discovery_response(),
            _login_response(),
            FakeResponse({"success": True, "data": {"name": "a.pdf", "file_id": "1"}}),
        ]
    )

    client.upload_file(BytesIO(b"x"), "a.pdf", "/team-folders/printer")

    for record in caplog.records:
        assert "super-secret-pw" not in record.getMessage()


def test_network_error_message_never_leaks_password_from_url():
    # Regression test: a live smoke test against an unreachable host showed
    # that requests/urllib3 connection errors embed the full request URL
    # (including query string) in their message. This must never reach a
    # SynologyAPIError's text, since worker.py logs that text verbatim.
    leaking_exc = requests.exceptions.ConnectTimeout(
        "HTTPSConnectionPool(host='192.0.2.1', port=5001): Max retries exceeded with url: "
        "/webapi/auth.cgi?api=SYNO.API.Auth&account=prt01&passwd=super-secret-pw&session=x "
        "(Caused by ConnectTimeoutError(...))"
    )
    client, session = make_client([_discovery_response(), leaking_exc])

    try:
        client.login()
        assert False, "expected SynologyAPIError"
    except SynologyAPIError as exc:
        assert "super-secret-pw" not in str(exc)


def test_extract_items_handles_multiple_shapes():
    assert _extract_items({"items": [1, 2]}) == [1, 2]
    assert _extract_items([1, 2]) == [1, 2]
    assert _extract_items({"list": [1]}) == [1]
    assert _extract_items({"unknown": 123}) == []
    assert _extract_items(None) == []
