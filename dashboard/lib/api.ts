/**
 * Typed API client skeleton.
 *
 * The real client is generated from `contracts/openapi.json` via
 * `openapi-typescript` once the backend ships (Milestone 1, step 11).
 * This module owns the request helper and base URL so the rest of the
 * app can call it today.
 */

const DEFAULT_BASE_URL = "http://localhost:8000";

/** Resolve the API base URL at runtime (client) or build time (server). */
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_BASE_URL;
  }
  return process.env.API_BASE_URL ?? DEFAULT_BASE_URL;
}

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(message: string, status: number, code: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.name = "ApiError";
  }
}

export type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  accessToken?: string | null;
  signal?: AbortSignal;
};

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${getApiBaseUrl()}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (options.accessToken) {
    headers["Authorization"] = `Bearer ${options.accessToken}`;
  }

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    credentials: "include",
  });

  if (!response.ok) {
    let payload: { code?: string; message?: string } = {};
    try {
      payload = await response.json();
    } catch {
      // Ignore: the error envelope may not be JSON.
    }
    throw new ApiError(
      payload.message ?? `request failed with status ${response.status}`,
      response.status,
      payload.code ?? "unknown",
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}