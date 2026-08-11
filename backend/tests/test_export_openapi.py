"""Tests for ``scripts/export-openapi.py``.

The export script is the contract between the backend, the dashboard,
and the Android agent. A regression here silently rots the public API
every consumer sees, so we test the invariant checker end-to-end
against the live FastAPI app rather than mocking ``app.openapi()``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "export-openapi.py"


def _load_export_module():
    """Load the hyphenated module via importlib.

    Keeps the script CLI-only (no package boilerplate) while still
    letting pytest call its helpers directly.
    """
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, "could not load export-openapi.py"
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_openapi"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def exp():
    return _load_export_module()


def test_build_spec_returns_live_app_spec(exp):
    """The helper pulls from the actual FastAPI app, not a fixture."""
    spec = exp._build_spec()
    assert spec["openapi"].startswith("3.")
    # Every Milestone-1 + Milestone-2 route must be present.
    paths = set(spec["paths"].keys())
    assert {
        "/healthz",
        "/readyz",
        "/about",
        "/auth/register",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/auth/logout-all",
        "/users/me",
        "/devices",
        "/devices/enroll/request",
        "/devices/enroll/confirm",
        "/activity",
    } <= paths


def test_validate_passes_against_real_app(exp):
    spec = exp._build_spec()
    failures = exp._validate_spec(spec)
    assert failures == [], f"unexpected invariant failures: {failures}"


def test_validate_detects_missing_paths(exp):
    spec = exp._build_spec()
    spec["paths"] = {}
    failures = exp._validate_spec(spec)
    assert any("no paths" in f for f in failures)


def test_validate_detects_wrong_title(exp):
    spec = exp._build_spec()
    spec["info"]["title"] = "AegisOne-Wrong"
    failures = exp._validate_spec(spec)
    assert any("info.title" in f for f in failures)


def test_validate_detects_missing_developer_credit(exp):
    spec = exp._build_spec()
    spec["info"]["description"] = "no developer name here"
    spec["info"]["contact"] = {"name": "Nobody"}
    failures = exp._validate_spec(spec)
    assert any("developer_name" in f for f in failures)
    assert any("contact.name" in f for f in failures)


def test_validate_detects_missing_required_schemas(exp):
    spec = exp._build_spec()
    spec["components"]["schemas"] = {}
    failures = exp._validate_spec(spec)
    assert any("missing required schemas" in f for f in failures)
    # And it names the schemas it expected.
    msg = next(f for f in failures if "missing required schemas" in f)
    assert "RegisterIn" in msg
    assert "TokenPair" in msg
    assert "UserOut" in msg


def test_format_produces_stable_diffable_text(exp):
    """``_format`` should always emit the same bytes for the same spec.

    The CI workflow relies on byte-equality (via ``--check``) to detect
    drift, so any whitespace noise here would be a flake.
    """
    spec = exp._build_spec()
    one = exp._format(spec)
    two = exp._format(spec)
    assert one == two
    assert one.endswith("\n")
    # Make sure the JSON is still valid — i.e. the formatter isn't producing
    # garbage that happens to round-trip through Python.
    parsed = json.loads(one)
    assert parsed["info"]["title"] == "AegisOne"


def test_check_returns_zero_when_file_matches(exp, tmp_path):
    out = tmp_path / "openapi.json"
    body = exp._format(exp._build_spec())
    out.write_text(body, encoding="utf-8")
    assert exp._check(out, body) == 0


def test_check_returns_one_when_file_differs(exp, tmp_path):
    out = tmp_path / "openapi.json"
    out.write_text("stale content\n", encoding="utf-8")
    body = exp._format(exp._build_spec())
    assert exp._check(out, body) == 1


def test_check_returns_one_when_file_missing(exp, tmp_path):
    out = tmp_path / "does-not-exist.json"
    body = exp._format(exp._build_spec())
    assert exp._check(out, body) == 1
