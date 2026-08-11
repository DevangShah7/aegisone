"use client";

import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { DashboardShell } from "@/app/dashboard-shell";

export default function SettingsPage() {
  return (
    <DashboardShell>
      <SettingsContent />
    </DashboardShell>
  );
}

function SettingsContent() {
  const { user, logout } = useAuth();
  const router = useRouter();

  async function onSignOut() {
    await logout();
    document.cookie = "aegisone.session=; Path=/; Max-Age=0; SameSite=Lax";
    router.replace("/login");
  }

  return (
    <section className="max-w-md">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Your account and security options.</p>
      </header>

      <div className="rounded-lg border border-border p-6">
        <h2 className="mb-4 text-lg font-medium">Profile</h2>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Email</dt>
            <dd>{user?.email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">MFA</dt>
            <dd>{user?.mfa_enabled ? "Enabled" : "Disabled"}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Verified</dt>
            <dd>{user?.is_verified ? "Yes" : "No"}</dd>
          </div>
        </dl>
      </div>

      <div className="mt-6 rounded-lg border border-border p-6">
        <h2 className="mb-4 text-lg font-medium text-destructive">Sign out</h2>
        <p className="text-sm text-muted-foreground">
          Signing out revokes this browser&apos;s refresh token. Other devices
          and browsers remain signed in.
        </p>
        <button
          type="button"
          onClick={onSignOut}
          className="mt-4 inline-flex h-9 items-center justify-center rounded-md bg-destructive px-4 text-sm font-medium text-destructive-foreground hover:bg-destructive/90"
        >
          Sign out of this browser
        </button>
      </div>
    </section>
  );
}
