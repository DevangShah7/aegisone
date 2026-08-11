# Security Policy

## Supported versions

| Component | Supported |
|---|---|
| `backend` (latest minor) | ✅ |
| `dashboard` (latest minor) | ✅ |
| `android-agent` (latest minor) | ✅ |

Older minors receive security fixes only at the maintainer's discretion.

## Threat model

AegisOne is a **device-management platform installed on devices the owner has authorized**. The threat model assumes:

- **Trusted:** the device owner who enrolled the device, the operator who manages it through the Control Center, the backend operator, and the TLS / OAuth boundaries in front of those surfaces.
- **Untrusted:** network traffic, the Android platform on which the agent runs (including rooted devices), and any third-party software installed on enrolled devices.

AegisOne does **not** defend against:

- Covert surveillance — the system is designed to make surveillance visible (camera/mic indicators, MediaProjection banner, audit log).
- Malware already running with elevated privileges on the device (root, Magisk-hide, accessibility abuse).
- Compromise of the device owner's credentials — strong authentication, MFA, and revocation are the owner's responsibility.

For the full threat model, see [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Reporting a vulnerability

**Please do not file public GitHub issues for security-sensitive reports.**

Email security reports to the address in the repository's `SECURITY.md` contact section (TBD by the maintainer) with the subject `AegisOne security report`. Include:

- A description of the issue and the impact.
- Reproduction steps.
- The version / commit SHA affected.
- Your name and a contact method if you'd like credit.

We aim to acknowledge new reports within 3 business days and to coordinate disclosure on a 90-day timeline (or sooner if a fix is ready).

## Security baseline (enforced in code)

The following protections are mandatory in the codebase and reviewed on every pull request:

- TLS is terminated at the reverse proxy; the backend refuses to boot in `prod` without `X-Forwarded-Proto=https`.
- Passwords are hashed with argon2id (`m=64MB, t=3, p=1`).
- JWT access tokens (15 min) + opaque refresh tokens (30 days, rotated on every refresh, with chain revocation).
- Refresh-token reuse revokes the entire session chain.
- Account-enumeration defenses on login, registration, and password reset.
- Redis sliding-window rate limit on auth endpoints.
- Strict CORS allowlist; never `*` with credentials.
- Security response headers on every response: HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy.
- Pydantic input validation on every endpoint; `extra='forbid'` on auth endpoints.
- Audit log written for every auth event and every sensitive device operation.
- Secrets are never logged and never committed; `.env` files are git-ignored.
- The Android agent stores the device credential in the Android Keystore.

## Out of scope

- Bypassing Android platform restrictions (root, accessibility abuse, Magisk hide, etc.). These are explicitly forbidden by the project's non-covert-surveillance model.
- Pen-testing against devices you do not own. AegisOne is for owners and authorized operators only.
