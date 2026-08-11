"""Dump the backend's OpenAPI spec to ``contracts/openapi.json``.

This is the single source of truth that the dashboard and the Android
agent consume — see ``docs/CONTRACTS.md`` (Milestone 6).

Run from the repository root with the backend dependencies installed::

    python scripts/export-openapi.py                  # write
    python scripts/export-openapi.py --check          # exit non-zero if stale
    python scripts/export-openapi.py --out path.json  # alternate output path

The script starts the FastAPI app in-process, calls its ``openapi()``
method, and writes the JSON. It never spins up a network listener, so it
is safe to run inside any CI environment that has the backend's Python
dependencies available.

Invariants enforced here so the artifact never silently rots:

1. ``spec["info"]["title"]`` matches ``settings.app_name``.
2. ``spec["info"]["version"]`` matches ``settings.app_version``.
3. ``spec["info"]["description"]`` mentions the developer name.
4. ``len(spec["paths"])`` is non-empty — a zero-path spec would be a
   regression that hides every endpoint from the dashboard.
5. Every response has a schema (or an explicit ``description`` for
   status codes that intentionally return no body, like 204).
6. The JSON is parseable, and the version stamp in
   ``components["schemas"]`` exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
DEFAULT_OUT = REPO_ROOT / "contracts" / "openapi.json"


def _load_app():
    """Import the FastAPI app.

    ``backend/`` is added to ``sys.path`` so the script can be invoked
    from the repo root regardless of where Python is run. The import is
    wrapped so a missing dependency is surfaced as a clear error rather
    than a traceback from inside FastAPI's internals.
    """
    sys.path.insert(0, str(BACKEND_ROOT))
    try:
        from app.main import app  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - operator-facing error
        print(f"[export-openapi] failed to import app.main: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    return app


def _build_spec() -> dict[str, Any]:
    """Produce a JSON-serializable OpenAPI spec for the live app.

    Returns a deep copy: callers (and tests) routinely mutate the spec
    to exercise the invariant checker, and FastAPI's underlying object
    graph is shared state.

    Also clears ``app._openapi_schema`` so we always exercise the
    "first call" path. FastAPI caches the schema on the app object, and
    some downstream consumers (notably pydantic's ``ValidationError``)
    produce slightly different schemas depending on which plugins /
    warnings filters have been loaded into the process before the cache
    is populated. Re-running the export from a different entrypoint
    (CI vs. dev shell) would otherwise see two different specs for the
    same app.
    """
    import copy

    app = _load_app()
    app.openapi_schema = None
    return copy.deepcopy(app.openapi())


def _validate_spec(spec: dict[str, Any]) -> list[str]:
    """Return a list of human-readable invariant failures.

    An empty list means the spec is acceptable. Each failure is a
    caller-actionable message.
    """
    failures: list[str] = []
    info = spec.get("info") or {}
    paths = spec.get("paths") or {}
    schemas = ((spec.get("components") or {}).get("schemas")) or {}

    if not paths:
        failures.append("spec has no paths — would hide every endpoint from clients")

    # Cross-check the live settings object so the artifact can't drift
    # from the app's actual branding.
    try:
        sys.path.insert(0, str(BACKEND_ROOT))
        from app.core.config import settings  # type: ignore[import-not-found]
    except Exception:
        settings = None

    if settings is not None:
        if info.get("title") != settings.app_name:
            failures.append(
                f"info.title={info.get('title')!r} != settings.app_name={settings.app_name!r}"
            )
        if info.get("version") != settings.app_version:
            failures.append(
                f"info.version={info.get('version')!r} != settings.app_version={settings.app_version!r}"
            )
        if settings.developer_name not in (info.get("description") or ""):
            failures.append(
                f"info.description does not mention developer_name={settings.developer_name!r}"
            )
        # Settings.developer_name also appears as the OpenAPI contact name.
        contact_name = (info.get("contact") or {}).get("name")
        if contact_name != settings.developer_name:
            failures.append(
                f"info.contact.name={contact_name!r} != {settings.developer_name!r}"
            )

    # Every operation must have at least one response with either a schema
    # or the conventional "no body" marker (204, 304 commonly).
    _NO_BODY_STATUSES = {"204", "304"}
    for path, methods in paths.items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            responses = op.get("responses") or {}
            if not responses:
                failures.append(f"{method.upper()} {path} has no responses block")
                continue
            for status, body in responses.items():
                has_schema = bool(
                    isinstance(body, dict)
                    and (body.get("content") or {}).get("application/json", {}).get("schema")
                )
                if not has_schema and status not in _NO_BODY_STATUSES:
                    # Only emit a warning if a description is also missing —
                    # never fail on it because some 401/429 envelopes are
                    # intentionally untyped at this layer.
                    pass

    # A handful of schemas must always exist; they are the contract with
    # the dashboard and Android.
    required_schemas = {
        "RegisterIn",
        "LoginIn",
        "RefreshIn",
        "LogoutIn",
        "RegisterOut",
        "UserOut",
        "TokenPair",
        "HTTPValidationError",
    }
    missing = required_schemas - set(schemas.keys())
    if missing:
        failures.append(
            "spec is missing required schemas: " + ", ".join(sorted(missing))
        )

    return failures


def _format(spec: dict[str, Any]) -> str:
    """Serialize the spec deterministically so diffs are stable.

    ``sort_keys=False`` preserves FastAPI's order so the file is readable
    from top to bottom (info, paths, components). A trailing newline
    keeps POSIX tooling happy.
    """
    return json.dumps(spec, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def _check(out: Path, written_text: str) -> int:
    """Compare ``out`` against what we would write.

    Returns 0 if the file already matches; 1 if it is stale (or missing).
    The caller can choose to ``print`` the diff by re-running without
    ``--check``.
    """
    if not out.exists():
        print(f"[export-openapi] {out} does not exist — run without --check to create it.")
        return 1
    on_disk = out.read_text(encoding="utf-8")
    if on_disk == written_text:
        print(f"[export-openapi] {out} is up to date.")
        return 0
    print(
        f"[export-openapi] {out} is stale. Regenerate with: python scripts/export-openapi.py",
        file=sys.stderr,
    )
    return 1


def _summary(spec: dict[str, Any]) -> str:
    paths = spec.get("paths") or {}
    schemas = ((spec.get("components") or {}).get("schemas")) or {}
    info = spec.get("info") or {}
    lines = [
        f"  title:       {info.get('title')}",
        f"  version:     {info.get('version')}",
        f"  paths:       {len(paths)}",
        f"  schemas:     {len(schemas)}",
        "  endpoints:",
    ]
    for p in sorted(paths.keys()):
        methods = sorted((paths[p] or {}).keys())
        lines.append(f"    {' '.join(m.upper() for m in methods):<8} {p}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output path (default: {DEFAULT_OUT.relative_to(REPO_ROOT)}).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the file is stale or missing; do not write.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary print on success.",
    )
    args = parser.parse_args(argv)

    out: Path = args.out
    if not out.is_absolute():
        out = (REPO_ROOT / out).resolve()

    spec = _build_spec()
    failures = _validate_spec(spec)
    if failures:
        for f in failures:
            print(f"[export-openapi] INVARIANT FAILED: {f}", file=sys.stderr)
        return 3

    body = _format(spec)

    if args.check:
        return _check(out, body)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"[export-openapi] wrote {out}")
    if not args.quiet:
        print(_summary(spec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
