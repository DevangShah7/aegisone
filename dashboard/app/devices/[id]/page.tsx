"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { useAuth } from "@/lib/auth";
import { ApiError, getApiBaseUrl } from "@/lib/api";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";

type DeviceDetail = {
  id: string;
  name: string;
  hardware_model: string | null;
  os_version: string | null;
  app_version: string | null;
  battery_pct: number | null;
  network_type: string | null;
  enrollment_state: "pending" | "active" | "revoked";
  last_seen_at: string | null;
  created_at: string;
  consents: { id: string; capability: string; granted_at: string; expires_at: string | null; revoked_at: string | null }[];
  last_activity: { id: number; event_type: string; occurred_at: string; payload: Record<string, unknown> }[];
};

type LocationFix = {
  latitude: number;
  longitude: number;
  accuracy_m: number | null;
  provider: string | null;
  captured_at: string | null;
};

function lastLocationFix(activity: DeviceDetail["last_activity"]): LocationFix | null {
  for (const e of activity) {
    if (e.event_type !== "location.update") continue;
    const p = (e.payload ?? {}) as Record<string, unknown>;
    const lat = Number(p.latitude);
    const lng = Number(p.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
    return {
      latitude: lat,
      longitude: lng,
      accuracy_m: Number.isFinite(Number(p.accuracy_m)) ? Number(p.accuracy_m) : null,
      provider: typeof p.provider === "string" ? p.provider : null,
      captured_at: typeof p.captured_at === "string" ? p.captured_at : null,
    };
  }
  return null;
}

const COMMAND_CAPS = [
  { value: "screenshot", label: "Take a screenshot", needsConsent: "screenshot" },
  { value: "screen_share", label: "Start screen share", needsConsent: "screen_share" },
  { value: "locate", label: "Locate device", needsConsent: "location" },
  { value: "lock", label: "Lock device", needsConsent: null },
  { value: "ring", label: "Ring device", needsConsent: null },
];

export default function DeviceDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { accessToken } = useAuth();
  const [device, setDevice] = useState<DeviceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [commandResult, setCommandResult] = useState<{ command_id: string; status: string; expires_at: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refreshDevice = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${getApiBaseUrl()}/devices/${id}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
        credentials: "include",
      });
      if (res.ok) setDevice((await res.json()) as DeviceDetail);
    } catch {
      // Polling failures are silent — the next interval will retry.
    }
  }, [accessToken, id]);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${getApiBaseUrl()}/devices/${id}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
          credentials: "include",
        });
        if (!res.ok) {
          throw new ApiError(`Failed to load device (${res.status})`, res.status, "load_failed");
        }
        if (!cancelled) setDevice((await res.json()) as DeviceDetail);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load device");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, id]);

  async function sendCommand(capability: string) {
    if (!accessToken) return;
    setBusy(capability);
    setCommandResult(null);
    setError(null);
    try {
      const res = await fetch(`${getApiBaseUrl()}/devices/${id}/command/${capability}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        credentials: "include",
        body: JSON.stringify({ session_seconds: 60, reason: "Operator request" }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const code = body?.detail?.code;
        if (code === "consent_required") {
          setError(
            "The device owner has not yet granted this capability. Approve it on the device first.",
          );
        } else {
          setError(body?.detail?.message ?? `Command failed (${res.status})`);
        }
        return;
      }
      setCommandResult(body);
      // For location, the agent has to collect a fix and POST it back
      // as a ``location.update`` activity event. Poll the detail endpoint
      // for up to 30 s so the operator sees the fix without having to
      // manually reload the page.
      if (capability === "locate") {
        const deadline = Date.now() + 30_000;
        const tick = async () => {
          if (Date.now() > deadline) return;
          await refreshDevice();
          const fresh = (await (await fetch(`${getApiBaseUrl()}/devices/${id}`, {
            headers: { Authorization: `Bearer ${accessToken}` },
            credentials: "include",
          })).json()) as DeviceDetail;
          const got = lastLocationFix(fresh.last_activity);
          if (!got) {
            setTimeout(tick, 2_000);
          }
        };
        void tick();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Command failed");
    } finally {
      setBusy(null);
    }
  }

  async function revoke() {
    if (!accessToken) return;
    if (!confirm("Revoke this device? The agent will be disconnected immediately.")) return;
    setBusy("revoke");
    try {
      const res = await fetch(`${getApiBaseUrl()}/devices/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
        credentials: "include",
      });
      if (res.ok) {
        // Refresh detail.
        const detail = await fetch(`${getApiBaseUrl()}/devices/${id}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
          credentials: "include",
        });
        if (detail.ok) setDevice((await detail.json()) as DeviceDetail);
      }
    } finally {
      setBusy(null);
    }
  }

  if (error && !device) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (!device) {
    return <p className="text-sm text-muted-foreground">Loading device…</p>;
  }

  return (
    <section className="space-y-6">
      <header>
        <Link href="/devices" className="text-xs text-muted-foreground hover:underline">
          ← Back to devices
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{device.name}</h1>
            <p className="text-sm text-muted-foreground">
              {device.hardware_model ?? "Unknown model"}
              {device.os_version ? ` · ${device.os_version}` : ""}
              {device.app_version ? ` · AegisOne ${device.app_version}` : ""}
            </p>
          </div>
          <StatusPill state={device.enrollment_state} lastSeen={device.last_seen_at} />
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Battery" value={device.battery_pct != null ? `${device.battery_pct}%` : "—"} />
        <Stat label="Network" value={device.network_type ?? "—"} />
        <Stat label="Last seen" value={device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : "Never"} />
      </div>

      <LocationCard fix={lastLocationFix(device.last_activity)} />

      <Card title="Commands">
        <p className="mb-4 text-sm text-muted-foreground">
          Sending a command prompts the device owner to approve it on the device. Lost-device
          commands (lock, ring) do not require consent.
        </p>
        <div className="flex flex-wrap gap-2">
          {COMMAND_CAPS.map((c) => (
            <Button
              key={c.value}
              variant={c.needsConsent ? "default" : "outline"}
              disabled={busy !== null || device.enrollment_state !== "active"}
              onClick={() => sendCommand(c.value)}
            >
              {busy === c.value ? "Sending…" : c.label}
            </Button>
          ))}
          <Button
            variant="destructive"
            disabled={busy !== null || device.enrollment_state === "revoked"}
            onClick={revoke}
          >
            {busy === "revoke" ? "Revoking…" : "Revoke device"}
          </Button>
        </div>
        {commandResult ? (
          <p className="mt-4 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-300">
            Command sent. ID: <span className="font-mono">{commandResult.command_id}</span> ·
            expires {new Date(commandResult.expires_at).toLocaleTimeString()}.
          </p>
        ) : null}
        {error ? (
          <p className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
            {error}
          </p>
        ) : null}
      </Card>

      <Card title="Consents">
        {device.consents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No active consents. The device owner must grant each capability on the device.
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {device.consents.map((c) => (
              <li
                key={c.id}
                className="rounded-full border border-border px-3 py-1 text-xs"
              >
                {c.capability}
                {c.revoked_at ? " · revoked" : ""}
                {c.expires_at ? ` · expires ${new Date(c.expires_at).toLocaleString()}` : ""}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Recent activity">
        {device.last_activity.length === 0 ? (
          <p className="text-sm text-muted-foreground">No activity yet.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {device.last_activity.map((e) => (
              <li key={e.id} className="flex justify-between border-b border-border pb-2 last:border-0">
                <span className="font-mono text-xs">{e.event_type}</span>
                <span className="text-xs text-muted-foreground">
                  {new Date(e.occurred_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-xs uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border p-6">
      <h2 className="mb-4 text-lg font-medium">{title}</h2>
      {children}
    </div>
  );
}

function LocationCard({ fix }: { fix: LocationFix | null }) {
  return (
    <Card title="Last location">
      {fix === null ? (
        <p className="text-sm text-muted-foreground">
          The device hasn&apos;t shared a location yet. Tap &quot;Locate device&quot; below — the
          device owner will see a one-time consent prompt on the device, and a fix will appear
          here within seconds.
        </p>
      ) : (
        <div className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Coordinates:</span>{" "}
            <span className="font-mono">
              {fix.latitude.toFixed(6)}, {fix.longitude.toFixed(6)}
            </span>
          </p>
          <p>
            <span className="text-muted-foreground">Accuracy:</span>{" "}
            {fix.accuracy_m != null ? `±${Math.round(fix.accuracy_m)} m` : "unknown"}
            {fix.provider ? <span className="text-muted-foreground"> · {fix.provider}</span> : null}
          </p>
          {fix.captured_at ? (
            <p className="text-xs text-muted-foreground">
              Captured {new Date(Number(fix.captured_at)).toLocaleString()}
            </p>
          ) : null}
          <p className="pt-2">
            <a
              href={`https://www.openstreetmap.org/?mlat=${fix.latitude}&mlon=${fix.longitude}#map=17/${fix.latitude}/${fix.longitude}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              View on OpenStreetMap ↗
            </a>
          </p>
        </div>
      )}
    </Card>
  );
}
