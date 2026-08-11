"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/lib/auth";
import { ApiError, getApiBaseUrl } from "@/lib/api";
import { DashboardShell } from "@/app/dashboard-shell";

type Event = {
  id: number;
  device_id: string;
  event_type: string;
  occurred_at: string;
  payload: Record<string, unknown>;
};

export default function AuditPage() {
  return (
    <DashboardShell>
      <AuditContent />
    </DashboardShell>
  );
}

function AuditContent() {
  const { accessToken } = useAuth();
  const [events, setEvents] = useState<Event[] | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${getApiBaseUrl()}/activity?limit=200`, {
          headers: { Authorization: `Bearer ${accessToken}` },
          credentials: "include",
        });
        if (!res.ok) {
          throw new ApiError(`Failed to load events (${res.status})`, res.status, "load_failed");
        }
        if (!cancelled) setEvents((await res.json()) as Event[]);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load events");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const filtered = (events ?? []).filter((e) =>
    filter ? e.event_type.toLowerCase().includes(filter.toLowerCase()) : true,
  );

  function exportCsv() {
    if (!events) return;
    const rows = [
      ["id", "device_id", "event_type", "occurred_at", "payload"],
      ...events.map((e) => [
        String(e.id),
        e.device_id,
        e.event_type,
        e.occurred_at,
        JSON.stringify(e.payload),
      ]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aegisone-audit-${new Date().toISOString()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section>
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
          <p className="text-sm text-muted-foreground">
            Cross-device activity stream. Every sensitive action is recorded.
          </p>
        </div>
        <div className="flex gap-2">
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by event type…"
            className="h-9 rounded-md border border-border bg-background px-3 text-sm"
          />
          <button
            type="button"
            onClick={exportCsv}
            disabled={!events}
            className="inline-flex h-9 items-center justify-center rounded-md border border-border px-3 text-sm hover:bg-accent disabled:opacity-50"
          >
            Export CSV
          </button>
        </div>
      </header>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {events === null ? (
        <p className="text-sm text-muted-foreground">Loading events…</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No events match.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase">Event</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase">Device</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase">When</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase">Payload</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr key={e.id} className="border-t border-border">
                  <td className="px-3 py-2 font-mono text-xs">{e.event_type}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {e.device_id.slice(0, 8)}…
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {new Date(e.occurred_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {JSON.stringify(e.payload)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
