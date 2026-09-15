"""Admin pages that rendered a 500 on 2026-09-15 (FORK.md divergences 21 and 22), graded through
the real Flask routes against a real database.

* Inventory profile **Edit** page: the template serialised ``profile.formats``; the model attribute
  is ``format_ids``, so Jinja's Undefined hit ``tojson`` and every edit page was a 500.
* GAM custom-targeting-keys API: built an OAuth refresh-token client unconditionally, so a tenant
  authenticated with a service-account key (the only method the pilot uses) got a 500 from the
  line-item viewer.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from src.core.database.models import Tenant

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

TENANT_ID = "ui_render_fixes"


@pytest.fixture
def env(integration_db, monkeypatch):
    """A committed tenant with one inventory profile and a service-account GAM config."""
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    from tests.factories import AdapterConfigFactory, InventoryProfileFactory, TenantFactory
    from tests.harness._base import IntegrationEnv

    with IntegrationEnv() as env:
        TenantFactory(tenant_id=TENANT_ID, name="UI Render Fixes", subdomain="uirender", ad_server="google_ad_manager")
        session = env.get_session()
        tenant = session.scalars(select(Tenant).filter_by(tenant_id=TENANT_ID)).one()
        profile = InventoryProfileFactory(
            tenant=tenant,
            name="Edit Me",
            format_ids=[{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"}],
        )
        AdapterConfigFactory(
            tenant=tenant,
            adapter_type="google_ad_manager",
            gam_auth_method="service_account",
            gam_network_code="12345678",
            gam_service_account_json='{"type": "service_account", "client_email": "sa@example.iam.gserviceaccount.com"}',
        )
        env.profile_id = profile.id
        yield env


def test_inventory_profile_edit_page_renders_with_stored_formats(authenticated_admin_client, env):
    resp = authenticated_admin_client.get(f"/tenant/{TENANT_ID}/inventory-profiles/{env.profile_id}/edit")
    assert resp.status_code == 200, resp.data[:500]
    html = resp.data.decode()
    assert "Edit Me" in html
    # The stored format list seeds the editor's state; it used to be Jinja Undefined.
    assert '"id": "display_300x250"' in html


def test_custom_targeting_keys_route_uses_the_adapter_auth_method(authenticated_admin_client, env):
    manager = MagicMock()
    manager.get_client.return_value = object()
    discovery = MagicMock()
    discovery.discover_custom_targeting.return_value = [{"id": "111", "name": "section"}]
    with (
        patch("src.admin.blueprints.gam.GAMClientManager", return_value=manager) as manager_cls,
        patch("src.admin.blueprints.gam.GAMInventoryDiscovery", return_value=discovery),
    ):
        resp = authenticated_admin_client.get(f"/tenant/{TENANT_ID}/gam/api/custom-targeting-keys")
    assert resp.status_code == 200, resp.data[:500]
    assert resp.get_json() == {"success": True, "keys": [{"id": "111", "name": "section"}]}
    # The client is built from the adapter's own config: service-account JSON, not a refresh token.
    config, network_code = manager_cls.call_args.args
    assert network_code == "12345678"
    assert "service_account_json" in config
    assert "refresh_token" not in config
