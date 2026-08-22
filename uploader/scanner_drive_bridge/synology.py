"""Minimal direct client for the Synology Drive API.

We intentionally do not depend on the `synology-drive-api` PyPI package:
as of this writing it has had no commits since December 2023, it silently
forces `verify=False` for any HTTPS host addressed by an IP literal (which
is exactly how this NAS is reached), and it pulls in an unrelated hard
dependency on Selenium for a spreadsheet-conversion feature this service
never uses. This module re-implements only the handful of calls the bridge
needs, directly on top of `requests`, with TLS verification always
explicit and API versions discovered from the NAS itself (via
SYNO.API.Info) instead of hardcoded -- which also hedges against
version-mismatch errors like the wrapper's open, unresolved "error_code
103 at login" issue.
"""
from __future__ import annotations

import logging
import re
from typing import Any, BinaryIO, Optional

import requests

logger = logging.getLogger(__name__)

_AUTH_SESSION_NAME = "SynologyDrive"
_AUTH_ERROR_CODES = {105, 106, 107, 119}
_DEFAULT_API_VERSIONS = {
    "SYNO.API.Auth": 6,
    "SYNO.SynologyDrive.Files": 2,
    "SYNO.SynologyDrive.TeamFolders": 1,
}


class SynologyAPIError(Exception):
    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


def _extract_items(data: Any) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "list", "folders", "files"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _shape_of(data: Any) -> Any:
    if isinstance(data, dict):
        return list(data.keys())
    return type(data).__name__


def _redact(text: str) -> str:
    """Strip query strings from any URL-shaped substring in `text`.

    `requests`/`urllib3` exceptions (connection errors, timeouts) embed the
    full request URL -- including query parameters -- in their message. We
    only ever put non-secret values (api/version/method/path) in the query
    string (see `login`, which deliberately sends credentials via the POST
    body instead), but this is kept as defense in depth so a future call
    can never leak a secret into logs through an exception message.
    """
    return re.sub(r"\?\S*", "?<redacted>", text)


class SynologyDriveClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        verify: bool = True,
        ca_file: Optional[str] = None,
        otp_code: Optional[str] = None,
        timeout: float = 30.0,
        session: Optional[Any] = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._otp_code = otp_code
        self._timeout = timeout
        self._session = session if session is not None else requests.Session()
        self._sid: Optional[str] = None
        self._api_versions: dict[str, int] = {}

        if ca_file:
            self._verify: Any = ca_file
        else:
            self._verify = verify
            if not verify:
                logger.warning("TLS certificate verification is DISABLED for Synology API requests")

    @property
    def authenticated(self) -> bool:
        return self._sid is not None

    def _version_for(self, api: str) -> int:
        return self._api_versions.get(api, _DEFAULT_API_VERSIONS[api])

    def _call(
        self,
        http_method: str,
        cgi: str,
        api: str,
        version: int,
        method: str,
        *,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        files: Optional[dict] = None,
        auth_required: bool = True,
    ) -> Any:
        if auth_required and self._sid is None:
            self.login()

        query: dict = {"api": api, "version": version, "method": method}
        if params:
            query.update(params)
        if self._sid is not None:
            query["_sid"] = self._sid

        url = f"{self._host}/webapi/{cgi}"
        try:
            if http_method == "GET":
                resp = self._session.get(url, params=query, timeout=self._timeout, verify=self._verify)
            else:
                resp = self._session.post(
                    url, params=query, data=data, files=files, timeout=self._timeout, verify=self._verify
                )
        except requests.RequestException as exc:
            raise SynologyAPIError(f"network error calling {api}.{method}: {_redact(str(exc))}") from exc

        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise SynologyAPIError(f"HTTP {resp.status_code} calling {api}.{method}") from exc

        try:
            payload = resp.json()
        except ValueError as exc:
            raise SynologyAPIError(f"non-JSON response calling {api}.{method}") from exc

        if not payload.get("success"):
            error = payload.get("error") or {}
            code = error.get("code")
            if code in _AUTH_ERROR_CODES:
                self._sid = None
            raise SynologyAPIError(f"{api}.{method} failed with error code {code}", code=code)

        return payload.get("data")

    def discover_api_versions(self) -> None:
        try:
            data = self._call(
                "GET", "query.cgi", "SYNO.API.Info", 1, "query",
                params={"query": ",".join(_DEFAULT_API_VERSIONS)},
                auth_required=False,
            )
        except SynologyAPIError as exc:
            logger.warning("could not discover Synology API versions, using defaults: %s", exc)
            return
        if not isinstance(data, dict):
            return
        for api_name in _DEFAULT_API_VERSIONS:
            info = data.get(api_name)
            if isinstance(info, dict) and "maxVersion" in info:
                self._api_versions[api_name] = int(info["maxVersion"])
        logger.info("discovered Synology API versions: %s", self._api_versions)

    def login(self) -> None:
        if not self._api_versions:
            self.discover_api_versions()

        # Credentials go in the POST body, never the query string: the
        # query string ends up in `requests`/urllib3 connection-error
        # messages (and in DSM's own access logs) verbatim.
        secret_fields = {
            "account": self._username,
            "passwd": self._password,
            "session": _AUTH_SESSION_NAME,
            "format": "sid",
        }
        if self._otp_code:
            secret_fields["otp_code"] = self._otp_code

        data = self._call(
            "POST", "auth.cgi", "SYNO.API.Auth", self._version_for("SYNO.API.Auth"), "login",
            data=secret_fields, auth_required=False,
        )
        self._sid = data["sid"]
        logger.info("authenticated to Synology DSM as %s", self._username)

    def logout(self) -> None:
        if self._sid is None:
            return
        try:
            self._call(
                "GET", "auth.cgi", "SYNO.API.Auth", self._version_for("SYNO.API.Auth"), "logout",
                params={"session": _AUTH_SESSION_NAME}, auth_required=False,
            )
        except SynologyAPIError as exc:
            logger.warning("logout call failed, ignoring: %s", exc)
        finally:
            self._sid = None

    def list_team_folders(self) -> list[dict]:
        data = self._call(
            "GET", "entry.cgi", "SYNO.SynologyDrive.TeamFolders",
            self._version_for("SYNO.SynologyDrive.TeamFolders"), "list",
        )
        items = _extract_items(data)
        if not items and data:
            logger.debug("unexpected TeamFolders.list response shape: keys=%s", _shape_of(data))
        return items

    def list_folder(self, path: str) -> list[dict]:
        data = self._call(
            "GET", "entry.cgi", "SYNO.SynologyDrive.Files",
            self._version_for("SYNO.SynologyDrive.Files"), "list",
            params={"path": path, "offset": 0, "limit": 1000},
        )
        items = _extract_items(data)
        if not items and data:
            logger.debug("unexpected Files.list response shape: keys=%s", _shape_of(data))
        return items

    def upload_file(
        self,
        fileobj: BinaryIO,
        filename: str,
        dest_folder_path: str,
        conflict_action: str = "autorename",
    ) -> dict:
        # Confirmed against a real DSM 7.4.1 / Drive Server 4.0.3 (API
        # version 11): `upload` wants the full destination file path in
        # `path` (folder + filename, not just the folder) plus a `type`
        # discriminator -- not `dest_folder_path` alone, which is what the
        # reference library's older API version used and which this
        # version rejects with error code 120 ("path": "required"), then
        # 114 ("path and type are both required") once `path` alone was
        # supplied as just the folder.
        full_path = f"{dest_folder_path.rstrip('/')}/{filename}"
        data = self._call(
            "POST", "entry.cgi", "SYNO.SynologyDrive.Files",
            self._version_for("SYNO.SynologyDrive.Files"), "upload",
            data={"path": full_path, "type": "file", "conflict_action": conflict_action},
            files={"file": (filename, fileobj)},
        )
        return data if isinstance(data, dict) else {}

    def delete_path(self, path: str) -> None:
        parent, _, name = path.rpartition("/")
        parent = parent or "/"
        items = self.list_folder(parent)
        match = next((item for item in items if item.get("name") == name), None)
        if match is None or "file_id" not in match:
            raise SynologyAPIError(f"could not find file_id for {path!r} to delete it")
        self._call(
            "POST", "entry.cgi", "SYNO.SynologyDrive.Files",
            self._version_for("SYNO.SynologyDrive.Files"), "delete",
            data={"files": f'["{match["file_id"]}"]', "permanent": "true"},
        )
