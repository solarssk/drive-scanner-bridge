# Multi-stage build: the final image is Google's "distroless" Python base,
# which ships no shell, no package manager, and no OS packages beyond the
# Python runtime itself, so it lacks the unused OS packages (perl, coreutils,
# a shell, ...) that a python:3.13-slim image carries and this service never
# touches. CI scans the built image with Trivy (ci.yml, weekly-image-scan.yml,
# release-image.yml); the base is not CVE-free, those scans are the check.
# See docs/security.md.
#
# The builder stage uses python:3.13-slim specifically to match the Python
# 3.13 the distroless image bundles, so any compiled C extensions among our
# dependencies (e.g. charset_normalizer) are ABI-compatible with the
# interpreter that will actually run them.
FROM gcr.io/distroless/python3-debian13:latest@sha256:0e48fa084c225991c3f4e133306cd64fdca9ed028215a2d8a67eb798c857a981 AS distroless-base

FROM python:3.13-slim@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c AS builder

WORKDIR /build

# Runtime dependencies first, from the hash-locked requirements.txt (generated from
# requirements.in with pip-compile), so every build installs byte-identical packages
# and a source change does not re-resolve them. --target installs flatly into /deps,
# which is copied wholesale into the distroless stage (which has no pip).
COPY requirements.txt ./
RUN pip install --no-cache-dir --target=/deps --require-hashes -r requirements.txt

# Then the package itself, leaving the already-installed dependencies alone.
COPY pyproject.toml ./
COPY scanner_drive_bridge ./scanner_drive_bridge
RUN pip install --no-cache-dir --target=/deps --no-deps .

# distroless only defines root/nobody/nonroot. Append an entry for
# 1048:100 -- chosen to match the DSM user `prt01` and the smb1-printer
# container's USERID/GROUPID, so files Samba writes into the shared
# `scanner_incoming` volume are readable/removable by this container
# without chmod tricks -- onto its actual passwd/group files (rather than
# this stage's own, much larger Debian ones).
COPY --from=distroless-base /etc/passwd /etc/group /etc/
RUN echo 'bridge:x:100:' >> /etc/group \
 && echo 'bridge:x:1048:100:bridge:/nonexistent:/sbin/nologin' >> /etc/passwd \
 && mkdir -p /incoming /data \
 && chown -R 1048:100 /incoming /data

FROM gcr.io/distroless/python3-debian13:latest@sha256:0e48fa084c225991c3f4e133306cd64fdca9ed028215a2d8a67eb798c857a981

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/deps

COPY --from=builder /etc/passwd /etc/passwd
COPY --from=builder /etc/group /etc/group
COPY --from=builder /deps /deps
# --chown is required here: `COPY --from` does NOT preserve the source
# stage's file ownership on its own, it defaults to root. Without this,
# a fresh named volume (e.g. docker-compose's `uploader_state`/
# `scanner_incoming`) gets populated from image content owned by root,
# which the non-root 1048:100 user then can't write to at all.
COPY --from=builder --chown=1048:100 /incoming /incoming
COPY --from=builder --chown=1048:100 /data /data

USER 1048:100

VOLUME ["/incoming", "/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python3", "-m", "scanner_drive_bridge.main", "healthcheck"]

ENTRYPOINT ["python3", "-m", "scanner_drive_bridge.main"]
