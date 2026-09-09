# Security Policy

This is a personal-infrastructure project, maintained best-effort. There is
no SLA on response time.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub Security Advisories:

https://github.com/solarssk/drive-scanner-bridge/security/advisories/new

**Do not open a public GitHub issue** for anything touching credential
handling, DSM authentication, or the SMB1/Samba legacy-auth settings
(`smb1-printer`'s `ntlm auth` / `lanman auth` / signing-disabled
configuration). This service authenticates to a real NAS with a real
password -- a public issue is not the place to discuss an auth weakness,
even a suspected one.

For anything else (a bug with no security implication, a documentation
error, a feature request), a regular GitHub issue is fine.

## Scope

Covers this repository: the `drive-uploader` container, its Synology Drive
API client, and the `docker-compose.yml` / Samba (`smb1-printer`)
configuration shipped here. It does not cover DSM, Synology Drive Server,
or Samba themselves -- report those to Synology or the Samba project
directly.
