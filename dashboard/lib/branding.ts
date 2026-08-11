/**
 * AegisOne branding constants.
 *
 * Single source of truth for user-facing strings used by the dashboard.
 * Mirror the values in `backend/app/core/config.py` so both apps agree.
 *
 * Override at build time via the environment variables prefixed with
 * `NEXT_PUBLIC_` (e.g. `NEXT_PUBLIC_DEVELOPER_NAME`).
 */
export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "AegisOne";
export const APP_TAGLINE =
  process.env.NEXT_PUBLIC_APP_TAGLINE ?? "Secure Remote Device Management";
export const DEVELOPER_NAME = process.env.NEXT_PUBLIC_DEVELOPER_NAME ?? "Devang Shah";
export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "0.1.0";
export const APP_TAG = process.env.NEXT_PUBLIC_APP_TAG ?? "Secure. Manage. Protect.";