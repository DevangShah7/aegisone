# Threat Model

> **AegisOne** — Developed by Devang Shah.

This document is a STRIDE-style threat model for the AegisOne platform. It is a living document and updated whenever a new capability is added.

## Scope

The threat model covers:

- The AegisOne backend (FastAPI service, Postgres, Redis, MinIO).
- The AegisOne dashboard (Next.js, deployed on Vercel).
- The AegisOne Android agent (Kotlin / Compose, distributed via the Play Store or sideload).
- The on-the-wire protocols between these components.

Out of scope:

- The device owner's own practices (e.g., weak passwords, shared credentials).
- The TLS / CDN / hosting provider's own security model.
- The Android operating system itself.
- Third-party apps installed on enrolled devices.

## Trust boundaries

```
            +---------------------------+
            | AegisOne platform        |
            |                           |
   Owner/   |  +---------+   +-------+  |   Backend
   Operator |  | Browser |<->| Aegis |  |   operator
     ---    |  +---------+   | One   |  |   ---
     Trust  |                | Back- |  |   Trust
     boundary                | end   |  |   boundary
            |  +---------+   |       |  |
            |  | Android |   |       |  |
            |  |  agent  |<->|       |  |
            |  +---------+   +-------+  |
            +---------------------------+
```

## Assets

| Asset | Where it lives | Sensitivity |
|---|---|---|
| Account credentials | Backend Postgres | High |
| Refresh tokens | Backend Postgres (hashed) | High |
| Access tokens | Browser / Android Keystore | High |
| Device credentials | Android Keystore | High |
| Device location | Backend Postgres | High |
| Camera / mic / screen media | MinIO, with audit trail | High |
| Audit log | Backend Postgres | Medium (must be tamper-evident) |
| Backups | MinIO | High |
| Reports | MinIO / browser download | High |
| Consent records | Backend Postgres | Medium |

## Threats (STRIDE)

### Spoofing

| Threat | Mitigation |
|---|---|
| Attacker forges a request as a user | TLS + JWT signatures + opaque refresh-token hash + argon2id passwords |
| Attacker forges a request as a device | Device credentials generated in Android Keystore; bound to device hardware |
| DNS spoofing | TLS + HSTS + DNSSEC at the registrar |
| AI-supplied host header manipulated | Strict CORS allowlist; trusted-proxy list for `X-Forwarded-*` |

### Tampering

| Threat | Mitigation |
|---|---|
| Attacker modifies audit log entries | Audit log rows are append-only; future plan is signed hash chain |
| Attacker modifies a refresh token | Refresh tokens are opaque random strings; row hash is checked on every use |
| Attacker modifies a backup | Backups are content-addressed; checksum stored |
| Attacker tampers with a MinIO object | S3-compatible object locking + lifecycle policy |

### Repudiation

| Threat | Mitigation |
|---|---|
| User denies taking a sensitive action | Every auth event + device action writes an audit row with `user_id`, `device_id`, `ip`, `user_agent`, `metadata` |
| Device denies receiving a command | Every command carries an `id`, `exp`, `idempotency_key`; ack is recorded |

### Information disclosure

| Threat | Mitigation |
|---|---|
| Refresh token leaks via XSS | httpOnly Secure SameSite=Lax cookie; access token in memory only |
| Backup media leaks | MinIO private bucket; signed URLs max 15 min |
| Audit log leak contains sensitive data | Audit fields are metadata only; no message contents, no keystrokes, no call recordings |
| Error pages leak stack traces | Custom error handlers; structured logs include stack trace but never the response body |
| Side-channel timing leaks on login | Constant-time response shape and timing whether user exists or not |

### Denial of service

| Threat | Mitigation |
|---|---|
| Login brute force | Redis sliding window on `auth/login` (5/min/IP and 10/min/email) + account lockout |
| Token replay | Refresh token rotation; access tokens short-lived |
| Backend CPU exhaustion via large requests | Request body size cap (FastAPI middleware) |
| MinIO storage exhaustion | Per-account and per-device quotas |
| WebSocket fan-out CPU stall | In-memory pub/sub today; Redis pub/sub when we scale beyond one instance |

### Elevation of privilege

| Threat | Mitigation |
|---|---|
| Refresh-token replay across chains | Chain revocation on reuse |
| RBAC bypass | All endpoints have role checks; tests pin them |
| Cross-tenant data exposure | Application-layer authorization today; row-level security in Milestone 5 |
| Android `WRITE_SETTINGS` abuse | Not requested; not in the manifest |
| Accessibility-service abuse | Not requested; not in the manifest |
| Device-admin or profile-owner abuse | Not requested; not in the manifest |

## Out-of-band threats (we do not defend against)

- **Compromise of the device owner's credentials.** Use a password manager; enable MFA (planned Milestone 2).
- **Rooted / Magisk-hide devices.** We document this in the consent flow ("rooted devices may bypass system indicators") and ship rooted-detection as a *report* in the security policy view. We do not attempt to enforce.
- **Compromise of the platform's standard TLS / OAuth boundaries.** Out of scope.

## Adversarial review

Before each milestone, the threat model is reviewed against the new capabilities. Changes are tracked in [`adr/`](adr/).
