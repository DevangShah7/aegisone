# Privacy Model

> **AegisOne** — Developed by Devang Shah.

## Scope

AegisOne is a remote device management platform. By its nature it handles sensitive device data — locations, app inventories, network diagnostics, screenshots, and recordings. This document describes what AegisOne collects, why, and how the data subject (the device owner) can control it.

## Data inventory

| Data | Why | Retention | User control |
|---|---|---|---|
| Account email / password hash | Authentication | Until account deletion | Delete account |
| Refresh-token hashes | Session management | 30 days after last use, or until revocation | Logout (any device) / logout all |
| Device properties (model, OS, app version) | Inventory + capability gating | Until device is revoked | Revoke device |
| Device health (battery, storage, RAM) | Diagnostics | 90 days rolling | Disable health reporting |
| Location | Geofencing, locate, audit | 30 days rolling | Disable location collection |
| Application inventory | Permission audit, asset inventory | Until device is revoked | Disable inventory |
| Permissions | Security policy | Until device is revoked | Disable permission reporting |
| Audit log | Compliance, security review | 1 year (configurable) | Request export |
| Files / backups | User-initiated | Until user deletes | Delete backup |
| Screenshots / recordings | User-initiated remote support | Session + 24h | Delete session |
| Consent records | Legal record of explicit consent | Account lifetime | View in Privacy Center |

## Lawful basis

- **Contract performance.** Account creation, authentication, device pairing.
- **Legitimate interest.** Security alerting, diagnostic degradation, threat-response coordination.
- **Explicit consent.** Every sensitive capability (camera, microphone, screen capture, location, contacts, calendar, notifications, SMS, files) requires an in-app consent prompt on the device, with system-level permission on top of that. The device owner can revoke consent at any time.

## Data minimization

- We collect only the data we need for the feature in question.
- We do not collect call recordings, message contents, or keystrokes by default.
- Audit logs are metadata (event type, resource id, result) — not the data that triggered the event.

## Retention

| Class | Retention |
|---|---|
| Audit log | 1 year (default; configurable; per-jurisdiction override) |
| Device health | 90 days rolling |
| Location | 30 days rolling |
| Sessions | 30 days from last use, or until revocation |
| Backups | Until user-initiated deletion |
| Recordings | Session + 24 hours, then auto-deleted |

## Data subject rights

The device owner can:

- **Access** — export all data AegisOne holds about them and their device (JSON / CSV / PDF).
- **Rectify** — update their account email and profile.
- **Erase** — delete the account, the device, the backups, the audit log entries (subject to legal record-keeping requirements).
- **Restrict processing** — disable health reporting, location collection, inventory, etc., without revoking the device.
- **Portability** — same as access; exports in JSON / CSV / PDF.
- **Object** — disconnect a device and revoke all of its credentials.

These are surfaced in the dashboard's Privacy Center (planned Milestone 5).

## Subprocessors

- **Vercel** — dashboard hosting (Milestone 6).
- **Backend hosting provider** — backend and database hosting (TBD; documented in Privacy Center before public release).
- **Postmark / SendGrid / Mailgun** — transactional email (Milestone 2; user choice).
- **Sentry / OpenTelemetry backend** — error tracking and tracing (optional, Milestone 6).

## Children's data

AegisOne is not intended for users under 16. By using AegisOne, the account holder confirms they are authorized to enroll the device.

## Changes to this policy

Material changes will be notified in-product and require re-acceptance of the privacy policy before continued use.
