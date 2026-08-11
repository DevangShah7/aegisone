# AegisOne Documentation

> **AegisOne** — Secure Remote Device Management for device owners and authorized operators.
>
> **Developed by Devang Shah.**

This directory holds the long-form documentation for the AegisOne platform.

## Documents

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System architecture, components, data flow, deployment topology. |
| [`SECURITY.md`](../SECURITY.md) | Security policy, vulnerability disclosure, threat model summary. |
| [`PRIVACY.md`](PRIVACY.md) | Privacy model, data inventory, retention, deletion process. |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Production deployment runbook for backend, dashboard, and Android. |
| [`TESTING.md`](TESTING.md) | Test strategy, tooling, coverage gates, manual QA. |
| [`THREAT_MODEL.md`](THREAT_MODEL.md) | Detailed threat model. STRIDE-style analysis. |
| [`adr/`](adr/) | Architectural decision records. |

## Architectural decision records (ADRs)

We record significant architectural and security decisions as ADRs in [`adr/`](adr/).

Each ADR is a short Markdown file with the format:

```text
# NNN. Title
Status: proposed | accepted | superseded
Date: YYYY-MM-DD

## Context
## Decision
## Consequences
```

The current decision register:

- `001-monorepo-layout.md`
- `002-auth-token-strategy.md`
- `003-no-covert-operation.md`
