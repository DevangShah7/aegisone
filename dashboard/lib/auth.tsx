"use client";

/**
 * Auth context for the AegisOne dashboard.
 *
 * The backend returns access tokens (JWT, 15 min) and refresh tokens
 * (opaque, 30 d). For this slice we keep the refresh token in
 * ``sessionStorage`` so it survives a page refresh but is wiped when
 * the tab is closed. The access token is held in memory by this React
 * context and rehydrated by exchanging the refresh token on first
 * mount.
 *
 * Note on cookies: in production the backend can be configured to set
 * the refresh token via a ``Set-Cookie`` header (``Secure; SameSite=Lax;
 * HttpOnly``) so it never reaches JavaScript. For this slice the
 * dashboard lives on ``localhost:3000`` and the backend on the public
 * ``*.trycloudflare.com`` tunnel, so cross-site cookies would be
 * blocked by the browser. We therefore keep the refresh token in
 * sessionStorage on the client side. This is documented as a deliberate
 * dev-mode choice; the server-side cookie path stays available in
 * production via the reverse proxy.
 */

import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { ApiError, getApiBaseUrl } from "@/lib/api";

export type AuthUser = {
  id: string;
  email: string;
  is_active: boolean;
  is_verified: boolean;
  mfa_enabled: boolean;
  created_at: string;
};

export type AuthContextValue = {
  accessToken: string | null;
  user: AuthUser | null;
  isHydrating: boolean;
  backendReachable: boolean;
  login: (email: string, password: string, device_id: string) => Promise<void>;
  register: (email: string, password: string, device_id: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<boolean | void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const DEVICE_ID_KEY = "aegisone.device_id";
const REFRESH_TOKEN_KEY = "aegisone.refresh_token";

function getOrCreateDeviceId(): string {
  if (typeof window === "undefined") {
    return "server";
  }
  const existing = window.localStorage.getItem(DEVICE_ID_KEY);
  if (existing) return existing;
  // Stable per-browser device id used for refresh-token rotation.
  const id = `web-${crypto.randomUUID()}`;
  window.localStorage.setItem(DEVICE_ID_KEY, id);
  return id;
}

function readStoredRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(REFRESH_TOKEN_KEY);
}

function writeStoredRefreshToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.sessionStorage.setItem(REFRESH_TOKEN_KEY, token);
  } else {
    window.sessionStorage.removeItem(REFRESH_TOKEN_KEY);
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isHydrating, setIsHydrating] = useState(true);
  const [backendReachable, setBackendReachable] = useState(true);

  const fetchMe = useCallback(async (token: string) => {
    const res = await fetch(`${getApiBaseUrl()}/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
      credentials: "include",
    });
    if (res.ok) {
      setUser((await res.json()) as AuthUser);
    }
  }, []);

  const refresh = useCallback(async (): Promise<boolean> => {
    // Skip the network round-trip entirely when there's no stored
    // refresh token. Sending a placeholder ``refresh_token`` would
    // either 422 against the schema or 401 against the backend's
    // session table; an empty body is also rejected.
    const stored = readStoredRefreshToken();
    if (!stored) {
      setAccessToken(null);
      setUser(null);
      return false;
    }

    let res: Response;
    try {
      res = await fetch(`${getApiBaseUrl()}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          refresh_token: stored,
          device_id: getOrCreateDeviceId(),
        }),
      });
    } catch (networkErr) {
      // Backend unreachable — treat as "no session" without re-throwing
      // so callers don't surface a console error. The browser still logs
      // the failed request, but JS callers can carry on gracefully.
      setAccessToken(null);
      setUser(null);
      setBackendReachable(false);
      return false;
    }
    setBackendReachable(true);
    if (!res.ok) {
      // Refresh token invalid — drop it so the next mount doesn't retry.
      writeStoredRefreshToken(null);
      setAccessToken(null);
      setUser(null);
      return false;
    }
    const body = await res.json();
    setAccessToken(body.access_token);
    if (typeof body.refresh_token === "string" && body.refresh_token) {
      writeStoredRefreshToken(body.refresh_token);
    }
    return true;
  }, []);

  const login = useCallback(
    async (email: string, password: string, device_id: string) => {
      let res: Response;
      try {
        res = await fetch(`${getApiBaseUrl()}/auth/login`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, device_id }),
        });
      } catch (networkErr) {
        setBackendReachable(false);
        throw new ApiError(
          "Cannot reach the AegisOne backend. Is the API server running?",
          0,
          "backend_unreachable",
        );
      }
      setBackendReachable(true);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(
          body?.detail?.message ?? "Login failed",
          res.status,
          body?.detail?.code ?? "unknown",
        );
      }
      const body = await res.json();
      setAccessToken(body.access_token);
      // The refresh token travels in sessionStorage so it survives a
      // page refresh on this tab but is wiped when the tab closes.
      if (typeof body.refresh_token === "string" && body.refresh_token) {
        writeStoredRefreshToken(body.refresh_token);
      }
      await fetchMe(body.access_token);
    },
    [fetchMe],
  );

  const register = useCallback(
    async (email: string, password: string, device_id: string) => {
      const res = await fetch(`${getApiBaseUrl()}/auth/register`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, device_id }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(
          body?.detail?.message ?? "Registration failed",
          res.status,
          body?.detail?.code ?? "unknown",
        );
      }
      // Auto-login after registration so the user lands on /devices.
      await login(email, password, device_id);
    },
    [login],
  );

  const logout = useCallback(async () => {
    const stored = readStoredRefreshToken();
    if (stored) {
      await fetch(`${getApiBaseUrl()}/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: stored }),
      }).catch(() => undefined);
    }
    writeStoredRefreshToken(null);
    setAccessToken(null);
    setUser(null);
  }, []);

  // On first mount, try to refresh — succeeds if the sessionStorage
  // entry is still there (same-tab refresh).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ok = await refresh();
        if (!cancelled && ok && accessToken) {
          await fetchMe(accessToken);
        }
      } catch {
        // No valid session — anonymous.
      } finally {
        // Critical: always clear isHydrating, even on unexpected errors,
        // otherwise the app is stuck on the "Loading AegisOne…" / Suspense
        // fallback and the user sees a blank page.
        if (!cancelled) setIsHydrating(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-fetch the user whenever the access token changes (post-login).
  useEffect(() => {
    if (!accessToken) {
      setUser(null);
      return;
    }
    fetchMe(accessToken).catch(() => undefined);
  }, [accessToken, fetchMe]);

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken,
      user,
      isHydrating,
      backendReachable,
      login,
      register,
      logout,
      refresh,
    }),
    [accessToken, user, isHydrating, backendReachable, login, register, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}
