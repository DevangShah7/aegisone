"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { useAuth } from "@/lib/auth";
import { ApiError, getApiBaseUrl } from "@/lib/api";
import { StatusPill } from "@/components/status-pill";

type Device = {
  id: string;
  name: string;
  hardware_model: string | null;
  os_version: string | null;
  app_version: string | null;
  battery_pct: number | null;
  network_type: string | null;
  enrollment_state: "pending" | "active" | "revoked";
  last_seen_at: string | null;
};

function formatRelative(iso: string | null): string {
  if (!iso) return "Never";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const minutes = Math.max(0, Math.round((now - then) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export default function DevicesPage() {
  const { accessToken } = useAuth();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${getApiBaseUrl()}/devices`, {
          headers: { Authorization: `Bearer ${accessToken}` },
          credentials: "include",
        });
        if (!res.ok) {
          throw new ApiError(`Failed to load devices (${res.status})`, res.status, "load_failed");
        }
        const body = (await res.json()) as Device[];
        if (!cancelled) setDevices(body);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load devices");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  return (
    <section>
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Devices</h1>
          <p className="text-sm text-muted-foreground">
            Devices you have enrolled in AegisOne.
          </p>
        </div>
        <Link
          href="/devices/enroll"
          className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Enroll a device
        </Link>
      </header>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {devices === null ? (
        <p className="text-sm text-muted-foreground">Loading devices…</p>
      ) : devices.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-10 text-center">
          <h2 className="text-lg font-medium">No devices yet</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Enroll your first device to start managing it from here.
          </p>
          <Link
            href="/devices/enroll"
            className="mt-4 inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Enroll a device
          </Link>
        </div>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {devices.map((d) => (
            <li key={d.id} className="flex items-center justify-between px-4 py-4">
              <div>
                <Link
                  href={`/devices/${d.id}`}
                  className="text-sm font-medium hover:underline"
                >
                  {d.name}
                </Link>
                <p className="text-xs text-muted-foreground">
                  {d.hardware_model ?? "Unknown model"}
                  {d.os_version ? ` · ${d.os_version}` : ""}
                  {d.battery_pct != null ? ` · ${d.battery_pct}% battery` : ""}
                </p>
              </div>
              <div className="flex items-center gap-4">
                <StatusPill state={d.enrollment_state} lastSeen={d.last_seen_at} />
                <span className="text-xs text-muted-foreground">
                  {formatRelative(d.last_seen_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
