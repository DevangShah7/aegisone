"use client";

import { useState } from "react";

import { useAuth } from "@/lib/auth";
import { ApiError, getApiBaseUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type EnrollmentResponse = {
  pairing_code: string;
  device_id: string;
  expires_at: string;
};

export default function EnrollPage() {
  const { accessToken } = useAuth();
  const [deviceName, setDeviceName] = useState("My device");
  const [result, setResult] = useState<EnrollmentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onGenerate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!accessToken) {
      setError("Please sign in first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${getApiBaseUrl()}/devices/enroll/request`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        credentials: "include",
        body: JSON.stringify({ device_name: deviceName }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(
          body?.detail?.message ?? "Failed to generate pairing code",
          res.status,
          body?.detail?.code ?? "enroll_failed",
        );
      }
      setResult((await res.json()) as EnrollmentResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate pairing code");
    } finally {
      setBusy(false);
    }
  }

  async function copyCode() {
    if (!result) return;
    await navigator.clipboard.writeText(result.pairing_code);
  }

  return (
    <section className="max-w-md">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Enroll a device</h1>
        <p className="text-sm text-muted-foreground">
          Generate a 6-digit pairing code and open the AegisOne app on the device.
          The code expires in 10 minutes.
        </p>
      </header>

      {!result ? (
        <form onSubmit={onGenerate} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="device_name">Device name</Label>
            <Input
              id="device_name"
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
              maxLength={120}
              required
            />
          </div>
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" disabled={busy}>
            {busy ? "Generating…" : "Generate pairing code"}
          </Button>
        </form>
      ) : (
        <div className="space-y-6 rounded-lg border border-border p-6">
          <div>
            <p className="text-xs uppercase tracking-widest text-muted-foreground">
              Pairing code
            </p>
            <p className="mt-2 font-mono text-4xl font-semibold tracking-[0.4em]">
              {result.pairing_code}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Expires at {new Date(result.expires_at).toLocaleTimeString()}
            </p>
          </div>
          <div className="space-y-2">
            <Label>Device id</Label>
            <Input value={result.device_id} readOnly className="font-mono text-xs" />
          </div>
          <div className="flex gap-2">
            <Button type="button" onClick={copyCode} variant="outline">
              Copy code
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setResult(null)}
            >
              Generate a new one
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Open the AegisOne Android app, choose &quot;Enroll&quot;, and enter this
            code. The device will appear under <strong>Devices</strong> once it
            completes pairing.
          </p>
        </div>
      )}
    </section>
  );
}
