"""Non-destructive connectivity check against a real Synology Drive instance.

Run with:

    docker compose exec drive-uploader python -m scanner_drive_bridge.test_connection

By default this only performs read-only calls (login, list team folders,
list the destination folder). Set SCANNER_BRIDGE_TEST_UPLOAD=true to also
upload a tiny, uniquely-named test file and then delete it again.
"""
from __future__ import annotations

import os
import sys
import time
from io import BytesIO

from .config import Config, ConfigError
from .synology import SynologyAPIError, SynologyDriveClient


def main() -> int:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}")
        return 1

    client = SynologyDriveClient(
        host=config.synology_host,
        username=config.synology_username,
        password=config.synology_password,
        verify=config.synology_verify_tls,
        ca_file=config.synology_ca_file,
        otp_code=config.synology_otp_code,
        timeout=config.http_timeout_seconds,
    )

    try:
        print("1. authenticating...")
        client.login()
        print("   OK")

        print("2. listing team folders...")
        folders = client.list_team_folders()
        names = [f.get("name") for f in folders]
        print(f"   found: {names}")

        target_name = config.synology_destination.rstrip("/").split("/")[-1]
        if target_name not in names:
            print(f"   WARNING: '{target_name}' not found among team folders")

        print(f"3. listing destination folder {config.synology_destination}...")
        items = client.list_folder(config.synology_destination)
        print(f"   OK ({len(items)} entries)")

        if os.environ.get("SCANNER_BRIDGE_TEST_UPLOAD", "false").strip().lower() == "true":
            test_name = f".scanner-drive-bridge-test-{int(time.time())}.txt"
            print(f"4. uploading tiny test file {test_name}...")
            result = client.upload_file(
                BytesIO(b"scanner-drive-bridge connectivity test\n"),
                filename=test_name,
                dest_folder_path=config.synology_destination,
                conflict_action=config.conflict_action,
            )
            uploaded_name = result.get("name", test_name)
            print(f"   OK uploaded_as={uploaded_name} file_id={result.get('file_id')}")

            print("5. deleting test file...")
            try:
                client.delete_path(f"{config.synology_destination}/{uploaded_name}")
                print("   OK")
            except SynologyAPIError as exc:
                print(f"   WARNING: could not delete test file automatically: {exc}")
        else:
            print("4. skipping upload test (set SCANNER_BRIDGE_TEST_UPLOAD=true to enable)")

    except SynologyAPIError as exc:
        print(f"FAILED: {exc}")
        return 1
    finally:
        client.logout()

    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
