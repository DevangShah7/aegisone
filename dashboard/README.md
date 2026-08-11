# AegisOne Control Center — Next.js dashboard.

> **AegisOne** — Developed by Devang Shah.

This is the AegisOne web Control Center. It is a Next.js 14 app with the App Router, Tailwind CSS, shadcn/ui primitives, and TypeScript strict mode.

## Quick start

```bash
cd dashboard
pnpm install
pnpm dev          # http://localhost:3000
```

## Production build

```bash
pnpm build
pnpm start
```

The dashboard is deployable to Vercel (see `docs/DEPLOYMENT.md`). The backend it talks to must be reachable at `NEXT_PUBLIC_API_BASE_URL`.

## Configuration

| Env var | Purpose | Default |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend base URL (used in the browser) | `http://localhost:8000` |
| `NEXT_PUBLIC_APP_NAME` | Override the product name shown in the UI | `AegisOne` |
| `NEXT_PUBLIC_DEVELOPER_NAME` | Override the developer credit | `Devang Shah` |

## Layout

- `app/` — Next.js App Router routes (`/`, `/login`, `/register`, `/about`).
- `components/ui/` — shadcn-style primitives (Button, Card, Input, Label).
- `lib/branding.ts` — single source of truth for user-facing strings.
- `lib/api.ts` — typed API client (skeleton until the OpenAPI generator lands).

## Status

- ✅ Milestone 1: scaffold, branding, login + register + about pages, dark mode, secure headers.
- ⏳ Milestone 1 (continued): real auth flow against the backend (next iteration).
- ⏳ Milestone 2: Devices list + detail + enrollment.
- ⏳ Milestone 3: command palette and live device status.
