"""Deactivating a sales agent refuses its buyers with SERVICE_UNAVAILABLE; reactivating lets them back in.

Real database, real Flask app, real form POSTs. The buyer side is exercised through
``_resolve_identity()`` with the tenant's virtual host and a real principal token, which is the
one resolution every MCP, A2A and REST request goes through before business logic runs.
"""

import pytest

from src.core.exceptions import AdCPServiceUnavailableError
from src.core.resolved_identity import _resolve_identity
from tests.factories import TenantFactory
from tests.factories.principal import PrincipalFactory, plaintext_token_for
from tests.harness._base import IntegrationEnv
from tests.helpers.credentials import credential_headers

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

HOST = "deactivate-test.example.com"


def test_deactivate_refuses_buyers_and_reactivate_lets_them_back_in(authenticated_admin_session):
    client = authenticated_admin_session
    with IntegrationEnv(tenant_id="dz_buyers"):
        tenant = TenantFactory(tenant_id="dz_buyers", name="Buyer Publisher", virtual_host=HOST)
        principal = PrincipalFactory(tenant=tenant)
        anonymous = {"host": HOST}
        buyer = {**credential_headers(token=plaintext_token_for(principal.principal_id)), "host": HOST}

        assert _resolve_identity(buyer, require_valid_token=True).principal.principal_id == principal.principal_id

        resp = client.post("/tenant/dz_buyers/deactivate", data={"confirm_name": "Buyer Publisher"})
        assert resp.status_code == 302

        with pytest.raises(AdCPServiceUnavailableError) as exc_info:
            _resolve_identity(buyer, require_valid_token=True)
        assert exc_info.value.retry_after == 300
        with pytest.raises(AdCPServiceUnavailableError):
            _resolve_identity(anonymous, require_valid_token=False)

        resp = client.post("/admin/tenant/dz_buyers/reactivate")
        assert resp.status_code == 302
        assert _resolve_identity(buyer, require_valid_token=True).principal.principal_id == principal.principal_id


def test_unknown_host_still_resolves_to_no_tenant(integration_db):
    assert _resolve_identity({"host": "nobody.example.net"}, require_valid_token=False).tenant is None
