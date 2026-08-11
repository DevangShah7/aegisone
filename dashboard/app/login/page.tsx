"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { APP_NAME, APP_TAGLINE, DEVELOPER_NAME } from "@/lib/branding";

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginFallback />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginFallback() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-12 text-muted-foreground">
      Loading…
    </main>
  );
}

function LoginForm() {
  const { login, backendReachable } = useAuth();
  const router = useRouter();
  const sp = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const device_id =
        typeof window !== "undefined"
          ? window.localStorage.getItem("aegisone.device_id") ?? `web-${crypto.randomUUID()}`
          : "server";
      if (typeof window !== "undefined") {
        window.localStorage.setItem("aegisone.device_id", device_id);
      }
      await login(email, password, device_id);
      const next = sp.get("next") ?? "/devices";
      // The ``next`` query is a string; cast to a typed route for Next.js.
      router.push(next as "/devices");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
            {APP_NAME}
          </span>
          <CardTitle className="text-2xl">Welcome back</CardTitle>
          <CardDescription>{APP_TAGLINE}</CardDescription>
        </CardHeader>

        <form className="space-y-4" onSubmit={onSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
            {!backendReachable ? (
              <p className="text-xs text-amber-700 dark:text-amber-300" role="status">
                Backend unreachable. Start the API server (<code>python -m app</code> in <code>backend/</code>) and reload.
              </p>
            ) : null}
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Signing in..." : "Log in"}
            </Button>
            <p className="text-xs text-muted-foreground">
              No account yet?{" "}
              <Link href="/register" className="font-medium text-primary hover:underline">
                Create one
              </Link>
              .
            </p>
          </CardFooter>
        </form>
      </Card>

      <footer className="absolute bottom-4 left-0 right-0 text-center text-xs text-muted-foreground">
        Developed by {DEVELOPER_NAME}
      </footer>
    </main>
  );
}
