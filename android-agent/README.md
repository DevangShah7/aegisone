# AegisOne Android Agent — Kotlin / Jetpack Compose

> **AegisOne** — Developed by Devang Shah.

The Android agent is the on-device component of AegisOne. It is installed only on devices the owner has explicitly enrolled. It uses the platform's official APIs and surfaces a visible system indicator whenever a sensitive capability is in use.

## Prerequisites

- **JDK 17+.** Android Gradle Plugin 8.x requires JDK 17. JDK 25 is not supported by AGP 8.x — install JDK 17 (e.g. Eclipse Temurin) and set `JAVA_HOME` to its install root.
- **Android SDK** with platform 36, build-tools 36.1.0, and platform-tools.
  - On Windows: `C:\Users\DEVANG\AppData\Local\Android\Sdk` (see `local.properties`).
- **Gradle wrapper** is committed; uses Gradle 8.14.3.

## Build

```bash
cd android-agent
./gradlew :app:assembleDebug
```

Output: `app/build/outputs/apk/debug/app-debug.apk`.

## Install on a device or emulator

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## What's in this slice

The shipped APK contains:

- **Home screen** with status card and "Enroll this device" CTA.
- **Enrollment screen** — the user enters the 6-digit pairing code the
  operator produced on the dashboard, plus the device UUID. The agent
  exchanges the code for opaque tokens via `POST /devices/enroll/confirm`
  and persists them in DataStore.
- **Heartbeat worker** — runs every 15 minutes via WorkManager,
  posts `DeviceHeartbeatIn` to `/devices/{id}/heartbeat`.
- **Foreground service** — shows a persistent notification in the
  `aegisone_active` channel while the agent is paired. Removing the
  notification kills the agent (visible, per ADR-003).
- **Device info collector** — battery, network type, free storage, OS
  version, hardware model. Read-only public APIs.

Build verified: `app-debug.apk` is 18 MB, `package: com.aegisone.agent.debug`,
`label: AegisOne`, `sdkVersion: 26`, `targetSdkVersion: 35`.

## Permissions policy

The manifest starts with the minimum permission set:

- `INTERNET`, `ACCESS_NETWORK_STATE` — backend communication.
- `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`, `POST_NOTIFICATIONS` — visible pairing indicator.

Every additional permission is added in a phase-specific PR after a
justification in `docs/THREAT_MODEL.md`. **No device-admin, no
accessibility service, no silent overlays, no covert capture** — see
`docs/adr/003-no-covert-operation.md`.

## Future capabilities (next slices)

The next slices overlay these features behind an explicit per-device
consent gate (the device's UI is the only place a consent is granted):

- Location (Fused Location + foreground service, persistent indicator).
- Screenshot / screen-share (MediaProjection + persistent indicator).
- Camera / microphone diagnostics (one-shot, with system indicator).
- Application inventory (`QUERY_ALL_PACKAGES` + rationale UI).
- Geofencing, lost-device mode (lock, ring, locate).
- Tamper detection (read-only report, no enforcement).
