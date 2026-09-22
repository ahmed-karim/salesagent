"""Longitude patch: pause a product so it can be set up without being for sale.

``Product.paused_at`` set: the buyer-facing listings (ProductRepository.list_all and
list_all_with_inventory, behind get_products and the capabilities declaration) skip it and
create_media_buy refuses it with PRODUCT_UNAVAILABLE; the admin product list still shows it,
badged "Paused", with a Resume button. Real database, real Flask app, real form POSTs.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.core.database.models import Product
from src.core.database.repositories import MediaBuyUoW
from src.core.database.repositories.product import ProductRepository
from src.core.exceptions import AdCPProductUnavailableError
from tests.factories import ProductFactory, TenantFactory
from tests.harness._base import IntegrationEnv
from tests.harness.media_buy_create import MediaBuyCreateEnv
from tests.helpers.envelope_assertions import raises_adcp
from tests.integration.test_create_media_buy_behavioral import _make_request

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


def _paused_at(env, tenant_id: str, product_id: str):
    session = env.get_session()
    session.expire_all()
    return session.scalars(select(Product.paused_at).filter_by(tenant_id=tenant_id, product_id=product_id)).one()


class TestBuyersDoNotSeePausedProducts:
    def test_listings_skip_paused_products_but_lookup_by_id_still_finds_them(self, integration_db):
        with IntegrationEnv(tenant_id="pp_repo") as env:
            tenant = TenantFactory(tenant_id="pp_repo")
            ProductFactory(tenant=tenant, product_id="live", name="Live")
            ProductFactory(tenant=tenant, product_id="paused", name="Paused", paused_at=datetime.now(UTC))
            repo = ProductRepository(env.get_session(), "pp_repo")
            assert [p.product_id for p in repo.list_all()] == ["live"]
            assert [p.product_id for p in repo.list_all_with_inventory()] == ["live"]
            # The admin UI and existing media buys still reach the product itself.
            assert repo.get_by_id("paused") is not None

    def test_create_media_buy_refuses_a_paused_product_as_unavailable(self, integration_db):
        with MediaBuyCreateEnv() as env:
            tenant, _principal = env.setup_default_data()
            product, _pricing = env.setup_product_chain(tenant)
            product.paused_at = datetime.now(UTC)
            # The boundary answers with the buyer-facing code; assert on the wire.
            with raises_adcp(AdCPProductUnavailableError):
                env.call_impl(req=_make_request())
            tenant_id = env._tenant_id

        with MediaBuyUoW(tenant_id) as uow:
            assert uow.media_buys.list_all() == [], "a refused buy must persist nothing"


class TestPauseFromTheProductList:
    def test_pause_then_resume(self, authenticated_admin_session):
        with IntegrationEnv(tenant_id="pp_admin") as env:
            tenant = TenantFactory(tenant_id="pp_admin")
            ProductFactory(tenant=tenant, product_id="homepage", name="Homepage Takeover")

            resp = authenticated_admin_session.post(
                "/tenant/pp_admin/products/homepage/pause", data={"paused": "1"}, follow_redirects=True
            )
            assert resp.status_code == 200
            assert b"is paused" in resp.data
            assert b">Paused</span>" in resp.data and b">Resume</button>" in resp.data
            assert _paused_at(env, "pp_admin", "homepage") is not None

            resp = authenticated_admin_session.post(
                "/tenant/pp_admin/products/homepage/pause", data={"paused": "0"}, follow_redirects=True
            )
            assert resp.status_code == 200
            assert b"is live again" in resp.data
            assert b">Paused</span>" not in resp.data and b">Pause</button>" in resp.data
            assert _paused_at(env, "pp_admin", "homepage") is None

    def test_unknown_product_is_reported_not_created(self, authenticated_admin_session):
        with IntegrationEnv(tenant_id="pp_none") as env:
            TenantFactory(tenant_id="pp_none")
            resp = authenticated_admin_session.post(
                "/tenant/pp_none/products/nope/pause", data={"paused": "1"}, follow_redirects=True
            )
            assert resp.status_code == 200
            assert b"Product not found" in resp.data
            assert env.get_session().scalars(select(Product).filter_by(tenant_id="pp_none")).all() == []
