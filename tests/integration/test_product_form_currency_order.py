"""The product form lists the tenant's currencies in the order they were configured.

The pricing-option dropdown preselects its first entry, so the first currency a publisher
configured is the default for new pricing options. Upstream returned the currency limits in
table order, which is undefined.
"""

from datetime import UTC, datetime, timedelta

import pytest

from tests.factories import AuthorizedPropertyFactory, CurrencyLimitFactory, TenantFactory
from tests.harness._base import IntegrationEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


def test_gam_product_form_lists_currencies_in_configuration_order(authenticated_admin_session):
    with IntegrationEnv(tenant_id="cur_order"):
        # TenantFactory already gives the tenant a USD currency limit (created now).
        tenant = TenantFactory(tenant_id="cur_order", ad_server="google_ad_manager")
        AuthorizedPropertyFactory(tenant=tenant, publisher_domain="unwind-test", tags=["all_inventory"])
        later = datetime.now(UTC) + timedelta(minutes=1)
        CurrencyLimitFactory(tenant=tenant, currency_code="EUR", created_at=later)
        CurrencyLimitFactory(tenant=tenant, currency_code="CAD", created_at=later + timedelta(minutes=1))

        resp = authenticated_admin_session.get("/tenant/cur_order/products/add")
        assert resp.status_code == 200
        page = resp.data.decode()
        assert page.index('<option value="USD"') < page.index('<option value="EUR"') < page.index('<option value="CAD"')
