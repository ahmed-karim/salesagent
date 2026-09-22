"""A deactivated tenant's landing page is a notice, not a list of endpoints it will refuse."""

from unittest.mock import patch

from src.landing.landing_page import generate_tenant_landing_page


def test_deactivated_tenant_gets_a_notice_without_endpoint_urls():
    tenant = {"tenant_id": "pub", "name": "Unwind Media", "subdomain": "pub", "is_active": False}
    page = generate_tenant_landing_page(tenant, "agent.example.com")

    assert "Unwind Media" in page
    assert "not currently accepting requests" in page
    assert "/mcp" not in page
    assert "/admin/" in page  # operators can still sign in from the notice


def test_active_tenant_still_gets_the_full_page():
    tenant = {"tenant_id": "pub", "name": "Unwind Media", "subdomain": "pub", "is_active": True}
    with patch("src.core.tenant_status.is_tenant_ad_server_configured", return_value=True):
        page = generate_tenant_landing_page(tenant, "agent.example.com")

    assert "/mcp" in page
    assert "not currently accepting requests" not in page


def test_unconfigured_tenant_still_gets_the_pending_page():
    tenant = {"tenant_id": "pub", "name": "Unwind Media", "subdomain": "pub"}
    with patch("src.core.tenant_status.is_tenant_ad_server_configured", return_value=False):
        page = generate_tenant_landing_page(tenant, "agent.example.com")

    assert "Pending Configuration" in page
    assert "Sign In to Configure" in page
