"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth";
import { APP_NAME, APP_TAGLINE, DEVELOPER_NAME } from "@/lib/branding";
import { cn } from "@/lib/cn";

const NAV = [
  { href: "/devices" as const, label: "Devices" },
  { href: "/devices/enroll" as const, label: "Enroll a device" },
  { href: "/audit" as const, label: "Audit log" },
  { href: "/settings" as const, label: "Settings" },
  { href: "/about" as const, label: "About" },
];

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const { user, isHydrating, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // If hydration finishes and we have no user, send to /login.
  useEffect(() => {
    if (!isHydrating && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [isHydrating, user, router, pathname]);

  if (isHydrating) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        <span>Loading AegisOne…</span>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  async function onLogout() {
    await logout();
    // We don't rely on a session-marker cookie for auth, so nothing to
    // delete here. The refresh token (in sessionStorage) is wiped by
    // `logout()` itself.
    router.replace("/login");
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/devices" className="flex items-center gap-2">
            <span className="text-sm font-semibold uppercase tracking-widest">
              {APP_NAME}
            </span>
            <span className="text-xs text-muted-foreground">{APP_TAGLINE}</span>
          </Link>
          <div className="flex items-center gap-4">
            <span className="text-xs text-muted-foreground">{user.email}</span>
            <button
              type="button"
              onClick={onLogout}
              className="text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-6xl gap-8 px-6 py-8">
        <nav className="w-44 shrink-0">
          <ul className="space-y-1">
            {NAV.map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== "/devices" && pathname.startsWith(item.href));
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={cn(
                      "block rounded-md px-3 py-2 text-sm transition-colors",
                      active
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <main className="flex-1">{children}</main>
      </div>

      <footer className="mx-auto max-w-6xl border-t border-border px-6 py-6 text-xs text-muted-foreground">
        <p>
          {APP_NAME} — developed by{" "}
          <span className="font-medium text-foreground">{DEVELOPER_NAME}</span>.
        </p>
      </footer>
    </div>
  );
}
