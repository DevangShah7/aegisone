"""Health and about endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_ok_with_dependencies() -> None:
    client = TestClient(app)
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "postgres" in body["dependencies"]
    assert "redis" in body["dependencies"]


def test_about_includes_developer_credit() -> None:
    client = TestClient(app)
    response = client.get("/about")
    assert response.status_code == 200
    body = response.json()
    assert body["developer"] == "Devang Shah"
    assert body["name"] == "AegisOne"


def test_healthz_sends_security_headers() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    headers = response.headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Permissions-Policy"] == "()"
    assert headers["X-Developer"] == "Devang Shah"
    assert headers["X-AegisOne-App"] == "AegisOne"
    assert "Content-Security-Policy" in headers


def test_healthz_assigns_request_id() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert "X-Request-Id" in response.headers
    assert len(response.headers["X-Request-Id"]) >= 8


def test_healthz_preserves_inbound_request_id() -> None:
    client = TestClient(app)
    response = client.get("/healthz", headers={"X-Request-Id": "abc12345"})
    assert response.headers["X-Request-Id"] == "abc12345"
