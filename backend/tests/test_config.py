"""Settings tests."""

from __future__ import annotations

from app.core.config import settings


def test_default_environment_is_dev() -> None:
    assert settings.environment in {"dev", "staging", "prod"}


def test_cors_origins_list_parses_comma_separated() -> None:
    assert isinstance(settings.cors_origins_list, list)
    assert all(isinstance(o, str) for o in settings.cors_origins_list)


def test_trusted_proxy_networks_includes_loopback() -> None:
    nets = settings.trusted_proxy_networks
    assert any("127.0.0.1" in str(n) for n in nets)


def test_branding_defaults_match_master_prompt() -> None:
    assert settings.app_name == "AegisOne"
    assert settings.developer_name == "Devang Shah"
    assert "Secure" in settings.app_tagline
