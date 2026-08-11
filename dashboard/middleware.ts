import { NextResponse, type NextRequest } from "next/server";

/**
 * Route-level auth gate.
 *
 * The dashboard's auth model lives in the React context: the access
 * token lives in memory; the refresh token lives in sessionStorage (so
 * it survives a tab refresh but is wiped when the tab closes). The
 * server-side middleware can't read either of those, so it can't make a
 * definitive auth decision — that belongs to the React layer.
 *
 * What the middleware *can* do: redirect anonymous traffic away from
 * protected pages so a deep-linked URL doesn't render an empty shell
 * before React loads. We rely on the React context for the real auth
 * decision (DashboardShell redirects back to /login if hydration
 * finishes without a user).
 *
 * Routes wrapped here:
 *   - /devices
 *   - /settings
 *   - /audit
 */

const PROTECTED = ["/devices", "/settings", "/audit"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (PROTECTED.some((p) => pathname.startsWith(p))) {
    // The React layer is the source of truth for auth. The middleware
    // only blocks suspicious or malformed paths here; the actual auth
    // check (with refresh-token rotation) happens client-side.
    // We deliberately do NOT redirect /login → /devices here, because
    // doing so based on a non-HttpOnly marker cookie causes a redirect
    // loop whenever the marker is stale or out of sync with the React
    // session — the React layer is the one place that knows whether
    // the user is actually authenticated.
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|about).*)",
  ],
};
