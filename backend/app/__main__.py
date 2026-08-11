"""Run the AegisOne backend with the right asyncio event loop.

Usage (from the backend/ directory)::

    python -m app

Or with explicit arguments forwarded to uvicorn::

    python -m app --port 8000 --reload

Why this exists
---------------

uvicorn 0.39's default Windows loop factory
(``uvicorn.loops.asyncio.asyncio_loop_factory``) hardcodes
``ProactorEventLoop`` regardless of the active event-loop policy. The
psycopg v3 driver refuses to run on ``ProactorEventLoop`` because it
uses ``socket.sendmsg`` / ``recvmsg`` which Proactor does not support.

We can't patch uvicorn's loop factory from inside the ASGI app module:
uvicorn resolves the factory before it imports the app string. So this
wrapper installs a Windows-compatible selector loop factory, then
delegates to ``uvicorn.run``.

On non-Windows platforms this is a thin pass-through to ``uvicorn.run``.
"""

from __future__ import annotations

import sys


def _install_selector_loop_on_windows() -> None:
    """Replace uvicorn's Windows loop factory with the selector variant.

    Safe to call on any platform — it's a no-op off Windows.
    """
    if sys.platform != "win32":
        return

    import asyncio
    from collections.abc import Callable

    import uvicorn.loops.asyncio as _uv_asyncio

    def _selector_loop_factory(
        use_subprocess: bool = False,  # noqa: ARG001
    ) -> Callable[[], asyncio.AbstractEventLoop]:
        # The selector loop works for both in-process and subprocess
        # workers; the only reason uvicorn's stock factory picks
        # ProactorEventLoop on Windows is to support the subprocess
        # transport, but psycopg (and many other async DB drivers)
        # require the selector variant.
        return asyncio.SelectorEventLoop

    _uv_asyncio.asyncio_loop_factory = _selector_loop_factory


def main() -> int:
    """Entry point for ``python -m app``."""
    _install_selector_loop_on_windows()

    import uvicorn

    # Mirror ``python -m uvicorn`` argument parsing. ``uvicorn.main:run``
    # doesn't expose its CLI to programmatic callers, so we hand the
    # most common flags through and let everything else fall back to
    # uvicorn's defaults.
    args = sys.argv[1:]

    # Default to 0.0.0.0 so the Android agent on a phone on the same
    # Wi-Fi can reach the backend. ``--host 127.0.0.1`` from the CLI
    # still overrides this for desktop-only development.
    host = "0.0.0.0"  # noqa: S104
    port = 8000
    if "--host" in args:
        i = args.index("--host")
        if i + 1 < len(args):
            host = args[i + 1]
            args = args[:i] + args[i + 2 :]
    if "--port" in args:
        i = args.index("--port")
        if i + 1 < len(args):
            port = int(args[i + 1])
            args = args[:i] + args[i + 2 :]

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload="--reload" in args,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
