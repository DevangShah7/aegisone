# 003. No covert operation

- **Status:** Accepted
- **Date:** 2026-08-10

## Context

AegisOne's mission is to be a consent-based remote device management platform. The product's long-term value — its defensibility against anti-virus, its Play Store presence, its legal status — depends on never operating covertly.

## Decision

The platform will never implement:

- Hidden camera activation.
- Hidden microphone recording.
- Covert screen capture outside the MediaProjection consent flow.
- Credential theft or authentication bypass.
- Exploit-based device takeover.
- Hidden installation or stealth persistence.
- Unauthorized device enrollment.
- Covert surveillance of any kind.
- Security-control bypass.

Every sensitive capability uses the platform's official APIs and surfaces a visible system indicator. The developer credit (`Developed by Devang Shah`) and the product name (`AegisOne`) are visible at every user-facing surface.

## Consequences

- Camera / microphone / screen capture are gated on the MediaProjection consent flow with a persistent foreground notification.
- Rooted-device detection is reported, not enforced.
- The Play Store distribution is sideload / F-Droid; commercial distribution is via enterprise track or self-host.
- Marketing copy positions the product as "device management for owners and authorized operators," not "threat intelligence."
