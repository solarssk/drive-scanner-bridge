# Multi-stage build: the final image is Google's "distroless" Python base,
# which ships no shell, no package manager, and no OS packages beyond the
# Python runtime itself -- a `docker scout cves` scan of it comes back at
# 0 Critical/High/Medium/Low, vs. dozens found in a python:3.12-slim image
# (mostly unused OS packages like perl that this service never touches).
# See README "Security".
#
# The builder stage uses python:3.11-slim specifically to match the Python
# 3.11 the distroless image bundles, so any compiled C extensions among our
# dependencies (e.g. charset_normalizer) are ABI-compatible with the
# interpreter that will actually run them.
FROM gcr.io/distroless/python3-debian12:latest AS distroless-base

FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY scanner_drive_bridge ./scanner_drive_bridge

# --target installs our package and its dependencies flatly into /deps,
# which is copied wholesale into the distroless stage (which has no pip).
RUN pip install --no-cache-dir --target=/deps .

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

FROM gcr.io/distroless/python3-debian12:latest

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
